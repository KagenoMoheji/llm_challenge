import os
import inspect
import sys
import time
import traceback
PYPATH = os.path.dirname(os.path.abspath(inspect.getfile(inspect.currentframe())))
MODNAME = os.path.splitext(os.path.basename(inspect.getfile(inspect.currentframe())))[0]

# その他のモジュールやROOTPATHのディレクトリ起点の相対パスでのimport
import importlib.util
import re
import shlex
from capass_core.cli.common.conf import read_installed_mode
from capass_core.cli.common.errors import (
    AppDirectoryError,
    ModeNotInstalledError,
    MultipleModesInstalledError,
    RoleConflictError,
)
from capass_core.cli.common.paths import SERVICE_NAME, AppPaths
from capass_core.cli.common.system import SystemOps

MODE_AGENT = "agent"  # AIエージェントの作業環境
MODE_TOOLSERVER = "toolserver"  # ツールサーバ
MODE_SERVER = "server"  # CaPassサーバ
MODES = (MODE_TOOLSERVER, MODE_AGENT, MODE_SERVER)
MODE_LABELS = {MODE_AGENT: "AIエージェント", MODE_TOOLSERVER: "ツールサーバ", MODE_SERVER: "CaPassサーバ"}
# モードごとの、CLIの実装状況(capass --help に表示する。実装が進んだら更新する)
MODE_STATUS = {MODE_TOOLSERVER: "初期導入(init)のみ実装済み", MODE_AGENT: "未実装", MODE_SERVER: "未実装"}


def _label(mode: str) -> str:
    return MODE_LABELS.get(mode, mode)


# ---------- (1) 同じPython環境に、インストールされているモードのパッケージ ----------
def package_name(mode: str) -> str:
    """モードのPythonパッケージ名。モードごとのパッケージ(別々に配布される)は、capass_<モード> という名前にそろえる。"""
    return f"capass_{mode}"


def install_hint(mode: str) -> str:
    return f'pip install "capass[{mode}]"'


def detect_installed_modes(find_spec=None) -> set[str]:
    """このPython環境に、インストールされているモードを返す。パッケージを、importせずに、有無だけを調べる(find_spec)。
    find_specは、テストで差し替えるための引数(本番は省略)。"""
    find_spec = find_spec or importlib.util.find_spec
    return {mode for mode in MODES if find_spec(package_name(mode)) is not None}


def ensure_single_mode(installed: set[str]) -> str:
    """インストール済みのモードが、ちょうど1つであることを確認して、そのモードを返す。
    0個ならModeNotInstalledError、2個以上ならMultipleModesInstalledError。
    AIエージェントとツールサーバ(とCaPassサーバ)を、同じPython環境で、同時に使えないようにするための、ガード。
    なお、これは、同じPython環境の中の確認。別のPython環境(venv)にあるモードは、検出できない。サーバ全体の確認は、下の ensure_host_mode。"""
    if not installed:
        hints = "、".join(install_hint(m) for m in MODES)
        raise ModeNotInstalledError(f"モードがインストールされていません。モードを指定して、インストールしてください。\n  例: {hints}")
    if len(installed) > 1:
        names = ", ".join(sorted(installed))
        raise MultipleModesInstalledError(
            "capass[server, toolserver, agent] のうち、2つ以上を、同時に使うことはできません"
            f"(同じPython環境に、複数のモードがインストールされています)。\n  現在のインストール状態: {names}\n"
            "  使わないモードを、pip uninstall で削除してください(パッケージ名は capass-<モード>)。"
        )
    return next(iter(installed))


# ---------- (2) サーバ全体(/opt/capass と、稼働中のプロセス)に、設定されているモード ----------
def _exists(path) -> bool:
    """ファイルの有無。権限が無くて調べられない場合(実行ユーザの持ち物のkeys/を、一般ユーザが調べる場合)は、Falseとする。"""
    try:
        return path.exists()
    except PermissionError:
        return False


def detect_role_evidence(paths: AppPaths) -> dict[str, list[str]]:
    """アプリディレクトリに、設定済みのモードと、その根拠を返す。根拠は、(1) 設定ファイルのモード、(2) 鍵ファイルのファイル名(<モード>.key / <モード>.pub)。"""
    evidence: dict[str, list[str]] = {}
    mode = read_installed_mode(paths)
    if mode:
        evidence.setdefault(mode, []).append(f"設定ファイル {paths.conf_file}")
    for candidate in MODES:
        for key_path in (paths.private_key_path(candidate), paths.public_key_path(candidate)):
            if _exists(key_path):
                evidence.setdefault(candidate, []).append(f"鍵ファイル {key_path}")
    return evidence


PYTHON_PROGRAM = re.compile(r"^python[\d.]*$")
SERVER_PROGRAMS = ("uvicorn", "gunicorn", "hypercorn", "daphne", "granian")  # ASGIサーバ(capass_<モード>.xxx:app を起動する)


def _is_mode_process(command_line: str, mode: str) -> bool:
    """プロセスのコマンドラインが、そのモードの常駐プロセスの起動の形か。プログラム(1つ目の語)が、pythonかASGIサーバのときだけ、見る。
    エディタ、grep、シェルの -c(長い文字列の中に、パッケージ名が、含まれる場合)などを、誤検出しないため。
    起動の形: (1) python -m capass_<モード>  (2) capass_<モード>.xxx:app(uvicorn など)  (3) コンソールスクリプト capass-<モード>"""
    try:
        tokens = shlex.split(command_line)
    except ValueError:
        tokens = command_line.split()
    if not tokens:
        return False
    program = os.path.basename(tokens[0])
    package, script = package_name(mode), f"capass-{mode}"
    if program == script:
        return True
    is_python = bool(PYTHON_PROGRAM.match(program))
    if not (is_python or program in SERVER_PROGRAMS):
        return False
    rest = tokens[1:]
    app_target = re.compile(rf"^{package}(?:\.\w+)+:\w+$")
    for i, token in enumerate(rest):
        if token == "-m" and i + 1 < len(rest) and re.match(rf"^{package}(?:\.[\w.]+)?$", rest[i + 1]):
            return True
        if app_target.match(token) or os.path.basename(token) == script:
            return True
    return False


def detect_running_modes(paths: AppPaths, ops: SystemOps) -> dict[str, list[str]]:
    """稼働中の常駐プロセスの、モードと根拠を返す。(1) systemdのサービス capass.service が稼働中(モードは、設定ファイルから)、
    (2) プロセスのコマンドラインに、他のモードの起動の形がある(capass init を使わずに起動された、サーバなど)。
    これは、確認できる範囲の、目安。systemctl や ps が使えない環境(コンテナなど)では、調べられない。"""
    evidence: dict[str, list[str]] = {}
    if ops.service_active(SERVICE_NAME):
        try:
            mode = read_installed_mode(paths)
        except AppDirectoryError:
            mode = None
        if mode:
            evidence.setdefault(mode, []).append(f"systemdのサービス {SERVICE_NAME} が稼働中")
    for line in ops.process_command_lines():
        for mode in MODES:
            if _is_mode_process(line, mode):
                evidence.setdefault(mode, []).append(f"プロセス `{line[:100]}`")
    return evidence


def ensure_host_mode(paths: AppPaths, mode: str, ops: SystemOps) -> None:
    """このサーバで、modeを使ってよいかを確認する。別のモードの、設定(/opt/capass の設定ファイルのモード、鍵ファイルのファイル名)、
    または、稼働中の常駐プロセス(systemd、ps)があれば、RoleConflictError。
    AIエージェントとツールサーバ(とCaPassサーバ)を、同じサーバに同居させないための、ガード。
    AIエージェントは、プロンプトインジェクションなどで、意図しない操作をする恐れがある。同じサーバにツールサーバがあると、
    ツールサーバの秘密鍵や認証情報に、直接アクセスでき、CaPassサーバの承認と署名の確認を、迂回できてしまう。
    アプリディレクトリは、サーバ全体で1つ(/opt/capass)に固定しているので、ユーザや、Python環境(venv)が違っても、同居を検出できる。
    なお、これは、設定ミスを防ぐ仕組みで、悪意のある操作(ファイルの削除など)は、防げない。"""
    evidence = detect_role_evidence(paths)
    for found_mode, found in detect_running_modes(paths, ops).items():
        evidence.setdefault(found_mode, []).extend(found)
    others = {m: e for m, e in evidence.items() if m != mode}
    if not others:
        return
    existing = "、".join(f"「{_label(m)}」({'、'.join(e)})" for m, e in sorted(others.items()))
    raise RoleConflictError(
        f"このサーバは、すでに{existing}として使われています。「{_label(mode)}」のモードを、同じサーバに同居させることはできません。\n"
        "  AIエージェントとツールサーバが同居すると、AIエージェントが、ツールサーバの秘密鍵や認証情報に直接アクセスでき、CaPassサーバの承認と署名の確認を、迂回できてしまうためです。\n"
        "  別のサーバで設定してください(初期化を取り消す機能は、まだありません)。"
    )


def describe_current_mode(paths: AppPaths) -> str:
    """`capass --help` に表示する、このサーバの、初期化済みのモード。"""
    try:
        mode = read_installed_mode(paths)
    except AppDirectoryError:
        return "不明(設定ファイルを読めません)"
    if mode is None:
        return "未初期化(capass init で、初期化します)"
    return f"{mode}({_label(mode)}。{paths.root} で初期化済み)"

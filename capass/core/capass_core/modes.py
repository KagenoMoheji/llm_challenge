import os
import inspect
import sys
import time
import traceback
PYPATH = os.path.dirname(os.path.abspath(inspect.getfile(inspect.currentframe())))
MODNAME = os.path.splitext(os.path.basename(inspect.getfile(inspect.currentframe())))[0]

# その他のモジュールやROOTPATHのディレクトリ起点の相対パスでのimport
import importlib.util
from capass_core.errors import ModeNotInstalledError, MultipleModesInstalledError

MODE_AGENT = "agent"  # AIエージェントの作業環境
MODE_TOOLSERVER = "toolserver"  # ツールサーバ
MODE_SERVER = "server"  # CaPassサーバ
MODES = (MODE_TOOLSERVER, MODE_AGENT, MODE_SERVER)
MODE_LABELS = {MODE_AGENT: "AIエージェント", MODE_TOOLSERVER: "ツールサーバ", MODE_SERVER: "CaPassサーバ"}
# モードごとの、CLIの実装状況(capass --help に表示する。実装が進んだら更新する)
MODE_STATUS = {MODE_TOOLSERVER: "初期導入(init)のみ実装済み", MODE_AGENT: "未実装", MODE_SERVER: "未実装"}


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
    なお、これは、同じPython環境の中の確認。別のPython環境(venv)にあるモードは、検出できない。サーバ全体の確認は、roles.py(/opt/capass)。"""
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

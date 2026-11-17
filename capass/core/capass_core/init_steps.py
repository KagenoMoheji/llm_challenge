import os
import inspect
import sys
import time
import traceback
PYPATH = os.path.dirname(os.path.abspath(inspect.getfile(inspect.currentframe())))
MODNAME = os.path.splitext(os.path.basename(inspect.getfile(inspect.currentframe())))[0]

# その他のモジュールやROOTPATHのディレクトリ起点の相対パスでのimport
import re
import shlex
from dataclasses import dataclass
from pathlib import Path
from capass_core import __version__
from capass_core.conf import read_installed_mode, render_conf
from capass_core.errors import (
    AlreadyInitializedError,
    AppDirectoryError,
    InvalidOptionError,
    NotRootError,
    UnsupportedEnvironmentError,
)
from capass_core.fileio import write_atomic
from capass_core.keys import KeyPairInfo, create_key_files
from capass_core.paths import NOLOGIN_SHELL, SERVICE_NAME, AppPaths
from capass_core.roles import ensure_role_available
from capass_core.system import SystemContext
from capass_core.systemd import UNIT_MARKER, render_unit

USER_PATTERN = re.compile(r"^[a-z_][a-z0-9_-]{0,31}$")
PORT_MIN = 1024  # 実行ユーザ(root以外)が、待ち受けできるポート
PORT_MAX = 65535


@dataclass(frozen=True)
class InitSpec:
    """常駐プロセスを持つモード(toolserver、server)の、初期導入の、モードごとの違い。モードのパッケージ(capass_toolserver など)が、定義する。"""

    mode: str  # 例: "toolserver"
    unit_description: str  # systemdのサービスの説明
    exec_args: str = "serve"  # サービスが実行するコマンド(bin/capass の引数)
    daemon_label: str = "常駐プロセス"  # 次の手順の表示に使う、常駐プロセスの呼び名


@dataclass(frozen=True)
class InitOptions:
    user: str
    port: int
    log_dir: Path | None = None  # 省略時は {アプリディレクトリ}/logs
    data_dir: Path | None = None  # 省略時は {アプリディレクトリ}/data


@dataclass(frozen=True)
class InitResult:
    mode: str
    user: str
    group: str
    user_created: bool
    port: int
    log_dir: Path
    data_dir: Path
    wrapper_path: Path
    conf_path: Path
    unit_path: Path
    keys: KeyPairInfo


def _validate_dir(value: Path | None, default: Path, option: str, paths: AppPaths) -> Path:
    path = Path(value) if value is not None else default
    if not path.is_absolute():
        raise InvalidOptionError(f"{option} は、絶対パスで指定してください: {path}")
    path = Path(os.path.normpath(path))
    if path == Path("/") or path == paths.root:
        raise InvalidOptionError(f"{option} に、指定できない場所です: {path}")
    for reserved in (paths.bin_dir, paths.confs_dir, paths.keys_dir):
        if path == reserved or reserved in path.parents:
            raise InvalidOptionError(f"{option} に、アプリディレクトリの {reserved.name}/ の中は、指定できません: {path}")
    return path


def validate_options(options: InitOptions, paths: AppPaths) -> InitOptions:
    """オプションの値を確認して、省略されたログ・データのディレクトリを補う。"""
    if not USER_PATTERN.match(options.user) or options.user == "root":
        raise InvalidOptionError(f"--user は、root以外の、英小文字・数字・_・- のユーザ名(32文字まで)を指定してください: {options.user}")
    if not (PORT_MIN <= options.port <= PORT_MAX):
        raise InvalidOptionError(f"--port は、{PORT_MIN}〜{PORT_MAX} を指定してください(実行ユーザは、root以外のため): {options.port}")
    log_dir = _validate_dir(options.log_dir, paths.default_log_dir, "--log-dir", paths)
    data_dir = _validate_dir(options.data_dir, paths.default_data_dir, "--data-dir", paths)
    if log_dir == data_dir:
        raise InvalidOptionError("--log-dir と --data-dir に、同じ場所は指定できません")
    return InitOptions(options.user, options.port, log_dir, data_dir)


def _make_dir(context: SystemContext, path: Path, mode: int, user: str, group: str) -> None:
    try:
        path.mkdir(parents=True, exist_ok=True)
        os.chmod(path, mode)
        context.ops.chown(path, user, group)
    except OSError as e:
        raise AppDirectoryError(f"ディレクトリを作成できません: {path} ({e})")


def _write_file(context: SystemContext, path: Path, text: str, mode: int, user: str, group: str) -> None:
    try:
        write_atomic(path, text, mode)
        context.ops.chown(path, user, group)
    except OSError as e:
        raise AppDirectoryError(f"ファイルを書き込めません: {path} ({e})")


def render_wrapper(python_executable: str) -> str:
    """実行ファイル(シェルスクリプト)。CLIをインストールしたPython環境で、capass_core.cli.mainを起動する。"""
    return (
        "#!/bin/sh\n"
        "# CaPassクライアント(capass init が作成しました)。インストール済みのPython環境の capass を、起動します。\n"
        f"exec {shlex.quote(python_executable)} -m capass_core.cli.main \"$@\"\n"
    )


def run_init(spec: InitSpec, options: InitOptions, context: SystemContext) -> InitResult:
    """常駐プロセスを持つモードの、初期導入。root権限で、次を行う: 実行ユーザ/グループの作成、アプリディレクトリの作成、実行ファイルの配置、
    鍵の作成、systemdのサービスファイルの作成、設定ファイルの作成(最後)。
    確認(root権限、環境、オプション、初期化済みか、別のモードの設定)は、最初に全て行い、失敗したら、何も変更しない。
    途中で失敗した場合は、設定ファイル(初期化済みの目印)が無いので、原因を直して、再実行できる(作成済みのものは、そのまま使う)。"""
    paths, ops = context.paths, context.ops

    # ---- 1. 確認(何も変更しない) ----
    if not ops.is_root():
        raise NotRootError("root権限で実行してください(例: sudo capass init)。ユーザ・ディレクトリ・サービスファイルを作成するためです。")
    if not context.systemd_dir.is_dir():
        raise UnsupportedEnvironmentError(
            f"systemdのサービスファイルの置き場所が、ありません: {context.systemd_dir}\n"
            "  いまは、RPM/yum系のLinux(systemd)だけを想定しています。他のOSへの対応は、docs/TODO.md を参照してください。"
        )
    options = validate_options(options, paths)
    if read_installed_mode(paths) == spec.mode:
        raise AlreadyInitializedError(f"このサーバは、すでに初期化されています: {paths.conf_file}\n  設定の変更や、再初期化の機能は、まだありません。")
    ensure_role_available(paths, spec.mode)  # 別のモードの設定や鍵があれば、RoleConflictError
    unit_path = context.systemd_dir / SERVICE_NAME
    if unit_path.exists() and UNIT_MARKER not in unit_path.read_text(encoding="utf-8", errors="replace"):
        raise AppDirectoryError(f"{unit_path} が、すでに存在します(capass init が作成したものではありません)。上書きしないので、確認してください。")

    # ---- 2. 実行ユーザ/グループ ----
    group = ops.user_group(options.user)
    user_created = group is None
    if user_created:
        group = options.user
        if not ops.group_exists(group):
            ops.create_group(group)
        ops.create_user(options.user, group, paths.root, NOLOGIN_SHELL)

    # ---- 3. ディレクトリ(実行ファイルと設定は、実行ユーザが書き換えられないよう、rootの持ち物にする) ----
    _make_dir(context, paths.root, 0o755, "root", "root")
    _make_dir(context, paths.bin_dir, 0o755, "root", "root")
    _make_dir(context, paths.confs_dir, 0o755, "root", "root")
    _make_dir(context, paths.keys_dir, 0o700, options.user, group)
    _make_dir(context, options.log_dir, 0o750, options.user, group)
    _make_dir(context, options.data_dir, 0o700, options.user, group)

    # ---- 4. 実行ファイル ----
    _write_file(context, paths.wrapper, render_wrapper(ops.python_executable()), 0o755, "root", "root")

    # ---- 5. 鍵(既存の鍵があれば、そのまま使う) ----
    keys = create_key_files(paths, spec.mode, ops, options.user, group)

    # ---- 6. systemdのサービスファイル ----
    unit = render_unit(paths, options.user, group, options.log_dir, options.data_dir, spec.unit_description, spec.exec_args)
    _write_file(context, unit_path, unit, 0o644, "root", "root")

    # ---- 7. 設定ファイル(最後に作る。これが、初期化済みの目印) ----
    conf_text = render_conf(spec.mode, __version__, options.user, group, options.port, options.log_dir, options.data_dir, paths)
    _write_file(context, paths.conf_file, conf_text, 0o644, "root", "root")

    return InitResult(spec.mode, options.user, group, user_created, options.port, options.log_dir, options.data_dir, paths.wrapper, paths.conf_file, unit_path, keys)

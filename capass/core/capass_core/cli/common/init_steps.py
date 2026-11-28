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
from capass_core.cli.common.conf import read_installed_mode
from capass_core.cli.common.errors import (
    AlreadyInitializedError,
    AppDirectoryError,
    InvalidOptionError,
    NotRootError,
    UnsupportedEnvironmentError,
)
from capass_core.cli.common.fileio import write_atomic
from capass_core.cli.common.keys import KeyPairInfo
from capass_core.cli.common.paths import NOLOGIN_SHELL, AppPaths
from capass_core.cli.common.system import SystemContext
from capass_core.cli.common.systemd import UNIT_MARKER

# 初期導入(init)の、手順の部品。モードごとの手順(run_init)は、各モードの cli/commands/init.py が、これらを組み合わせて書く
# (AIエージェントはサービスファイルを作らない、など、モードによって手順が違うため)。

USER_PATTERN = re.compile(r"^[a-z_][a-z0-9_-]{0,31}$")
PORT_MIN = 1024  # 実行ユーザ(root以外)が、待ち受けできるポート
PORT_MAX = 65535


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
    unit_path: Path | None  # サービスファイル(サービスを持たないモードは、None)
    keys: KeyPairInfo


# ---------- オプション ----------
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


# ---------- 確認(何も変更しない) ----------
def check_root(context: SystemContext) -> None:
    if not context.ops.is_root():
        raise NotRootError("root権限で実行してください(例: sudo capass init)。ユーザ・ディレクトリ・サービスファイルを作成するためです。")


def check_systemd_dir(context: SystemContext) -> None:
    if not context.systemd_dir.is_dir():
        raise UnsupportedEnvironmentError(
            f"systemdのサービスファイルの置き場所が、ありません: {context.systemd_dir}\n"
            "  いまは、RPM/yum系のLinux(systemd)だけを想定しています。他のOSへの対応は、docs/TODO.md を参照してください。"
        )


def check_not_initialized(paths: AppPaths, mode: str) -> None:
    """設定ファイル(初期化済みの目印)が、すでにmodeで作られていれば、AlreadyInitializedError。"""
    if read_installed_mode(paths) == mode:
        raise AlreadyInitializedError(f"このサーバは、すでに初期化されています: {paths.conf_file}\n  設定の変更や、再初期化の機能は、まだありません。")


def check_unit_file_is_ours(unit_path: Path) -> None:
    """サービスファイルが、すでに存在する場合は、capass init が作ったものだけを、上書きしてよい。"""
    if unit_path.exists() and UNIT_MARKER not in unit_path.read_text(encoding="utf-8", errors="replace"):
        raise AppDirectoryError(f"{unit_path} が、すでに存在します(capass init が作成したものではありません)。上書きしないので、確認してください。")


# ---------- 変更(ユーザ、ディレクトリ、ファイル) ----------
def ensure_service_user(context: SystemContext, user: str) -> tuple[str, bool]:
    """実行ユーザ/グループを、用意する。(主グループの名前, 新しく作ったか)を返す。既存のユーザなら、そのまま使う。"""
    ops, paths = context.ops, context.paths
    group = ops.user_group(user)
    if group is not None:
        return group, False
    group = user
    if not ops.group_exists(group):
        ops.create_group(group)
    ops.create_user(user, group, paths.root, NOLOGIN_SHELL)
    return group, True


def make_dir(context: SystemContext, path: Path, mode: int, user: str, group: str) -> None:
    try:
        path.mkdir(parents=True, exist_ok=True)
        os.chmod(path, mode)
        context.ops.chown(path, user, group)
    except OSError as e:
        raise AppDirectoryError(f"ディレクトリを作成できません: {path} ({e})")


def write_file(context: SystemContext, path: Path, text: str, mode: int, user: str, group: str) -> None:
    try:
        write_atomic(path, text, mode)
        context.ops.chown(path, user, group)
    except OSError as e:
        raise AppDirectoryError(f"ファイルを書き込めません: {path} ({e})")


def create_app_dirs(context: SystemContext, user: str, group: str, log_dir: Path | None = None, data_dir: Path | None = None) -> None:
    """アプリディレクトリを作る。実行ファイルと設定は、実行ユーザが書き換えられないよう、rootの持ち物にする。
    鍵は実行ユーザだけが読める。log_dir / data_dir は、指定されたら作る(ログやデータを持たないモードは、None)。"""
    paths = context.paths
    make_dir(context, paths.root, 0o755, "root", "root")
    make_dir(context, paths.bin_dir, 0o755, "root", "root")
    make_dir(context, paths.confs_dir, 0o755, "root", "root")
    make_dir(context, paths.keys_dir, 0o700, user, group)
    if log_dir is not None:
        make_dir(context, log_dir, 0o750, user, group)
    if data_dir is not None:
        make_dir(context, data_dir, 0o700, user, group)


def render_wrapper(python_executable: str) -> str:
    """実行ファイル(シェルスクリプト)。CLIをインストールしたPython環境で、capass_core.cli.mainを起動する。"""
    return (
        "#!/bin/sh\n"
        "# CaPassクライアント(capass init が作成しました)。インストール済みのPython環境の capass を、起動します。\n"
        f"exec {shlex.quote(python_executable)} -m capass_core.cli.main \"$@\"\n"
    )


def write_wrapper(context: SystemContext) -> Path:
    """実行ファイル(bin/capass)を、rootの持ち物として、配置する。"""
    path = context.paths.wrapper
    write_file(context, path, render_wrapper(context.ops.python_executable()), 0o755, "root", "root")
    return path

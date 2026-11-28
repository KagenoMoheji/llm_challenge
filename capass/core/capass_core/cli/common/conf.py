import os
import inspect
import sys
import time
import traceback
PYPATH = os.path.dirname(os.path.abspath(inspect.getfile(inspect.currentframe())))
MODNAME = os.path.splitext(os.path.basename(inspect.getfile(inspect.currentframe())))[0]

# その他のモジュールやROOTPATHのディレクトリ起点の相対パスでのimport
import configparser
import io
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from capass_core.cli.common.errors import AppDirectoryError
from capass_core.cli.common.paths import AppPaths

CONF_HEADER = "# CaPassクライアントの設定(capass init が作成しました)。サービスの再起動が必要な設定は、変更後に、systemctl restart capass してください。\n"


@dataclass(frozen=True)
class InstalledConf:
    mode: str
    version: str
    initialized_at: str
    user: str
    group: str
    port: int
    log_dir: str
    data_dir: str


def render_conf(mode: str, version: str, user: str, group: str, port: int, log_dir: Path, data_dir: Path, paths: AppPaths) -> str:
    parser = configparser.ConfigParser(interpolation=None)
    parser["capass"] = {
        "mode": mode,
        "version": version,
        "initialized_at": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
    }
    parser["paths"] = {"app_dir": str(paths.root), "log_dir": str(log_dir), "data_dir": str(data_dir), "keys_dir": str(paths.keys_dir)}
    parser["service"] = {"user": user, "group": group, "port": str(port)}
    out = io.StringIO()
    parser.write(out)
    return CONF_HEADER + out.getvalue()


def read_conf(path: Path) -> InstalledConf:
    parser = configparser.ConfigParser(interpolation=None)
    try:
        parser.read_string(path.read_text(encoding="utf-8"))
        return InstalledConf(
            mode=parser["capass"]["mode"],
            version=parser["capass"]["version"],
            initialized_at=parser["capass"]["initialized_at"],
            user=parser["service"]["user"],
            group=parser["service"]["group"],
            port=int(parser["service"]["port"]),
            log_dir=parser["paths"]["log_dir"],
            data_dir=parser["paths"]["data_dir"],
        )
    except (OSError, configparser.Error, KeyError, ValueError) as e:
        raise AppDirectoryError(f"設定ファイルを読めません: {path} ({e})")


def read_installed_mode(paths: AppPaths) -> str | None:
    """初期化済みのモード。設定ファイルが無ければ(未初期化)None。"""
    if not paths.conf_file.exists():
        return None
    return read_conf(paths.conf_file).mode

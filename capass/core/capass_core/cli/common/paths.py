import os
import inspect
import sys
import time
import traceback
PYPATH = os.path.dirname(os.path.abspath(inspect.getfile(inspect.currentframe())))
MODNAME = os.path.splitext(os.path.basename(inspect.getfile(inspect.currentframe())))[0]

# その他のモジュールやROOTPATHのディレクトリ起点の相対パスでのimport
from dataclasses import dataclass
from pathlib import Path

APP_DIR = Path("/opt/capass")  # アプリディレクトリ。固定(1つのサーバに、1つのモードだけを置くため)
SYSTEMD_UNIT_DIR = Path("/etc/systemd/system")  # RPM/yum系(RHEL、Rocky、AlmaLinux、CentOS、Fedoraなど)を想定。他のOSへの対応は、docs/TODO.md
SERVICE_NAME = "capass.service"
NOLOGIN_SHELL = "/sbin/nologin"  # RPM/yum系の、ログインできないシェル
DEFAULT_USER = "capass"
DEFAULT_PORT = 31000


@dataclass(frozen=True)
class AppPaths:
    """アプリディレクトリ以下の、場所。本番は、APP_DIR(/opt/capass)で固定。テストでは、別の場所を指定する。"""

    root: Path = APP_DIR

    @property
    def bin_dir(self) -> Path:
        return self.root / "bin"

    @property
    def confs_dir(self) -> Path:
        return self.root / "confs"

    @property
    def keys_dir(self) -> Path:
        return self.root / "keys"

    @property
    def default_log_dir(self) -> Path:
        return self.root / "logs"

    @property
    def default_data_dir(self) -> Path:
        return self.root / "data"

    @property
    def conf_file(self) -> Path:
        """CLIのバージョンと各種設定。初期化の最後に作られる(これがあれば、初期化済み)。"""
        return self.confs_dir / "capass.conf"

    @property
    def wrapper(self) -> Path:
        """実行ファイル(systemdのサービスは、これを起動する)。"""
        return self.bin_dir / "capass"

    def private_key_path(self, mode: str) -> Path:
        """秘密鍵。ファイル名に、モードを入れる(別の場所へコピーされても、どのモードの鍵か分かるように)。例: /opt/capass/keys/toolserver.key"""
        return self.keys_dir / f"{mode}.key"

    def public_key_path(self, mode: str) -> Path:
        return self.keys_dir / f"{mode}.pub"

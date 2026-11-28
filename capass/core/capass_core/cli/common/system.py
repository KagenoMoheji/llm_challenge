import os
import inspect
import sys
import time
import traceback
PYPATH = os.path.dirname(os.path.abspath(inspect.getfile(inspect.currentframe())))
MODNAME = os.path.splitext(os.path.basename(inspect.getfile(inspect.currentframe())))[0]

# その他のモジュールやROOTPATHのディレクトリ起点の相対パスでのimport
import shutil
import subprocess
from dataclasses import dataclass, field
from pathlib import Path
from capass_core.cli.common.errors import SystemCommandError
from capass_core.cli.common.paths import SYSTEMD_UNIT_DIR, AppPaths


class SystemOps:
    """OSの操作(root権限が必要なもの)。テストでは、差し替える(tests/testlib.py)。"""

    def is_root(self) -> bool:
        raise NotImplementedError

    def user_group(self, user: str) -> str | None:
        """ユーザが存在すれば、その主グループの名前を返す。存在しなければNone。"""
        raise NotImplementedError

    def group_exists(self, group: str) -> bool:
        raise NotImplementedError

    def create_group(self, group: str) -> None:
        raise NotImplementedError

    def create_user(self, user: str, group: str, home: Path, shell: str) -> None:
        raise NotImplementedError

    def chown(self, path: Path, user: str, group: str) -> None:
        raise NotImplementedError

    def python_executable(self) -> str:
        """CLIを実行しているPythonのパス(実行ファイルのラッパーが、これを使う)。"""
        raise NotImplementedError

    def service_active(self, name: str) -> bool:
        """systemdのサービスが、稼働中(active)か。systemdが無い環境などでは、False。"""
        return False

    def process_command_lines(self) -> list[str]:
        """稼働中のプロセスの、コマンドライン(引数を含む)の一覧。調べられない環境では、空。"""
        return []


class LinuxSystemOps(SystemOps):
    """Linuxの、実際の操作。ユーザとグループの作成は、groupadd / useradd コマンドで行う。"""

    def is_root(self) -> bool:
        return os.geteuid() == 0

    def user_group(self, user: str) -> str | None:
        import grp
        import pwd

        try:
            return grp.getgrgid(pwd.getpwnam(user).pw_gid).gr_name
        except KeyError:
            return None

    def group_exists(self, group: str) -> bool:
        import grp

        try:
            grp.getgrnam(group)
            return True
        except KeyError:
            return False

    def create_group(self, group: str) -> None:
        self._run(["groupadd", "--system", group])

    def create_user(self, user: str, group: str, home: Path, shell: str) -> None:
        self._run(["useradd", "--system", "--gid", group, "--home-dir", str(home), "--no-create-home", "--shell", shell, user])

    def chown(self, path: Path, user: str, group: str) -> None:
        shutil.chown(path, user=user, group=group)

    def python_executable(self) -> str:
        return sys.executable

    def service_active(self, name: str) -> bool:
        if shutil.which("systemctl") is None:
            return False
        try:
            result = subprocess.run(["systemctl", "is-active", name], capture_output=True, text=True, timeout=5)
        except (OSError, subprocess.SubprocessError):
            return False
        return result.stdout.strip() == "active"

    def process_command_lines(self) -> list[str]:
        if shutil.which("ps") is None:
            return []
        try:
            result = subprocess.run(["ps", "-eo", "args="], capture_output=True, text=True, timeout=5)
        except (OSError, subprocess.SubprocessError):
            return []
        return [line.strip() for line in result.stdout.splitlines() if line.strip()] if result.returncode == 0 else []

    @staticmethod
    def _run(command: list[str]) -> None:
        try:
            result = subprocess.run(command, capture_output=True, text=True)
        except FileNotFoundError:
            raise SystemCommandError(f"コマンドが見つかりません: {command[0]}")
        if result.returncode != 0:
            raise SystemCommandError(f"コマンドが失敗しました: {' '.join(command)}\n  {result.stderr.strip()}")


@dataclass
class SystemContext:
    """CLIが操作する、システムの場所とOSの操作。本番は既定値(/opt/capass、/etc/systemd/system、LinuxSystemOps)。テストでは、差し替える。"""

    paths: AppPaths = field(default_factory=AppPaths)
    systemd_dir: Path = SYSTEMD_UNIT_DIR
    ops: SystemOps = field(default_factory=LinuxSystemOps)

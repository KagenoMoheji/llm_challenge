import os
import inspect
import sys
import time
import traceback
PYPATH = os.path.dirname(os.path.abspath(inspect.getfile(inspect.currentframe())))
MODNAME = os.path.splitext(os.path.basename(inspect.getfile(inspect.currentframe())))[0]

# その他のモジュールやROOTPATHのディレクトリ起点の相対パスでのimport
from pathlib import Path
from capass_core.paths import AppPaths
from capass_core.system import SystemContext, SystemOps


class FakeSystemOps(SystemOps):
    """OSの操作の代わり(実際には、ユーザの作成もchownもしない)。呼ばれた操作を記録する。各パッケージのテストで使う。"""

    def __init__(self, root: bool = True, users: dict[str, str] | None = None, groups: set[str] | None = None) -> None:
        self.root = root
        self.users = dict(users or {})  # ユーザ名 → 主グループ名
        self.groups = set(groups or set())
        self.calls: list[tuple] = []
        self.chowns: dict[str, tuple[str, str]] = {}  # パス → (ユーザ, グループ)

    def is_root(self) -> bool:
        return self.root

    def user_group(self, user: str) -> str | None:
        return self.users.get(user)

    def group_exists(self, group: str) -> bool:
        return group in self.groups

    def create_group(self, group: str) -> None:
        self.groups.add(group)
        self.calls.append(("create_group", group))

    def create_user(self, user: str, group: str, home: Path, shell: str) -> None:
        self.users[user] = group
        self.calls.append(("create_user", user, group, str(home), shell))

    def chown(self, path: Path, user: str, group: str) -> None:
        self.chowns[str(path)] = (user, group)

    def python_executable(self) -> str:
        return "/usr/bin/python3"


def make_context(tmp_path: Path, ops: FakeSystemOps | None = None, with_systemd_dir: bool = True) -> SystemContext:
    """tmp_pathの下に、アプリディレクトリとsystemdのディレクトリを置いた、テスト用のシステム。"""
    systemd_dir = tmp_path / "systemd"
    if with_systemd_dir:
        systemd_dir.mkdir()
    return SystemContext(paths=AppPaths(root=tmp_path / "opt" / "capass"), systemd_dir=systemd_dir, ops=ops or FakeSystemOps())

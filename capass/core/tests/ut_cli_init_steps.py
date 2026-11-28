import os
import inspect
import sys
import time
import traceback
PYPATH = os.path.dirname(os.path.abspath(inspect.getfile(inspect.currentframe())))
# 以下のROOTPATHでimportの起点を指定
ROOTPATH = os.path.abspath(f"{PYPATH}/..")
MODNAME = os.path.splitext(os.path.basename(inspect.getfile(inspect.currentframe())))[0]
sys.path.append(ROOTPATH)

# その他のモジュールやROOTPATHのディレクトリ起点の相対パスでのimport
import os
import stat
import pytest
from pathlib import Path
from capass_core.cli.common.errors import AlreadyInitializedError, AppDirectoryError, NotRootError, UnsupportedEnvironmentError
from capass_core.cli.common.init_steps import (
    check_not_initialized,
    check_root,
    check_systemd_dir,
    check_unit_file_is_ours,
    create_app_dirs,
    ensure_service_user,
    make_dir,
    render_wrapper,
    write_file,
    write_wrapper,
)
from capass_core.cli.common.systemd import UNIT_MARKER
from capass_core.cli.common.testing import FakeSystemOps, make_context


def _mode(path: Path) -> int:
    return stat.S_IMODE(path.stat().st_mode)


def test_check_root(tmp_path):
    check_root(make_context(tmp_path, FakeSystemOps(root=True)))
    other = tmp_path / "not-root"
    other.mkdir()
    with pytest.raises(NotRootError) as e:
        check_root(make_context(other, FakeSystemOps(root=False)))
    assert e.value.exit_code == 6


def test_check_systemd_dir(tmp_path):
    check_systemd_dir(make_context(tmp_path))
    without_systemd = tmp_path / "without-systemd"
    without_systemd.mkdir()
    with pytest.raises(UnsupportedEnvironmentError):
        check_systemd_dir(make_context(without_systemd, with_systemd_dir=False))


def test_check_not_initialized(tmp_path):
    ctx = make_context(tmp_path)
    check_not_initialized(ctx.paths, "toolserver")  # 設定ファイルが、まだ無い
    ctx.paths.confs_dir.mkdir(parents=True)
    ctx.paths.conf_file.write_text("[capass]\nmode = toolserver\nversion = 1\ninitialized_at = x\n[service]\nuser = u\ngroup = g\nport = 31000\n[paths]\nlog_dir = /l\ndata_dir = /d\n", encoding="utf-8")
    with pytest.raises(AlreadyInitializedError):
        check_not_initialized(ctx.paths, "toolserver")
    check_not_initialized(ctx.paths, "agent")  # 別のモードの確認は、ensure_host_mode の仕事(ここでは、同じモードだけを見る)


def test_check_unit_file_is_ours(tmp_path):
    unit = tmp_path / "capass.service"
    check_unit_file_is_ours(unit)  # 無ければ、問題ない
    unit.write_text(UNIT_MARKER + "\n[Unit]\n", encoding="utf-8")
    check_unit_file_is_ours(unit)  # capass init が作ったものは、上書きしてよい
    unit.write_text("[Unit]\nDescription=other\n", encoding="utf-8")
    with pytest.raises(AppDirectoryError):
        check_unit_file_is_ours(unit)


def test_ensure_service_user_creates_group_and_user(tmp_path):
    ops = FakeSystemOps()
    ctx = make_context(tmp_path, ops)
    assert ensure_service_user(ctx, "capass") == ("capass", True)
    assert ops.calls == [("create_group", "capass"), ("create_user", "capass", "capass", str(ctx.paths.root), "/sbin/nologin")]


def test_ensure_service_user_reuses_existing_user_and_group(tmp_path):
    ops = FakeSystemOps(users={"svc": "svcgrp"}, groups={"svcgrp"})
    assert ensure_service_user(make_context(tmp_path, ops), "svc") == ("svcgrp", False)
    assert ops.calls == []
    ops2 = FakeSystemOps(groups={"capass"})  # グループだけ存在する場合は、グループを作らない
    other = tmp_path / "other"
    other.mkdir()
    assert ensure_service_user(make_context(other, ops2), "capass") == ("capass", True)
    assert [c[0] for c in ops2.calls] == ["create_user"]


def test_make_dir_and_write_file_set_permissions_and_owner(tmp_path):
    ops = FakeSystemOps()
    ctx = make_context(tmp_path, ops)
    directory, file = tmp_path / "a" / "b", tmp_path / "a" / "b" / "f.txt"
    make_dir(ctx, directory, 0o750, "svc", "svcgrp")
    write_file(ctx, file, "x", 0o640, "svc", "svcgrp")
    assert ops.chowns[str(directory)] == ("svc", "svcgrp") and ops.chowns[str(file)] == ("svc", "svcgrp")
    if os.name != "nt":
        assert _mode(directory) == 0o750 and _mode(file) == 0o640


def test_create_app_dirs_with_and_without_log_and_data(tmp_path):
    ops = FakeSystemOps()
    ctx = make_context(tmp_path, ops)
    create_app_dirs(ctx, "capass", "capass", tmp_path / "log", tmp_path / "data")
    p = ctx.paths
    assert all(d.is_dir() for d in (p.root, p.bin_dir, p.confs_dir, p.keys_dir, tmp_path / "log", tmp_path / "data"))
    assert ops.chowns[str(p.bin_dir)] == ("root", "root") and ops.chowns[str(p.keys_dir)] == ("capass", "capass")  # 実行ファイルと設定は、rootの持ち物
    if os.name != "nt":
        assert _mode(p.keys_dir) == 0o700 and _mode(tmp_path / "log") == 0o750 and _mode(tmp_path / "data") == 0o700
    second = tmp_path / "second"
    second.mkdir()
    ctx2 = make_context(second, FakeSystemOps())
    create_app_dirs(ctx2, "capass", "capass")  # ログとデータを持たないモード(AIエージェントなど)
    assert ctx2.paths.keys_dir.is_dir() and not ctx2.paths.default_log_dir.exists() and not ctx2.paths.default_data_dir.exists()


def test_write_wrapper_is_a_root_owned_executable_script(tmp_path):
    ops = FakeSystemOps()
    ctx = make_context(tmp_path, ops)
    create_app_dirs(ctx, "capass", "capass")
    path = write_wrapper(ctx)
    assert path == ctx.paths.wrapper and ops.chowns[str(path)] == ("root", "root")
    script = path.read_text(encoding="utf-8")
    assert script == render_wrapper("/usr/bin/python3")
    assert script.startswith("#!/bin/sh") and "exec /usr/bin/python3 -m capass_core.cli.main" in script and '"$@"' in script
    if os.name != "nt":
        assert _mode(path) == 0o755

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
from capass_core.cli.common.conf import read_conf
from capass_core.cli.common.errors import AlreadyInitializedError
from capass_core.cli.main import main
from capass_core.cli.common.testing import FakeSystemOps, make_context


def _only_toolserver(name):
    return object() if name == "capass_toolserver" else None


def _init(ctx, *extra: str) -> int:
    return main(["init", *extra], context=ctx, find_spec=_only_toolserver)  # CLIは、本物(capass_toolserver.cli)を読み込む


def _mode(path: Path) -> int:
    return stat.S_IMODE(path.stat().st_mode)


def test_init_creates_everything_and_prints_public_info_only(tmp_path, capsys):
    ctx = make_context(tmp_path)
    assert _init(ctx) == 0
    paths, out = ctx.paths, capsys.readouterr().out
    for directory in (paths.root, paths.bin_dir, paths.confs_dir, paths.keys_dir, paths.default_log_dir, paths.default_data_dir):
        assert directory.is_dir(), directory
    assert paths.wrapper.is_file() and paths.conf_file.is_file() and paths.private_key_path("toolserver").is_file()
    assert (ctx.systemd_dir / "capass.service").is_file()

    private_text = paths.private_key_path("toolserver").read_text(encoding="utf-8").strip()
    public_text = paths.public_key_path("toolserver").read_text(encoding="utf-8").strip()
    assert public_text in out and "SHA256:" in out  # 公開鍵とフィンガープリントを表示する
    assert private_text not in out  # 秘密鍵は、表示しない
    assert "systemctl daemon-reload" in out and "31000" in out  # 次の手順と、ポート


def test_init_creates_the_service_user_and_group_with_defaults(tmp_path):
    ops = FakeSystemOps()
    ctx = make_context(tmp_path, ops)
    assert _init(ctx) == 0
    assert ops.calls == [("create_group", "capass"), ("create_user", "capass", "capass", str(ctx.paths.root), "/sbin/nologin")]  # ログインできないシステムユーザ


def test_init_uses_an_existing_user_and_group(tmp_path, capsys):
    ops = FakeSystemOps(users={"capass": "capass-grp"}, groups={"capass-grp"})
    ctx = make_context(tmp_path, ops)
    assert _init(ctx) == 0
    assert ops.calls == []  # 作らない
    assert ops.chowns[str(ctx.paths.keys_dir)] == ("capass", "capass-grp")  # 既存の主グループを使う
    assert "既存のユーザを使います" in capsys.readouterr().out


def test_init_reuses_an_existing_group_without_creating_it(tmp_path):
    ops = FakeSystemOps(groups={"capass"})
    ctx = make_context(tmp_path, ops)
    assert _init(ctx) == 0
    assert [c[0] for c in ops.calls] == ["create_user"]


def test_init_writes_conf_with_version_and_settings(tmp_path):
    ctx = make_context(tmp_path)
    assert _init(ctx, "--user", "svc", "--port", "32000", "--log-dir", str(tmp_path / "log"), "--data-dir", str(tmp_path / "data")) == 0
    conf = read_conf(ctx.paths.conf_file)
    assert (conf.mode, conf.user, conf.group, conf.port) == ("toolserver", "svc", "svc", 32000)
    assert (conf.log_dir, conf.data_dir) == (str(tmp_path / "log"), str(tmp_path / "data"))
    from capass_core import __version__
    assert conf.version == __version__
    assert (tmp_path / "log").is_dir() and (tmp_path / "data").is_dir()  # アプリディレクトリの外にも、作る


def test_init_unit_file_matches_the_options(tmp_path):
    ctx = make_context(tmp_path)
    assert _init(ctx, "--user", "svc", "--log-dir", str(tmp_path / "log"), "--data-dir", str(tmp_path / "data")) == 0
    unit = (ctx.systemd_dir / "capass.service").read_text(encoding="utf-8")
    assert "User=svc" in unit and f"ReadWritePaths={tmp_path / 'log'} {tmp_path / 'data'}" in unit
    assert f"ExecStart={ctx.paths.wrapper} serve" in unit


def test_init_wrapper_runs_the_installed_python_module(tmp_path):
    ctx = make_context(tmp_path)
    assert _init(ctx) == 0
    script = ctx.paths.wrapper.read_text(encoding="utf-8")
    assert script.startswith("#!/bin/sh") and "exec /usr/bin/python3 -m capass_core.cli.main" in script and '"$@"' in script


def test_init_permissions_and_ownership(tmp_path):
    ops = FakeSystemOps()
    ctx = make_context(tmp_path, ops)
    assert _init(ctx) == 0
    p = ctx.paths
    if os.name != "nt":
        assert [_mode(x) for x in (p.root, p.bin_dir, p.confs_dir)] == [0o755, 0o755, 0o755]
        assert _mode(p.keys_dir) == 0o700 and _mode(p.default_data_dir) == 0o700 and _mode(p.default_log_dir) == 0o750
        assert _mode(p.private_key_path("toolserver")) == 0o600 and _mode(p.public_key_path("toolserver")) == 0o644
        assert _mode(p.wrapper) == 0o755 and _mode(p.conf_file) == 0o644 and _mode(ctx.systemd_dir / "capass.service") == 0o644
    owners = ops.chowns
    for root_owned in (p.root, p.bin_dir, p.confs_dir, p.wrapper, p.conf_file, ctx.systemd_dir / "capass.service"):
        assert owners[str(root_owned)] == ("root", "root"), root_owned  # 実行ファイルと設定は、実行ユーザが書き換えられない
    for service_owned in (p.keys_dir, p.default_log_dir, p.default_data_dir, p.private_key_path("toolserver"), p.public_key_path("toolserver")):
        assert owners[str(service_owned)] == ("capass", "capass"), service_owned


def test_init_is_refused_without_root_and_changes_nothing(tmp_path, capsys):
    ctx = make_context(tmp_path, FakeSystemOps(root=False))
    assert _init(ctx) == 6
    assert "root" in capsys.readouterr().err
    assert not ctx.paths.root.exists() and list(ctx.systemd_dir.iterdir()) == []


def test_init_is_refused_without_systemd_directory(tmp_path):
    ctx = make_context(tmp_path, with_systemd_dir=False)
    assert _init(ctx) == 7
    assert not ctx.paths.root.exists()


def test_init_twice_is_an_error_and_keeps_the_keys(tmp_path, capsys):
    ctx = make_context(tmp_path)
    assert _init(ctx) == 0
    key_file = ctx.paths.private_key_path("toolserver")
    before = key_file.read_text(encoding="utf-8")
    capsys.readouterr()
    assert _init(ctx) == 4
    assert "すでに初期化" in capsys.readouterr().err
    assert key_file.read_text(encoding="utf-8") == before


def test_init_is_refused_on_a_server_set_up_as_an_agent(tmp_path, capsys):
    ctx = make_context(tmp_path)
    ctx.paths.keys_dir.mkdir(parents=True)
    ctx.paths.private_key_path("agent").write_text("x\n", encoding="utf-8")  # AIエージェントの鍵が、すでにある
    assert _init(ctx) == 3  # モードの同居
    err = capsys.readouterr().err
    assert "AIエージェント" in err and "同居" in err
    assert not ctx.paths.conf_file.exists() and not ctx.paths.bin_dir.exists() and list(ctx.systemd_dir.iterdir()) == []  # 何も作らない
    assert ctx.ops.calls == []  # ユーザも作らない


def test_init_is_refused_when_the_conf_says_another_mode(tmp_path):
    ctx = make_context(tmp_path)
    ctx.paths.confs_dir.mkdir(parents=True)
    ctx.paths.conf_file.write_text("[capass]\nmode = server\nversion = 0.1.6\ninitialized_at = x\n[service]\nuser = u\ngroup = g\nport = 31000\n[paths]\nlog_dir = /l\ndata_dir = /d\n", encoding="utf-8")
    assert _init(ctx) == 3
    assert ctx.ops.calls == []


def test_init_can_be_rerun_after_an_interrupted_run_and_keeps_the_keys(tmp_path):
    ctx = make_context(tmp_path)
    assert _init(ctx) == 0
    first_public = ctx.paths.public_key_path("toolserver").read_text(encoding="utf-8")
    ctx.paths.conf_file.unlink()  # 初期化が途中で止まった状態(設定ファイルが、まだ無い)
    assert _init(ctx) == 0
    assert ctx.paths.public_key_path("toolserver").read_text(encoding="utf-8") == first_public  # 鍵は、作り直さない


def test_init_does_not_overwrite_an_unrelated_service_file(tmp_path, capsys):
    ctx = make_context(tmp_path)
    unit = ctx.systemd_dir / "capass.service"
    unit.write_text("[Unit]\nDescription=something else\n", encoding="utf-8")
    assert _init(ctx) == 5
    assert unit.read_text(encoding="utf-8") == "[Unit]\nDescription=something else\n"
    assert not ctx.paths.root.exists()  # 確認の段階で止まる


def test_init_overwrites_its_own_service_file_when_rerunning(tmp_path):
    ctx = make_context(tmp_path)
    assert _init(ctx) == 0
    ctx.paths.conf_file.unlink()
    assert _init(ctx, "--user", "other") == 0  # capass init が作ったサービスファイルは、更新してよい
    assert "User=other" in (ctx.systemd_dir / "capass.service").read_text(encoding="utf-8")


def test_init_invalid_options_exit_with_2_and_change_nothing(tmp_path):
    ctx = make_context(tmp_path)
    for extra in (("--port", "80"), ("--port", "70000"), ("--user", "root"), ("--log-dir", "relative"), ("--data-dir", str(ctx.paths.root))):
        assert _init(ctx, *extra) == 2, extra
    assert not ctx.paths.root.exists() and ctx.ops.calls == []
    with pytest.raises(SystemExit) as e:
        _init(ctx, "--port", "abc")  # 数値ではない(argparseの使い方の誤り)
    assert e.value.code == 2


def test_already_initialized_error_has_exit_code_4():
    assert AlreadyInitializedError("x").exit_code == 4


def test_init_is_refused_when_a_process_of_another_mode_is_running(tmp_path, capsys):
    ops = FakeSystemOps()
    ops.processes = ["/venv/bin/python /venv/bin/uvicorn capass_server.daemon.main:app --port 8000"]
    ctx = make_context(tmp_path, ops)
    assert _init(ctx) == 3
    assert "CaPassサーバ" in capsys.readouterr().err
    assert not ctx.paths.root.exists() and ctx.ops.calls == []  # 何も作らない


def test_init_is_refused_when_the_service_of_another_mode_is_active(tmp_path):
    ops = FakeSystemOps()
    ctx = make_context(tmp_path, ops)
    ctx.paths.confs_dir.mkdir(parents=True)
    ctx.paths.conf_file.write_text("[capass]\nmode = agent\nversion = 0.1.6\ninitialized_at = x\n[service]\nuser = u\ngroup = g\nport = 31000\n[paths]\nlog_dir = /l\ndata_dir = /d\n", encoding="utf-8")
    ops.active_services.add("capass.service")
    assert _init(ctx) == 3
    assert ops.calls == []


def test_toolserver_init_describes_the_receiver_service():
    from capass_toolserver.cli.commands.init import UNIT_DESCRIPTION, UNIT_EXEC_ARGS

    assert "tool server" in UNIT_DESCRIPTION and UNIT_EXEC_ARGS == "serve"


def test_init_help_names_the_mode(tmp_path, capsys):
    ctx = make_context(tmp_path)
    with pytest.raises(SystemExit) as e:
        _init(ctx, "--help")
    assert e.value.code == 0
    out = capsys.readouterr().out
    for text in ("ツールサーバ", "--user", "--log-dir", "--data-dir", "--port", "31000", "/opt/capass", "capass.service", "同居"):
        assert text in out, text


def test_help_lists_init_as_a_toolserver_command(tmp_path, capsys):
    with pytest.raises(SystemExit):
        main(["--help"], context=make_context(tmp_path), find_spec=_only_toolserver)
    out = capsys.readouterr().out
    assert "init" in out and "[モード: toolserver]" in out and "インストール済みのモード: toolserver" in out


def test_init_output_mentions_the_receiver_that_is_not_implemented_yet(tmp_path, capsys):
    assert _init(make_context(tmp_path), "--port", "32000") == 0
    out = capsys.readouterr().out
    assert "受け口(capass serve)" in out and "32000" in out


def test_daemon_package_exists_but_is_not_implemented_yet():
    import capass_toolserver.daemon as daemon

    assert daemon.__doc__ and "まだ実装していない" in daemon.__doc__

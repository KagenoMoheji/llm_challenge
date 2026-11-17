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
import pytest
from capass_core.cli.main import main
from capass_core.testing import FakeSystemOps, make_context
from capass_toolserver.cli import INIT_SPEC


def _only_toolserver(name):
    return object() if name == "capass_toolserver" else None


def test_init_spec_describes_the_receiver_service():
    assert INIT_SPEC.mode == "toolserver" and INIT_SPEC.exec_args == "serve" and "tool server" in INIT_SPEC.unit_description


def test_capass_init_with_the_real_toolserver_cli(tmp_path, capsys):
    ctx = make_context(tmp_path, FakeSystemOps())
    assert main(["init", "--port", "32000"], context=ctx, find_spec=_only_toolserver) == 0  # CLIは、本物(capass_toolserver.cli)を読み込む
    out = capsys.readouterr().out
    assert "ツールサーバの初期導入が完了しました" in out and "受け口(capass serve)" in out
    unit = (ctx.systemd_dir / "capass.service").read_text(encoding="utf-8")
    assert "Description=CaPass tool server receiver" in unit and f"ExecStart={ctx.paths.wrapper} serve" in unit
    assert "mode = toolserver" in ctx.paths.conf_file.read_text(encoding="utf-8") and "port = 32000" in ctx.paths.conf_file.read_text(encoding="utf-8")
    assert ctx.paths.private_key_path("toolserver").is_file()


def test_init_help_names_the_mode(tmp_path, capsys):
    with pytest.raises(SystemExit) as e:
        main(["init", "--help"], context=make_context(tmp_path), find_spec=_only_toolserver)
    assert e.value.code == 0
    out = capsys.readouterr().out
    assert "ツールサーバ" in out and "--user" in out and "--port" in out and "/opt/capass" in out


def test_help_lists_init_as_a_toolserver_command(tmp_path, capsys):
    with pytest.raises(SystemExit):
        main(["--help"], context=make_context(tmp_path), find_spec=_only_toolserver)
    out = capsys.readouterr().out
    assert "init" in out and "[モード: toolserver]" in out and "インストール済みのモード: toolserver" in out


def test_init_is_refused_on_a_server_that_is_set_up_as_an_agent(tmp_path, capsys):
    ctx = make_context(tmp_path)
    ctx.paths.keys_dir.mkdir(parents=True)
    ctx.paths.private_key_path("agent").write_text("x\n", encoding="utf-8")  # 別のPython環境で、AIエージェントとして設定済み
    assert main(["init"], context=ctx, find_spec=_only_toolserver) == 3  # Python環境が違っても、サーバ全体で、同居を防ぐ
    assert not ctx.paths.conf_file.exists() and ctx.ops.calls == []
    assert "同居" in capsys.readouterr().err


def test_daemon_package_exists_but_is_not_implemented_yet():
    import capass_toolserver.daemon as daemon

    assert daemon.__doc__ and "まだ実装していない" in daemon.__doc__

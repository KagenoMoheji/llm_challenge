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
from types import SimpleNamespace
from capass_core import __version__
from capass_core.cli.main import load_mode_cli, main
from capass_core.cli.common.testing import FakeSystemOps, make_context


def _finder(*packages):
    return lambda name: object() if name in packages else None


def _fake_cli(calls):
    """モードのCLIの代わり: hello というコマンドを登録する。"""

    def register(subparsers, context):
        parser = subparsers.add_parser("hello", help="テスト用のコマンド [モード: toolserver]")
        parser.set_defaults(func=lambda args: calls.append(args.context) or 0)

    return SimpleNamespace(register=register)


def test_commands_of_the_installed_mode_are_registered_and_receive_the_context(tmp_path):
    ctx, calls = make_context(tmp_path), []
    assert main(["hello"], context=ctx, find_spec=_finder("capass_toolserver"), load_cli=lambda mode: _fake_cli(calls)) == 0
    assert calls == [ctx]


def test_mode_cli_is_loaded_lazily_only_for_the_selected_mode(tmp_path):
    loaded = []

    def load_cli(mode):
        loaded.append(mode)
        return _fake_cli([])

    assert main(["hello"], context=make_context(tmp_path), find_spec=_finder("capass_toolserver"), load_cli=load_cli) == 0
    assert loaded == ["toolserver"]  # 他のモードのCLIは、読み込まない


def test_without_any_mode_installed_commands_fail_with_10_and_the_install_hint(tmp_path, capsys):
    assert main(["init"], context=make_context(tmp_path), find_spec=_finder()) == 10
    err = capsys.readouterr().err
    assert "エラー" in err and 'pip install "capass[toolserver]"' in err


def test_with_two_modes_installed_commands_fail_with_11(tmp_path, capsys):
    loaded = []
    code = main(["init"], context=make_context(tmp_path), find_spec=_finder("capass_agent", "capass_toolserver"), load_cli=lambda m: loaded.append(m))
    assert code == 11
    assert "agent, toolserver" in capsys.readouterr().err and loaded == []  # どのモードのCLIも、読み込まない


def test_a_mode_without_cli_commands_fails_with_9(tmp_path, capsys):
    ctx = make_context(tmp_path)
    for mode in ("agent", "server"):
        assert main(["init"], context=ctx, find_spec=_finder(f"capass_{mode}"), load_cli=lambda m: None) == 9
        assert "実装されていません" in capsys.readouterr().err
    # CLIのパッケージはあるが、registerが無い場合も、同じ
    assert main(["init"], context=ctx, find_spec=_finder("capass_agent"), load_cli=lambda m: SimpleNamespace()) == 9


def test_help_shows_modes_installed_modes_and_host_mode(tmp_path, capsys):
    ctx = make_context(tmp_path)
    with pytest.raises(SystemExit) as e:
        main(["--help"], context=ctx, find_spec=_finder("capass_toolserver"), load_cli=lambda m: _fake_cli([]))
    assert e.value.code == 0
    out = capsys.readouterr().out
    for mode in ("toolserver", "agent", "server"):
        assert f'pip install "capass[{mode}]"' in out  # どのモードが、あるか
    assert "インストール済みのモード: toolserver" in out
    assert "このサーバのモード(初期化済み): 未初期化" in out
    assert "hello" in out and "[モード: toolserver]" in out  # コマンドが、どのモードのものか分かる


def test_help_works_even_without_a_mode_or_with_two_modes(tmp_path, capsys):
    ctx = make_context(tmp_path)
    for installed, expected in (((), "インストール済みのモード: なし"), (("capass_agent", "capass_server"), "agent, server(同時に使えません)")):
        with pytest.raises(SystemExit) as e:
            main(["--help"], context=ctx, find_spec=_finder(*installed))
        assert e.value.code == 0
        assert expected in capsys.readouterr().out


def test_version_option(tmp_path, capsys):
    with pytest.raises(SystemExit) as e:
        main(["--version"], context=make_context(tmp_path), find_spec=_finder())
    assert e.value.code == 0
    assert __version__ in capsys.readouterr().out


def test_usage_errors_exit_with_2(tmp_path):
    ctx = make_context(tmp_path)
    for argv in ([], ["no-such-command"]):
        with pytest.raises(SystemExit) as e:
            main(argv, context=ctx, find_spec=_finder("capass_toolserver"), load_cli=lambda m: _fake_cli([]))
        assert e.value.code == 2, argv


def test_load_mode_cli_returns_none_when_the_mode_package_has_no_cli(tmp_path):
    import sys

    package = tmp_path / "capass_nocli"  # CLIの無いモードのパッケージ(例: いまの capass_server)
    package.mkdir()
    (package / "__init__.py").write_text("", encoding="utf-8")
    sys.path.insert(0, str(tmp_path))
    try:
        assert load_mode_cli("nocli") is None  # capass_nocli.cli が無い
    finally:
        sys.path.remove(str(tmp_path))
        sys.modules.pop("capass_nocli", None)


def test_load_mode_cli_does_not_hide_import_errors_inside_the_cli(tmp_path):
    import sys

    package = tmp_path / "capass_brokencli"
    (package / "cli").mkdir(parents=True)
    (package / "__init__.py").write_text("", encoding="utf-8")
    (package / "cli" / "__init__.py").write_text("import no_such_dependency_xyz\n", encoding="utf-8")  # CLIの中の、依存の不足
    sys.path.insert(0, str(tmp_path))
    try:
        with pytest.raises(ModuleNotFoundError) as e:
            load_mode_cli("brokencli")
        assert e.value.name == "no_such_dependency_xyz"  # 「CLIが無い」と取り違えない
    finally:
        sys.path.remove(str(tmp_path))
        for name in ("capass_brokencli", "capass_brokencli.cli"):
            sys.modules.pop(name, None)


# ---------- サーバ全体の確認(別のモードの設定、鍵、稼働中のプロセス) ----------
CONF_TEXT = "[capass]\nmode = {mode}\nversion = 0.1.6\ninitialized_at = x\n[service]\nuser = u\ngroup = g\nport = 31000\n[paths]\nlog_dir = /l\ndata_dir = /d\n"


def _toolserver_only(tmp_path, ops=None):
    return make_context(tmp_path, ops), _finder("capass_toolserver")


def test_a_key_of_another_mode_on_the_server_blocks_commands_with_3(tmp_path, capsys):
    ctx, find_spec = _toolserver_only(tmp_path)
    ctx.paths.keys_dir.mkdir(parents=True)
    ctx.paths.private_key_path("agent").write_text("x\n", encoding="utf-8")  # 別のPython環境で、AIエージェントとして設定済み
    assert main(["hello"], context=ctx, find_spec=find_spec, load_cli=lambda m: _fake_cli([])) == 3
    err = capsys.readouterr().err
    assert "AIエージェント" in err and "同居" in err and str(ctx.paths.private_key_path("agent")) in err


def test_the_conf_of_another_mode_blocks_commands_with_3(tmp_path):
    ctx, find_spec = _toolserver_only(tmp_path)
    ctx.paths.confs_dir.mkdir(parents=True)
    ctx.paths.conf_file.write_text(CONF_TEXT.format(mode="server"), encoding="utf-8")
    assert main(["hello"], context=ctx, find_spec=find_spec, load_cli=lambda m: _fake_cli([])) == 3


def test_a_running_process_of_another_mode_blocks_commands_with_3(tmp_path, capsys):
    ops = FakeSystemOps()
    ops.processes = ["/venv/bin/python /venv/bin/uvicorn capass_server.daemon.main:app --port 8000"]  # capass init を使わずに起動された、サーバ
    ctx, find_spec = _toolserver_only(tmp_path, ops)
    assert main(["hello"], context=ctx, find_spec=find_spec, load_cli=lambda m: _fake_cli([])) == 3
    assert "CaPassサーバ" in capsys.readouterr().err


def test_a_running_service_of_another_mode_blocks_commands_with_3(tmp_path):
    ops = FakeSystemOps()
    ctx, find_spec = _toolserver_only(tmp_path, ops)
    ctx.paths.confs_dir.mkdir(parents=True)
    ctx.paths.conf_file.write_text(CONF_TEXT.format(mode="agent"), encoding="utf-8")
    ops.active_services.add("capass.service")  # systemd のサービスが、稼働中
    assert main(["hello"], context=ctx, find_spec=find_spec, load_cli=lambda m: _fake_cli([])) == 3


def test_the_same_mode_on_the_server_does_not_block(tmp_path):
    ops = FakeSystemOps()
    ops.processes = ["/venv/bin/python /venv/bin/capass-toolserver"]
    ctx, find_spec = _toolserver_only(tmp_path, ops)
    ctx.paths.keys_dir.mkdir(parents=True)
    ctx.paths.private_key_path("toolserver").write_text("x\n", encoding="utf-8")
    calls = []
    assert main(["hello"], context=ctx, find_spec=find_spec, load_cli=lambda m: _fake_cli(calls)) == 0
    assert calls == [ctx]


def test_help_still_works_when_the_server_check_fails(tmp_path, capsys):
    ctx, find_spec = _toolserver_only(tmp_path)
    ctx.paths.keys_dir.mkdir(parents=True)
    ctx.paths.private_key_path("agent").write_text("x\n", encoding="utf-8")
    with pytest.raises(SystemExit) as e:
        main(["--help"], context=ctx, find_spec=find_spec, load_cli=lambda m: _fake_cli([]))
    assert e.value.code == 0
    out = capsys.readouterr().out
    assert "このサーバでは、コマンドを使えません" in out and "同居" in out


def test_package_check_runs_before_the_server_check(tmp_path):
    loaded = []
    ops = FakeSystemOps()
    ops.processes = ["/venv/bin/python -m capass_server.daemon.main"]
    ctx = make_context(tmp_path, ops)
    # 2つのモードのパッケージ: パッケージの確認(11)が先。サーバの確認には、進まない
    assert main(["hello"], context=ctx, find_spec=_finder("capass_agent", "capass_toolserver"), load_cli=lambda m: loaded.append(m)) == 11
    assert main(["hello"], context=ctx, find_spec=_finder()) == 10  # モードが無い
    assert loaded == []

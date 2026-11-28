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
from capass_core.cli.common.errors import ModeNotInstalledError, MultipleModesInstalledError
from capass_core.cli.common.modes import (
    MODE_AGENT,
    MODE_SERVER,
    MODE_TOOLSERVER,
    detect_installed_modes,
    ensure_single_mode,
    install_hint,
    package_name,
)


def _finder(*installed_packages):
    """指定のパッケージだけが、インストールされている、find_specの代わり。"""
    return lambda name: object() if name in installed_packages else None


def test_package_names_follow_the_convention():
    assert [package_name(m) for m in (MODE_SERVER, MODE_TOOLSERVER, MODE_AGENT)] == ["capass_server", "capass_toolserver", "capass_agent"]
    assert install_hint(MODE_TOOLSERVER) == 'pip install "capass[toolserver]"'


def test_detect_installed_modes_by_package_presence():
    assert detect_installed_modes(_finder()) == set()
    assert detect_installed_modes(_finder("capass_toolserver")) == {MODE_TOOLSERVER}
    assert detect_installed_modes(_finder("capass_agent", "capass_server", "capass_other")) == {MODE_AGENT, MODE_SERVER}  # 関係のないパッケージは、無視する


def test_detect_installed_modes_does_not_import_the_packages(monkeypatch):
    import importlib.util
    import sys

    sys.modules.pop("capass_toolserver_never_imported", None)
    detect_installed_modes(importlib.util.find_spec)  # 本物のfind_specで、エラーにならない(インストールされていないので、空)
    assert "capass_toolserver_never_imported" not in sys.modules


def test_exactly_one_mode_is_accepted():
    for mode in (MODE_SERVER, MODE_TOOLSERVER, MODE_AGENT):
        assert ensure_single_mode({mode}) == mode


def test_no_mode_installed_tells_how_to_install():
    with pytest.raises(ModeNotInstalledError) as e:
        ensure_single_mode(set())
    message = str(e.value)
    for mode in ("toolserver", "agent", "server"):
        assert f'pip install "capass[{mode}]"' in message
    assert e.value.exit_code == 10


def test_two_or_more_modes_are_refused_and_listed():
    for installed in ({MODE_AGENT, MODE_TOOLSERVER}, {MODE_SERVER, MODE_TOOLSERVER}, {MODE_AGENT, MODE_SERVER, MODE_TOOLSERVER}):
        with pytest.raises(MultipleModesInstalledError) as e:
            ensure_single_mode(installed)
        message = str(e.value)
        assert "同時に使うことはできません" in message and "pip uninstall" in message
        for mode in installed:
            assert mode in message  # 現在のインストール状態
        assert e.value.exit_code == 11


# ---------- サーバ全体の確認(旧 roles.py。modes.py に統合) ----------
from capass_core.cli.common.errors import RoleConflictError
from capass_core.cli.common.paths import AppPaths
from capass_core.cli.common.modes import describe_current_mode, detect_role_evidence, detect_running_modes, ensure_host_mode
from capass_core.cli.common.testing import FakeSystemOps


def _paths(tmp_path):
    paths = AppPaths(root=tmp_path / "capass")
    paths.keys_dir.mkdir(parents=True)
    paths.confs_dir.mkdir(parents=True)
    return paths


def _write_conf(paths, mode):
    paths.conf_file.write_text(f"[capass]\nmode = {mode}\nversion = 0.1.6\ninitialized_at = x\n[service]\nuser = u\ngroup = g\nport = 31000\n[paths]\nlog_dir = /l\ndata_dir = /d\n", encoding="utf-8")


def test_nothing_is_set_up_on_an_empty_server(tmp_path):
    assert detect_role_evidence(AppPaths(root=tmp_path / "none")) == {}  # アプリディレクトリが、まだ無い場合も同じ
    for mode in (MODE_AGENT, MODE_TOOLSERVER, MODE_SERVER):
        ensure_host_mode(AppPaths(root=tmp_path / "none"), mode, FakeSystemOps())


def test_conf_mode_blocks_other_modes(tmp_path):
    paths = _paths(tmp_path)
    _write_conf(paths, MODE_AGENT)
    ensure_host_mode(paths, MODE_AGENT, FakeSystemOps())  # 同じモードは、問題ない
    for mode in (MODE_TOOLSERVER, MODE_SERVER):
        with pytest.raises(RoleConflictError):
            ensure_host_mode(paths, mode, FakeSystemOps())


def test_key_file_names_block_other_modes(tmp_path):
    paths = _paths(tmp_path)
    paths.public_key_path(MODE_AGENT).write_text("x\n", encoding="utf-8")  # ファイル名で、モードを区別する
    with pytest.raises(RoleConflictError):
        ensure_host_mode(paths, MODE_TOOLSERVER, FakeSystemOps())
    ensure_host_mode(paths, MODE_AGENT, FakeSystemOps())


def test_own_mode_key_files_do_not_conflict(tmp_path):
    paths = _paths(tmp_path)
    paths.private_key_path(MODE_TOOLSERVER).write_text("x\n", encoding="utf-8")  # 初期化が途中で止まった後の、再実行
    ensure_host_mode(paths, MODE_TOOLSERVER, FakeSystemOps())


def test_conflict_message_names_the_existing_mode_and_where_it_was_found(tmp_path):
    paths = _paths(tmp_path)
    paths.private_key_path(MODE_AGENT).write_text("x\n", encoding="utf-8")
    with pytest.raises(RoleConflictError) as e:
        ensure_host_mode(paths, MODE_TOOLSERVER, FakeSystemOps())
    message = str(e.value)
    assert "AIエージェント" in message and "ツールサーバ" in message  # 既存のモードと、設定しようとしたモード
    assert str(paths.private_key_path(MODE_AGENT)) in message  # 根拠(どこにあったか)
    assert "同居" in message
    assert e.value.exit_code == 3


def test_both_conf_and_key_evidence_are_reported(tmp_path):
    paths = _paths(tmp_path)
    _write_conf(paths, MODE_AGENT)
    paths.private_key_path(MODE_AGENT).write_text("x\n", encoding="utf-8")
    assert len(detect_role_evidence(paths)[MODE_AGENT]) == 2


def test_unreadable_key_directory_is_not_an_error():
    class Denied:
        def exists(self):
            raise PermissionError  # 一般ユーザは、実行ユーザの持ち物の keys/ の中を、調べられない

    from capass_core.cli.common.modes import _exists

    assert _exists(Denied()) is False  # 調べられないものは、「無い」として扱う(設定ファイルは、誰でも読めるので、そちらで検出する)


def test_describe_current_mode(tmp_path):
    paths = _paths(tmp_path)
    assert "未初期化" in describe_current_mode(paths)
    _write_conf(paths, MODE_TOOLSERVER)
    described = describe_current_mode(paths)
    assert "toolserver" in described and "初期化済み" in described
    paths.conf_file.write_text("broken", encoding="utf-8")
    assert "不明" in describe_current_mode(paths)


# ---------- 稼働中の常駐プロセス(systemd、ps) ----------
def test_running_service_is_attributed_to_the_mode_in_the_conf(tmp_path):
    paths, ops = _paths(tmp_path), FakeSystemOps()
    ops.active_services.add("capass.service")
    assert detect_running_modes(paths, ops) == {}  # 設定ファイルが無く、モードが分からないサービスは、数えない
    _write_conf(paths, MODE_AGENT)
    evidence = detect_running_modes(paths, ops)
    assert list(evidence) == [MODE_AGENT] and "稼働中" in evidence[MODE_AGENT][0]


def test_a_running_service_of_another_mode_blocks(tmp_path):
    paths, ops = _paths(tmp_path), FakeSystemOps()
    _write_conf(paths, MODE_SERVER)
    ops.active_services.add("capass.service")
    with pytest.raises(RoleConflictError) as e:
        ensure_host_mode(paths, MODE_TOOLSERVER, ops)
    assert "稼働中" in str(e.value)
    ensure_host_mode(paths, MODE_SERVER, ops)  # 同じモードのサービスは、問題ない


def test_processes_are_recognized_by_how_a_mode_is_started(tmp_path):
    paths, ops = _paths(tmp_path), FakeSystemOps()
    ops.processes = [
        "/usr/bin/python3 -m capass_server.daemon.main",  # python -m
        "/venv/bin/python /venv/bin/uvicorn capass_server.daemon.main:app --port 8000",  # uvicorn
        "/venv/bin/python /venv/bin/capass-toolserver",  # コンソールスクリプト
    ]
    evidence = detect_running_modes(paths, ops)
    assert set(evidence) == {MODE_SERVER, MODE_TOOLSERVER} and len(evidence[MODE_SERVER]) == 2
    with pytest.raises(RoleConflictError):
        ensure_host_mode(paths, MODE_AGENT, ops)


def test_unrelated_processes_are_not_mistaken_for_a_running_mode(tmp_path):
    paths, ops = _paths(tmp_path), FakeSystemOps()
    ops.processes = [
        "vim capass_server/daemon/main.py",  # エディタ
        "grep -r capass_toolserver .",
        "/usr/bin/python3 -m pytest server/tests",
        "/opt/capass/bin/capass init",
        "/usr/bin/python3 -m capass_core.cli.main serve",  # capass 自身(モードは、設定ファイルで分かる)
        "/usr/sbin/sshd -D",
        # シェルの -c: 長い文字列の中に、起動の形が含まれていても、シェル自体は、常駐プロセスではない(実際のプロセスは、別の行に出る)
        "/bin/sh -c cd /work; echo uvicorn capass_server.daemon.main:app --port 8000; sleep 1",
        "bash -c python -m capass_toolserver.daemon",
        "docker run --rm capass_server:latest",
        "/usr/bin/python3 /opt/tools/restart.py capass_server",  # 引数に、名前があるだけ
    ]
    assert detect_running_modes(paths, ops) == {}
    ensure_host_mode(paths, MODE_AGENT, ops)


def test_same_mode_process_is_not_a_conflict(tmp_path):
    ops = FakeSystemOps()
    ops.processes = ["/venv/bin/python /venv/bin/uvicorn capass_server.daemon.main:app"]
    ensure_host_mode(_paths(tmp_path), MODE_SERVER, ops)


def test_process_forms_are_recognized_with_various_interpreters_and_servers(tmp_path):
    paths, ops = _paths(tmp_path), FakeSystemOps()
    ops.processes = [
        "python3.12 -m capass_server",  # モジュールそのもの
        "/usr/local/bin/uvicorn capass_toolserver.daemon.app:app",  # uvicornが、直接
        "gunicorn -w 2 -k uvicorn.workers.UvicornWorker capass_agent.daemon.app:app",
        "/venv/bin/capass-server",  # コンソールスクリプト
    ]
    assert set(detect_running_modes(paths, ops)) == {MODE_SERVER, MODE_TOOLSERVER, MODE_AGENT}

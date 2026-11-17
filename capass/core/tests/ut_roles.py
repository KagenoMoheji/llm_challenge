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
from capass_core.errors import RoleConflictError
from capass_core.paths import AppPaths
from capass_core.modes import MODE_AGENT, MODE_SERVER, MODE_TOOLSERVER
from capass_core.roles import describe_current_mode, detect_role_evidence, ensure_role_available


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
        ensure_role_available(AppPaths(root=tmp_path / "none"), mode)


def test_conf_mode_blocks_other_modes(tmp_path):
    paths = _paths(tmp_path)
    _write_conf(paths, MODE_AGENT)
    ensure_role_available(paths, MODE_AGENT)  # 同じモードは、問題ない
    for mode in (MODE_TOOLSERVER, MODE_SERVER):
        with pytest.raises(RoleConflictError):
            ensure_role_available(paths, mode)


def test_key_file_names_block_other_modes(tmp_path):
    paths = _paths(tmp_path)
    paths.public_key_path(MODE_AGENT).write_text("x\n", encoding="utf-8")  # ファイル名で、モードを区別する
    with pytest.raises(RoleConflictError):
        ensure_role_available(paths, MODE_TOOLSERVER)
    ensure_role_available(paths, MODE_AGENT)


def test_own_mode_key_files_do_not_conflict(tmp_path):
    paths = _paths(tmp_path)
    paths.private_key_path(MODE_TOOLSERVER).write_text("x\n", encoding="utf-8")  # 初期化が途中で止まった後の、再実行
    ensure_role_available(paths, MODE_TOOLSERVER)


def test_conflict_message_names_the_existing_mode_and_where_it_was_found(tmp_path):
    paths = _paths(tmp_path)
    paths.private_key_path(MODE_AGENT).write_text("x\n", encoding="utf-8")
    with pytest.raises(RoleConflictError) as e:
        ensure_role_available(paths, MODE_TOOLSERVER)
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


def test_describe_current_mode(tmp_path):
    paths = _paths(tmp_path)
    assert "未初期化" in describe_current_mode(paths)
    _write_conf(paths, MODE_TOOLSERVER)
    described = describe_current_mode(paths)
    assert "toolserver" in described and "初期化済み" in described
    paths.conf_file.write_text("broken", encoding="utf-8")
    assert "不明" in describe_current_mode(paths)

import os
import inspect
import sys
import time
import traceback
PYPATH = os.path.dirname(os.path.abspath(inspect.getfile(inspect.currentframe())))
ROOTPATH = os.path.abspath(f"{PYPATH}/..")
MODNAME = os.path.splitext(os.path.basename(inspect.getfile(inspect.currentframe())))[0]
# 以下のROOTPATHでimportの起点を指定
sys.path.append(ROOTPATH)

# その他のモジュールやROOTPATHのディレクトリ起点の相対パスでのimport
import pytest
from capass_cli.common.errors import RoleConflictError
from capass_cli.common.roles import (
    ROLE_AGENT,
    ROLE_SERVER,
    ROLE_TOOLSERVER,
    detect_role_evidence,
    ensure_role_available,
    write_role_marker,
)


def test_empty_home_has_no_roles_and_any_role_is_available(tmp_path):
    assert detect_role_evidence(tmp_path / "none") == {}  # ホームが、まだ無い場合も同じ
    for role in (ROLE_AGENT, ROLE_TOOLSERVER, ROLE_SERVER):
        ensure_role_available(tmp_path, role)


def test_role_directory_blocks_other_roles(tmp_path):
    (tmp_path / "agent").mkdir()
    ensure_role_available(tmp_path, ROLE_AGENT)  # 同じ役割は、問題ない
    for role in (ROLE_TOOLSERVER, ROLE_SERVER):
        with pytest.raises(RoleConflictError):
            ensure_role_available(tmp_path, role)


def test_role_marker_blocks_other_roles(tmp_path):
    write_role_marker(tmp_path, ROLE_TOOLSERVER)
    ensure_role_available(tmp_path, ROLE_TOOLSERVER)
    for role in (ROLE_AGENT, ROLE_SERVER):
        with pytest.raises(RoleConflictError):
            ensure_role_available(tmp_path, role)


def test_unknown_marker_is_treated_as_a_conflicting_role(tmp_path):
    (tmp_path / "role").write_text("something-else\n", encoding="utf-8")  # 手で書き換えられた、未知の役割
    with pytest.raises(RoleConflictError):
        ensure_role_available(tmp_path, ROLE_TOOLSERVER)


def test_empty_marker_is_ignored(tmp_path):
    (tmp_path / "role").write_text("\n", encoding="utf-8")
    ensure_role_available(tmp_path, ROLE_TOOLSERVER)


def test_conflict_message_names_the_existing_role_and_where_it_was_found(tmp_path):
    (tmp_path / "agent").mkdir()
    with pytest.raises(RoleConflictError) as e:
        ensure_role_available(tmp_path, ROLE_TOOLSERVER)
    message = str(e.value)
    assert "AIエージェント" in message and "ツールサーバ" in message  # 既存の役割と、設定しようとした役割
    assert str(tmp_path / "agent") in message  # 根拠(どこにあったか)
    assert "CAPASS_HOME" in message  # 開発・テストでの回避方法
    assert e.value.exit_code == 3


def test_both_directory_and_marker_are_reported(tmp_path):
    (tmp_path / "agent").mkdir()
    write_role_marker(tmp_path, ROLE_AGENT)
    evidence = detect_role_evidence(tmp_path)
    assert len(evidence[ROLE_AGENT]) == 2

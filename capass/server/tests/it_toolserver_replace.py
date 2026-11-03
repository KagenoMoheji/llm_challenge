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
sys.path.append(PYPATH)  # testlib.py(テスト共通の補助関数)をimportするため

# その他のモジュールやROOTPATHのディレクトリ起点の相対パスでのimport
import time
from datetime import datetime, timezone
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey
from sqlalchemy import select
from capass_server.common.config import SIGNATURE_MAX_SKEW_SEC, TOOL_SERVER_RESERVATION_TTL_SEC, TOOL_SERVER_STANDBY_TTL_SEC
from capass_server.common.signature import (
    SIGN_CONTEXT_AGENT_ADDTOOL,
    SIGN_CONTEXT_TOOLSERVER_REPLACE_ACTIVATE_NEW,
    SIGN_CONTEXT_TOOLSERVER_REPLACE_ACTIVATE_OLD,
)
from capass_server.models.entities import ApprovalStatus, TblAgentTool, TblToolServer
from capass_server.services import tool_server as tool_server_service
from testlib import (
    ADMIN_EMAIL,
    APPLICANT_EMAIL,
    EXEC_URL,
    NEW_EXEC_URL,
    PARAMS_SCHEMA,
    chtkn_body,
    exec_body,
    list_tools_headers,
    pub_b64,
    replace_activate_body,
    replace_reserve_body,
    replace_rollback_body,
    seed_agent,
    seed_agent_tool,
    seed_tool_server,
    signed_body,
)


def _reserve(client, old_id, body):
    return client.post(f"/api/v1/toolservers/{old_id}/replace/reserve", json=body)


def _activate(client, old_id, body):
    return client.post(f"/api/v1/toolservers/{old_id}/replace/activate", json=body)


def _rollback(client, old_id, body):
    return client.post(f"/api/v1/toolservers/{old_id}/replace/rollback", json=body)


def _chtkn(client, priv, tool_endpoint="psql_manager"):
    return client.post(f"/api/v1/agents/agent-1/chtkn/{tool_endpoint}", json=chtkn_body(priv, "agent-1", tool_endpoint))


def _addtool(client, priv, tool_endpoint):
    fields = {
        "tool_endpoint": tool_endpoint,
        "context": "テスト",
        "params_schema": PARAMS_SCHEMA,
        "tool_proxy_token": "token-" + tool_endpoint,
        "tool_server_public_key": pub_b64(priv),
    }
    body = signed_body(priv, SIGN_CONTEXT_AGENT_ADDTOOL, fields, path_params={"agent_id": "agent-1"})
    return client.post("/api/v1/agents/agent-1/addtool", json=body)


def _setup(session_factory):
    """旧ツールサーバ(承認済み)と、そのツール2つ(psql_manager, psql_terminal_admin)、それを割り当てられたAIエージェントを用意する。
    (旧のid, 旧の秘密鍵, 新の秘密鍵, AIエージェントの秘密鍵)を返す。"""
    old_priv, new_priv, agent_priv = Ed25519PrivateKey.generate(), Ed25519PrivateKey.generate(), Ed25519PrivateKey.generate()
    old_id = seed_tool_server(session_factory, old_priv, name="old-server")
    seed_agent(session_factory, agent_priv, "agent-1")
    seed_agent_tool(session_factory, "agent-1", "psql_manager", old_priv, token="tool-token")
    seed_agent_tool(session_factory, "agent-1", "psql_terminal_admin", old_priv, token="tool-token-2")
    return old_id, old_priv, new_priv, agent_priv


def _setup_reserved(client, session_factory, admin_priv):
    """_setupに加えて、管理者が、新ツールサーバを予約する。(旧のid, 新のid, 旧の秘密鍵, 新の秘密鍵, AIエージェントの秘密鍵)を返す。"""
    old_id, old_priv, new_priv, agent_priv = _setup(session_factory)
    res = _reserve(client, old_id, replace_reserve_body(admin_priv, old_id, new_priv))
    assert res.status_code == 201
    return old_id, res.json()["toolserver_id"], old_priv, new_priv, agent_priv


def _server(session_factory, server_id):
    with session_factory() as db:
        return db.get(TblToolServer, server_id)


def _tool_servers(session_factory):
    """ツールエンドポイントごとの、ツールサーバのid(AIエージェントagent-1のツール)。"""
    with session_factory() as db:
        return {t.tool_endpoint: t.tool_server_id for t in db.execute(select(TblAgentTool)).scalars().all()}


def _utc(dt):
    return dt if dt.tzinfo else dt.replace(tzinfo=timezone.utc)


# ---------- reserve(予約: CaPassサーバ管理者が、後継を事前に承認する) ----------
def test_reserve_registers_a_reserved_successor(client, session_factory, admin_priv):
    old_id, old_priv, new_priv, _ = _setup(session_factory)
    res = _reserve(client, old_id, replace_reserve_body(admin_priv, old_id, new_priv))
    assert res.status_code == 201
    data = res.json()
    assert (data["replaces_toolserver_id"], data["status"], data["approver_email"], data["applicant_email"]) == (old_id, "reserved", ADMIN_EMAIL, APPLICANT_EMAIL)
    assert (data["tool_server_exec_url"], data["tool_server_public_key"]) == (NEW_EXEC_URL, pub_b64(new_priv))
    assert data["reserved_until"] is not None

    successor = _server(session_factory, data["toolserver_id"])
    assert (successor.status, successor.replaces_tool_server_id, successor.exec_url) == (ApprovalStatus.RESERVED, old_id, NEW_EXEC_URL)
    remaining = (_utc(successor.status_expires_at) - datetime.now(timezone.utc)).total_seconds()
    assert TOOL_SERVER_RESERVATION_TTL_SEC - 60 < remaining <= TOOL_SERVER_RESERVATION_TTL_SEC  # 予約には期限がある
    assert _server(session_factory, old_id).status == ApprovalStatus.APPROVED  # 予約しただけでは、旧は、そのまま
    assert set(_tool_servers(session_factory).values()) == {old_id}  # ツールは、まだ旧のまま


def test_reserved_server_cannot_operate_before_activation(client, session_factory, admin_priv):
    old_id, new_id, old_priv, new_priv, _ = _setup_reserved(client, session_factory, admin_priv)
    assert _addtool(client, new_priv, "new_tool").status_code == 403  # 予約中の鍵では、まだ何もできない
    assert _chtkn(client, new_priv).status_code == 403


def test_reserve_by_non_admin_is_forbidden(client, session_factory, admin_priv):
    old_id, old_priv, new_priv, _ = _setup(session_factory)
    for signer in (Ed25519PrivateKey.generate(), old_priv):  # 無関係の鍵と、旧ツールサーバ自身の鍵は、予約できない
        assert _reserve(client, old_id, replace_reserve_body(signer, old_id, new_priv)).status_code == 403
    with session_factory() as db:
        assert len(db.execute(select(TblToolServer)).scalars().all()) == 1


def test_reserve_signature_checks(client, session_factory, admin_priv):
    old_id, old_priv, new_priv, _ = _setup(session_factory)
    body = replace_reserve_body(admin_priv, old_id, new_priv)
    assert _reserve(client, old_id, {**body, "new_tool_server_exec_url": "https://evil.example.com/exec"}).status_code == 401  # 管理者が署名した実行URLを、すり替えられない
    assert _reserve(client, old_id, {**body, "new_tool_server_public_key": pub_b64(Ed25519PrivateKey.generate())}).status_code == 401
    assert _reserve(client, old_id + 1, body).status_code == 401  # 別のツールサーバ向けの署名の使い回し
    expired = replace_reserve_body(admin_priv, old_id, new_priv, signed_at=int(time.time()) - SIGNATURE_MAX_SKEW_SEC - 60)
    assert _reserve(client, old_id, expired).status_code == 401


def test_reserve_unknown_predecessor_is_not_found(client, session_factory, admin_priv):
    _, _, new_priv, _ = _setup(session_factory)
    assert _reserve(client, 999, replace_reserve_body(admin_priv, 999, new_priv)).status_code == 404  # 管理者には、存在しないことを伝える


def test_reserve_requires_active_predecessor(client, session_factory, admin_priv):
    new_priv = Ed25519PrivateKey.generate()
    for status in (ApprovalStatus.PENDING, ApprovalStatus.REVOKED, ApprovalStatus.STANDBY, ApprovalStatus.RESERVED):
        old_priv = Ed25519PrivateKey.generate()
        old_id = seed_tool_server(session_factory, old_priv, status, name=f"server-{status.value}", expires_in_sec=3600)
        assert _reserve(client, old_id, replace_reserve_body(admin_priv, old_id, new_priv)).status_code == 409, status  # アクティブ(承認済み)なツールサーバだけが、置き換えられる


def test_reserve_conflicts(client, session_factory, admin_priv):
    old_id, old_priv, new_priv, _ = _setup(session_factory)
    assert _reserve(client, old_id, replace_reserve_body(admin_priv, old_id, new_priv)).status_code == 201
    another = Ed25519PrivateKey.generate()
    assert _reserve(client, old_id, replace_reserve_body(admin_priv, old_id, another)).status_code == 409  # 予約は、1つの旧ツールサーバに、1つだけ
    other_old = Ed25519PrivateKey.generate()
    other_old_id = seed_tool_server(session_factory, other_old, name="other-old")
    assert _reserve(client, other_old_id, replace_reserve_body(admin_priv, other_old_id, new_priv)).status_code == 409  # 新しい公開鍵は、すでに登録されている


def test_expired_reservation_does_not_block_a_new_reservation(client, session_factory, admin_priv):
    old_id, old_priv, new_priv, _ = _setup(session_factory)
    stale_priv = Ed25519PrivateKey.generate()
    seed_tool_server(session_factory, stale_priv, ApprovalStatus.RESERVED, name="stale", replaces_tool_server_id=old_id, expires_in_sec=-10)  # 期限切れの予約
    assert _reserve(client, old_id, replace_reserve_body(admin_priv, old_id, new_priv)).status_code == 201
    assert _reserve(client, old_id, replace_reserve_body(admin_priv, old_id, stale_priv)).status_code == 409  # 期限切れの鍵も、公開鍵としては登録済み(さらに、予約が1つ有効)


def test_reserve_exec_url_policy(client, session_factory, admin_priv, monkeypatch):
    old_id, old_priv, new_priv, _ = _setup(session_factory)
    monkeypatch.setattr(tool_server_service, "TOOL_SERVER_ALLOW_HTTP", False)
    res = _reserve(client, old_id, replace_reserve_body(admin_priv, old_id, new_priv, exec_url="http://10.1.2.3:8080/capass/exec"))
    assert res.status_code == 422 and "https" in res.json()["detail"]  # 既定では、httpは使えない
    assert _reserve(client, old_id, replace_reserve_body(admin_priv, old_id, new_priv, exec_url="https://10.1.2.3:8443/capass/exec")).status_code == 201  # プライベートIPのhttpsは、使える
    other_new = Ed25519PrivateKey.generate()
    other_old = Ed25519PrivateKey.generate()
    other_old_id = seed_tool_server(session_factory, other_old, name="other-old")
    monkeypatch.setattr(tool_server_service, "TOOL_SERVER_ALLOW_HTTP", True)  # 運用判断で、httpを許可した場合
    assert _reserve(client, other_old_id, replace_reserve_body(admin_priv, other_old_id, other_new, exec_url="http://10.1.2.4:8080/capass/exec")).status_code == 201


def test_reserve_invalid_input_is_unprocessable(client, session_factory, admin_priv):
    old_id, old_priv, new_priv, _ = _setup(session_factory)
    body = replace_reserve_body(admin_priv, old_id, new_priv)
    for key, bad in (("new_tool_server_public_key", "not-a-valid-key"), ("admin_public_key", "not-a-valid-key"), ("applicant_email", "not-an-email"), ("new_tool_server_exec_url", "ftp://example.com"), ("new_tool_server_name", "")):
        assert _reserve(client, old_id, {**body, key: bad}).status_code == 422, key
    assert _reserve(client, old_id, {**body, "unexpected": "x"}).status_code == 422
    for missing in ("new_tool_server_public_key", "new_tool_server_name", "new_tool_server_exec_url", "applicant_email", "admin_public_key"):
        assert _reserve(client, old_id, {k: v for k, v in body.items() if k != missing}).status_code == 422, missing


# ---------- activate(切り替え: 旧・新の両方の署名) ----------
def test_activate_switches_tools_to_the_reserved_server(client, session_factory, admin_priv, fake_tool_server):
    old_id, new_id, old_priv, new_priv, agent_priv = _setup_reserved(client, session_factory, admin_priv)
    res = _activate(client, old_id, replace_activate_body(old_priv, new_priv, old_id))
    assert res.status_code == 200
    data = res.json()
    assert (data["active_toolserver_id"], data["standby_toolserver_id"], data["moved_tools"], data["active_tool_server_exec_url"]) == (new_id, old_id, 2, NEW_EXEC_URL)
    assert data["standby_until"] is not None

    old, new = _server(session_factory, old_id), _server(session_factory, new_id)
    assert (old.status, new.status) == (ApprovalStatus.STANDBY, ApprovalStatus.APPROVED)
    assert new.status_expires_at is None
    remaining = (_utc(old.status_expires_at) - datetime.now(timezone.utc)).total_seconds()
    assert TOOL_SERVER_STANDBY_TTL_SEC - 60 < remaining <= TOOL_SERVER_STANDBY_TTL_SEC  # 切り戻しできる期限
    assert set(_tool_servers(session_factory).values()) == {new_id}  # ツールは、新へ付け替えられた

    # AIエージェントの一覧は、そのまま。実行は、新ツールサーバのURLへ、同じトークンで中継される
    tools = client.get("/api/v1/agents/agent-1/tools", headers=list_tools_headers(agent_priv, "agent-1")).json()["tools"]
    assert [t["tool_endpoint"] for t in tools] == ["psql_manager", "psql_terminal_admin"]
    assert client.post("/api/v1/agents/agent-1/exec/psql_manager", json=exec_body(agent_priv, "agent-1", "psql_manager")).status_code == 200
    assert (fake_tool_server.calls[0]["url"], fake_tool_server.calls[0]["token"]) == (NEW_EXEC_URL, "tool-token")


def test_after_activation_only_the_new_server_operates(client, session_factory, admin_priv):
    old_id, new_id, old_priv, new_priv, _ = _setup_reserved(client, session_factory, admin_priv)
    assert _activate(client, old_id, replace_activate_body(old_priv, new_priv, old_id)).status_code == 200
    assert _chtkn(client, new_priv).status_code == 200
    assert _chtkn(client, old_priv).status_code == 403  # 旧(待機中)の鍵では、もう更新できない
    assert _addtool(client, new_priv, "added_by_new").status_code == 201
    assert _addtool(client, old_priv, "added_by_old").status_code == 403


def test_activate_does_not_move_tools_of_other_tool_servers(client, session_factory, admin_priv):
    old_id, new_id, old_priv, new_priv, _ = _setup_reserved(client, session_factory, admin_priv)
    other_priv = Ed25519PrivateKey.generate()
    other_id = seed_tool_server(session_factory, other_priv, name="other-server")
    seed_agent_tool(session_factory, "agent-1", "other_tool", other_priv)
    assert _activate(client, old_id, replace_activate_body(old_priv, new_priv, old_id)).status_code == 200
    assert _tool_servers(session_factory)["other_tool"] == other_id


def test_activate_requires_a_reservation_for_the_new_key(client, session_factory, admin_priv):
    old_id, old_priv, new_priv, _ = _setup(session_factory)
    assert _activate(client, old_id, replace_activate_body(old_priv, new_priv, old_id)).status_code == 409  # 予約していない鍵には、切り替えられない(両方の署名があっても)
    approved_other = Ed25519PrivateKey.generate()
    seed_tool_server(session_factory, approved_other, name="approved-other")
    assert _activate(client, old_id, replace_activate_body(old_priv, approved_other, old_id)).status_code == 409  # 承認済みでも、後継として予約されていない
    pending = Ed25519PrivateKey.generate()
    seed_tool_server(session_factory, pending, ApprovalStatus.PENDING, name="pending-one", replaces_tool_server_id=old_id)
    assert _activate(client, old_id, replace_activate_body(old_priv, pending, old_id)).status_code == 409
    other_old = Ed25519PrivateKey.generate()
    other_old_id = seed_tool_server(session_factory, other_old, name="other-old")
    reserved_for_other = Ed25519PrivateKey.generate()
    seed_tool_server(session_factory, reserved_for_other, ApprovalStatus.RESERVED, name="reserved-for-other", replaces_tool_server_id=other_old_id, expires_in_sec=3600)
    assert _activate(client, old_id, replace_activate_body(old_priv, reserved_for_other, old_id)).status_code == 409  # 別のツールサーバの後継としての予約は、使えない
    assert set(_tool_servers(session_factory).values()) == {old_id}


def test_activate_with_expired_reservation_is_conflict(client, session_factory, admin_priv):
    old_id, old_priv, new_priv, _ = _setup(session_factory)
    seed_tool_server(session_factory, new_priv, ApprovalStatus.RESERVED, name="expired", replaces_tool_server_id=old_id, expires_in_sec=-10)
    res = _activate(client, old_id, replace_activate_body(old_priv, new_priv, old_id))
    assert res.status_code == 409 and "expired" in res.json()["detail"]
    assert _server(session_factory, old_id).status == ApprovalStatus.APPROVED


def test_activate_signature_checks(client, session_factory, admin_priv):
    old_id, new_id, old_priv, new_priv, _ = _setup_reserved(client, session_factory, admin_priv)
    attacker = Ed25519PrivateKey.generate()
    res = _activate(client, old_id, replace_activate_body(attacker, new_priv, old_id))  # 旧ツールサーバの鍵を持っていない
    assert res.status_code == 401 and res.json()["detail"] == "invalid signature"

    body = replace_activate_body(old_priv, new_priv, old_id)
    other_new_signature = replace_activate_body(old_priv, attacker, old_id, signed_at=body["signed_at"])["new_key_signature"]  # 新しい鍵の持ち主ではない人の署名
    res = _activate(client, old_id, {**body, "new_key_signature": other_new_signature})
    assert res.status_code == 401 and res.json()["detail"] == "invalid signature of the new public key"  # 旧の署名は正当なので、新の署名が不正だと伝える

    swapped = replace_activate_body(old_priv, new_priv, old_id, old_context=SIGN_CONTEXT_TOOLSERVER_REPLACE_ACTIVATE_NEW, new_context=SIGN_CONTEXT_TOOLSERVER_REPLACE_ACTIVATE_OLD)
    assert _activate(client, old_id, swapped).status_code == 401  # 役割(プレフィックス)を入れ替えた署名は、使えない
    assert _activate(client, old_id, {**body, "new_tool_server_public_key": pub_b64(attacker)}).status_code == 401  # 署名後に、新しい鍵をすり替える
    assert _activate(client, old_id, {**body, "signed_at": body["signed_at"] + 1}).status_code == 401
    assert _activate(client, 999, replace_activate_body(old_priv, new_priv, 999)).status_code == 401  # IDの有無は伝えない
    expired = replace_activate_body(old_priv, new_priv, old_id, signed_at=int(time.time()) - SIGNATURE_MAX_SKEW_SEC - 60)
    assert _activate(client, old_id, expired).status_code == 401
    assert _server(session_factory, old_id).status == ApprovalStatus.APPROVED  # どれも、切り替わらない
    assert set(_tool_servers(session_factory).values()) == {old_id}


def test_activate_twice_is_forbidden(client, session_factory, admin_priv):
    old_id, new_id, old_priv, new_priv, _ = _setup_reserved(client, session_factory, admin_priv)
    body = replace_activate_body(old_priv, new_priv, old_id)
    assert _activate(client, old_id, body).status_code == 200
    assert _activate(client, old_id, body).status_code == 403  # 旧は、もうアクティブではない(再送は、何も起こさない)
    assert _server(session_factory, new_id).status == ApprovalStatus.APPROVED


def test_activate_requires_active_predecessor(client, session_factory, admin_priv):
    old_priv, new_priv = Ed25519PrivateKey.generate(), Ed25519PrivateKey.generate()
    old_id = seed_tool_server(session_factory, old_priv, ApprovalStatus.REVOKED, name="revoked-old")
    seed_tool_server(session_factory, new_priv, ApprovalStatus.RESERVED, name="reserved-new", replaces_tool_server_id=old_id, expires_in_sec=3600)
    assert _activate(client, old_id, replace_activate_body(old_priv, new_priv, old_id)).status_code == 403  # 取り消されたツールサーバは、切り替えを開始できない


def test_activate_invalid_input_is_unprocessable(client, session_factory, admin_priv):
    old_id, new_id, old_priv, new_priv, _ = _setup_reserved(client, session_factory, admin_priv)
    body = replace_activate_body(old_priv, new_priv, old_id)
    assert _activate(client, old_id, {**body, "new_tool_server_public_key": "not-a-valid-key"}).status_code == 422
    assert _activate(client, old_id, {**body, "new_key_signature": "not-a-valid-signature"}).status_code == 422
    assert _activate(client, old_id, {**body, "unexpected": "x"}).status_code == 422
    for missing in ("signature", "new_key_signature", "new_tool_server_public_key", "signed_at"):
        assert _activate(client, old_id, {k: v for k, v in body.items() if k != missing}).status_code == 422, missing
    assert client.post("/api/v1/toolservers/not-a-number/replace/activate", json=body).status_code == 422


# ---------- rollback(切り戻し: 旧ツールサーバの署名だけ) ----------
def _activated(client, session_factory, admin_priv):
    old_id, new_id, old_priv, new_priv, agent_priv = _setup_reserved(client, session_factory, admin_priv)
    assert _activate(client, old_id, replace_activate_body(old_priv, new_priv, old_id)).status_code == 200
    return old_id, new_id, old_priv, new_priv, agent_priv


def test_rollback_restores_the_old_server_with_only_its_signature(client, session_factory, admin_priv, fake_tool_server):
    old_id, new_id, old_priv, new_priv, agent_priv = _activated(client, session_factory, admin_priv)
    res = _rollback(client, old_id, replace_rollback_body(old_priv, old_id))  # 新ツールサーバの署名は、不要(新に不具合があっても、戻せる)
    assert res.status_code == 200
    data = res.json()
    assert (data["active_toolserver_id"], data["standby_toolserver_id"], data["moved_tools"], data["active_tool_server_exec_url"]) == (old_id, new_id, 2, EXEC_URL)
    old, new = _server(session_factory, old_id), _server(session_factory, new_id)
    assert (old.status, new.status) == (ApprovalStatus.APPROVED, ApprovalStatus.STANDBY)
    assert old.status_expires_at is None and new.status_expires_at is not None
    assert set(_tool_servers(session_factory).values()) == {old_id}
    assert client.post("/api/v1/agents/agent-1/exec/psql_manager", json=exec_body(agent_priv, "agent-1", "psql_manager")).status_code == 200
    assert fake_tool_server.calls[0]["url"] == EXEC_URL  # 旧のURLへ戻る
    assert _chtkn(client, new_priv).status_code == 403  # 新(待機中)は、操作できない
    assert _chtkn(client, old_priv).status_code == 200


def test_roll_forward_again_after_rollback(client, session_factory, admin_priv):
    old_id, new_id, old_priv, new_priv, _ = _activated(client, session_factory, admin_priv)
    assert _rollback(client, old_id, replace_rollback_body(old_priv, old_id)).status_code == 200
    res = _activate(client, old_id, replace_activate_body(old_priv, new_priv, old_id))  # 待機中の新へ、再び切り替える(管理者の再承認は不要)
    assert res.status_code == 200
    assert res.json()["active_toolserver_id"] == new_id
    assert set(_tool_servers(session_factory).values()) == {new_id}


def test_rollback_signature_checks(client, session_factory, admin_priv):
    old_id, new_id, old_priv, new_priv, _ = _activated(client, session_factory, admin_priv)
    for signer in (Ed25519PrivateKey.generate(), new_priv):  # 無関係の鍵、新ツールサーバの鍵では、切り戻せない
        assert _rollback(client, old_id, replace_rollback_body(signer, old_id)).status_code == 401
    assert _rollback(client, old_id, replace_rollback_body(old_priv, old_id + 100)).status_code == 401  # 別のツールサーバ向けの署名の使い回し
    assert _rollback(client, 999, replace_rollback_body(old_priv, 999)).status_code == 401  # IDの有無は伝えない
    assert _rollback(client, old_id, replace_rollback_body(old_priv, old_id, signed_at=int(time.time()) - SIGNATURE_MAX_SKEW_SEC - 60)).status_code == 401
    body = replace_rollback_body(old_priv, old_id)
    assert _rollback(client, old_id, {**body, "unexpected": "x"}).status_code == 422
    assert _server(session_factory, old_id).status == ApprovalStatus.STANDBY


def test_rollback_requires_standby_within_period_with_active_successor(client, session_factory, admin_priv):
    old_id, old_priv, new_priv, _ = _setup(session_factory)
    assert _rollback(client, old_id, replace_rollback_body(old_priv, old_id)).status_code == 409  # 待機中ではない(アクティブ)

    standby_priv = Ed25519PrivateKey.generate()
    standby_id = seed_tool_server(session_factory, standby_priv, ApprovalStatus.STANDBY, name="standby-alone", expires_in_sec=3600)
    res = _rollback(client, standby_id, replace_rollback_body(standby_priv, standby_id))
    assert res.status_code == 409 and "no active successor" in res.json()["detail"]  # アクティブな後継が無い

    expired_priv, successor_priv = Ed25519PrivateKey.generate(), Ed25519PrivateKey.generate()
    expired_id = seed_tool_server(session_factory, expired_priv, ApprovalStatus.STANDBY, name="standby-expired", expires_in_sec=-10)
    seed_tool_server(session_factory, successor_priv, ApprovalStatus.APPROVED, name="active-successor", replaces_tool_server_id=expired_id)
    res = _rollback(client, expired_id, replace_rollback_body(expired_priv, expired_id))
    assert res.status_code == 409 and "expired" in res.json()["detail"]  # 切り戻せる期限が過ぎた

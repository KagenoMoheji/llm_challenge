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
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey
from sqlalchemy import select
from capass_server.common.config import SIGNATURE_MAX_SKEW_SEC
from capass_server.common.signature import (
    SIGN_CONTEXT_AGENT_ADDTOOL,
    SIGN_CONTEXT_TOOLSERVER_CHKEY_NEW,
    SIGN_CONTEXT_TOOLSERVER_CHKEY_OLD,
)
from capass_server.models.entities import ApprovalStatus, TblAgentTool, TblToolServer
from testlib import (
    EXEC_URL,
    chkey_body,
    exec_body,
    list_tools_headers,
    pub_b64,
    seed_agent,
    seed_agent_tool,
    seed_tool_server,
    signed_body,
)


def _chkey(client, toolserver_id, body):
    return client.post(f"/api/v1/toolservers/{toolserver_id}/chkey", json=body)


def _setup(session_factory, status=ApprovalStatus.APPROVED):
    """旧ツールサーバ(承認済み)と、そのツールを持つAIエージェントを用意する。(toolserver_id, 旧の秘密鍵, 新の秘密鍵, AIエージェントの秘密鍵)を返す。"""
    old_priv, new_priv, agent_priv = Ed25519PrivateKey.generate(), Ed25519PrivateKey.generate(), Ed25519PrivateKey.generate()
    ts_id = seed_tool_server(session_factory, old_priv, status)
    seed_agent(session_factory, agent_priv, "agent-1")
    seed_agent_tool(session_factory, "agent-1", "psql_manager", old_priv)
    return ts_id, old_priv, new_priv, agent_priv


def _setup_unique(session_factory, status):
    """ステータスを指定した旧ツールサーバだけを用意する(名称が重複しないようにする)。(toolserver_id, 旧の秘密鍵, 新の秘密鍵, None)を返す。"""
    old_priv, new_priv = Ed25519PrivateKey.generate(), Ed25519PrivateKey.generate()
    ts_id = seed_tool_server(session_factory, old_priv, status, name=f"server-{status.value}")
    return ts_id, old_priv, new_priv, None


def _tool_server_key(session_factory, ts_id):
    with session_factory() as db:
        return db.get(TblToolServer, ts_id).tool_server_public_key


# ---------- 成功 ----------
def test_chkey_replaces_public_key_and_keeps_record(client, session_factory):
    ts_id, old_priv, new_priv, _ = _setup(session_factory)
    res = _chkey(client, ts_id, chkey_body(old_priv, new_priv, ts_id))
    assert res.status_code == 200
    data = res.json()
    assert data["toolserver_id"] == ts_id
    assert data["tool_server_public_key"] == pub_b64(new_priv)
    assert data["status"] == "approved"  # 承認のやり直しは不要
    with session_factory() as db:
        row = db.get(TblToolServer, ts_id)
        assert row.tool_server_public_key == pub_b64(new_priv)
        assert (row.status, row.exec_url) == (ApprovalStatus.APPROVED, EXEC_URL)  # ステータス・実行URLは引き継がれる
        assert db.execute(select(TblToolServer).where(TblToolServer.tool_server_public_key == pub_b64(old_priv))).scalar_one_or_none() is None


def test_chkey_updates_public_key_of_the_tools_too(client, session_factory):
    ts_id, old_priv, new_priv, _ = _setup(session_factory)
    seed_agent_tool(session_factory, "agent-1", "psql_terminal_admin", old_priv)
    other_priv = Ed25519PrivateKey.generate()
    seed_tool_server(session_factory, other_priv, name="other-server")
    seed_agent_tool(session_factory, "agent-1", "other_tool", other_priv)
    assert _chkey(client, ts_id, chkey_body(old_priv, new_priv, ts_id)).status_code == 200
    with session_factory() as db:
        keys = {t.tool_endpoint: t.tool_server_public_key for t in db.execute(select(TblAgentTool)).scalars().all()}
    assert keys == {"psql_manager": pub_b64(new_priv), "psql_terminal_admin": pub_b64(new_priv), "other_tool": pub_b64(other_priv)}  # 他のツールサーバのツールは変わらない


def test_tools_stay_executable_after_replacement(client, session_factory, fake_tool_server):
    ts_id, old_priv, new_priv, agent_priv = _setup(session_factory)
    assert _chkey(client, ts_id, chkey_body(old_priv, new_priv, ts_id)).status_code == 200
    tools = client.get("/api/v1/agents/agent-1/tools", headers=list_tools_headers(agent_priv, "agent-1")).json()["tools"]
    assert [t["tool_endpoint"] for t in tools] == ["psql_manager"]  # 一覧にも残る
    res = client.post("/api/v1/agents/agent-1/exec/psql_manager", json=exec_body(agent_priv, "agent-1", "psql_manager"))
    assert res.status_code == 200
    assert fake_tool_server.calls[0]["url"] == EXEC_URL  # 実行URLは同じ


def test_new_key_can_addtool_and_old_key_cannot_after_replacement(client, session_factory):
    ts_id, old_priv, new_priv, _ = _setup(session_factory)
    assert _chkey(client, ts_id, chkey_body(old_priv, new_priv, ts_id)).status_code == 200

    def addtool(priv, endpoint):
        fields = {
            "tool_endpoint": endpoint,
            "context": "テスト",
            "params_schema": {"type": "object", "properties": {}},
            "tool_proxy_token": "token-" + endpoint,
            "tool_server_public_key": pub_b64(priv),
        }
        body = signed_body(priv, SIGN_CONTEXT_AGENT_ADDTOOL, fields, path_params={"agent_id": "agent-1"})
        return client.post("/api/v1/agents/agent-1/addtool", json=body)

    assert addtool(new_priv, "added_by_new_key").status_code == 201
    assert addtool(old_priv, "added_by_old_key").status_code == 403  # 旧公開鍵は、もう登録されていない


def test_replaying_the_same_request_fails(client, session_factory):
    ts_id, old_priv, new_priv, _ = _setup(session_factory)
    body = chkey_body(old_priv, new_priv, ts_id)
    assert _chkey(client, ts_id, body).status_code == 200
    assert _chkey(client, ts_id, body).status_code == 401  # 現在の公開鍵は、すでに新しい鍵。旧の署名は、もう通らない
    assert _tool_server_key(session_factory, ts_id) == pub_b64(new_priv)


def test_replacement_can_be_repeated(client, session_factory):
    ts_id, old_priv, new_priv, _ = _setup(session_factory)
    third_priv = Ed25519PrivateKey.generate()
    assert _chkey(client, ts_id, chkey_body(old_priv, new_priv, ts_id)).status_code == 200
    assert _chkey(client, ts_id, chkey_body(new_priv, third_priv, ts_id)).status_code == 200
    assert _tool_server_key(session_factory, ts_id) == pub_b64(third_priv)


# ---------- 署名 ----------
def test_chkey_signed_by_wrong_old_key_is_unauthorized(client, session_factory):
    ts_id, old_priv, new_priv, _ = _setup(session_factory)
    attacker = Ed25519PrivateKey.generate()  # 旧ツールサーバの秘密鍵を持っていない
    res = _chkey(client, ts_id, chkey_body(attacker, new_priv, ts_id))
    assert res.status_code == 401
    assert res.json()["detail"] == "invalid signature"
    assert _tool_server_key(session_factory, ts_id) == pub_b64(old_priv)


def test_chkey_with_invalid_new_key_signature_is_unauthorized(client, session_factory):
    ts_id, old_priv, new_priv, _ = _setup(session_factory)
    body = chkey_body(old_priv, new_priv, ts_id)
    other = Ed25519PrivateKey.generate()
    body["new_key_signature"] = chkey_body(old_priv, other, ts_id, signed_at=body["signed_at"])["new_key_signature"]  # 新しい鍵の持ち主ではない人の署名
    res = _chkey(client, ts_id, body)
    assert res.status_code == 401
    assert res.json()["detail"] == "invalid signature of the new public key"  # 旧の署名は正当なので、新の署名が不正だと伝える
    assert _tool_server_key(session_factory, ts_id) == pub_b64(old_priv)


def test_old_signature_cannot_be_reused_as_new_key_signature(client, session_factory):
    ts_id, old_priv, new_priv, _ = _setup(session_factory)
    body = chkey_body(old_priv, new_priv, ts_id)
    body["new_key_signature"] = body["signature"]  # 旧の署名を、新の署名として流用(役割ごとにプレフィックスが違うので通らない)
    assert _chkey(client, ts_id, body).status_code == 401


def test_chkey_signatures_with_swapped_roles_are_rejected(client, session_factory):
    ts_id, old_priv, new_priv, _ = _setup(session_factory)
    body = chkey_body(old_priv, new_priv, ts_id, old_context=SIGN_CONTEXT_TOOLSERVER_CHKEY_NEW, new_context=SIGN_CONTEXT_TOOLSERVER_CHKEY_OLD)
    assert _chkey(client, ts_id, body).status_code == 401


def test_chkey_tampered_body_is_unauthorized(client, session_factory):
    ts_id, old_priv, new_priv, _ = _setup(session_factory)
    attacker = Ed25519PrivateKey.generate()
    body = chkey_body(old_priv, new_priv, ts_id)
    body["new_tool_server_public_key"] = pub_b64(attacker)  # 署名後に、新しい公開鍵を攻撃者の鍵にすり替える
    assert _chkey(client, ts_id, body).status_code == 401
    body = chkey_body(old_priv, new_priv, ts_id)
    body["signed_at"] += 1  # 署名時刻の改ざん
    assert _chkey(client, ts_id, body).status_code == 401
    assert _tool_server_key(session_factory, ts_id) == pub_b64(old_priv)


def test_chkey_signed_for_other_toolserver_is_unauthorized(client, session_factory):
    ts_id, old_priv, new_priv, _ = _setup(session_factory)
    other_priv = Ed25519PrivateKey.generate()
    other_id = seed_tool_server(session_factory, other_priv, name="other-server")
    body = chkey_body(old_priv, new_priv, other_id)  # 別のtoolserver_id向けの署名を使い回す
    assert _chkey(client, ts_id, body).status_code == 401


def test_chkey_unknown_toolserver_is_unauthorized(client, session_factory):
    old_priv, new_priv = Ed25519PrivateKey.generate(), Ed25519PrivateKey.generate()
    assert _chkey(client, 999, chkey_body(old_priv, new_priv, 999)).status_code == 401  # 署名不正と区別しない(IDの有無を知らせない)


def test_chkey_expired_signature_is_unauthorized(client, session_factory):
    ts_id, old_priv, new_priv, _ = _setup(session_factory)
    body = chkey_body(old_priv, new_priv, ts_id, signed_at=int(time.time()) - SIGNATURE_MAX_SKEW_SEC - 60)
    assert _chkey(client, ts_id, body).status_code == 401


# ---------- 状態・重複 ----------
def test_chkey_requires_approved_tool_server(client, session_factory):
    for status in (ApprovalStatus.PENDING, ApprovalStatus.REVOKED):
        ts_id, old_priv, new_priv, _ = _setup_unique(session_factory, status)
        res = _chkey(client, ts_id, chkey_body(old_priv, new_priv, ts_id))
        assert res.status_code == 403, status  # 承認されていない(取り消された)ツールサーバは、リプレースして復帰することはできない
        assert _tool_server_key(session_factory, ts_id) == pub_b64(old_priv)


def test_chkey_to_already_registered_key_is_conflict(client, session_factory):
    ts_id, old_priv, _, _ = _setup(session_factory)
    other_priv = Ed25519PrivateKey.generate()
    seed_tool_server(session_factory, other_priv, name="other-server")
    assert _chkey(client, ts_id, chkey_body(old_priv, other_priv, ts_id)).status_code == 409  # 他のツールサーバの公開鍵には、更新できない
    assert _tool_server_key(session_factory, ts_id) == pub_b64(old_priv)


def test_chkey_to_the_same_key_is_conflict(client, session_factory):
    ts_id, old_priv, _, _ = _setup(session_factory)
    assert _chkey(client, ts_id, chkey_body(old_priv, old_priv, ts_id)).status_code == 409


# ---------- 入力の形式 ----------
def test_chkey_invalid_input_is_unprocessable(client, session_factory):
    ts_id, old_priv, new_priv, _ = _setup(session_factory)
    body = chkey_body(old_priv, new_priv, ts_id)
    assert _chkey(client, ts_id, {**body, "new_tool_server_public_key": "not-a-valid-key"}).status_code == 422
    assert _chkey(client, ts_id, {**body, "new_key_signature": "not-a-valid-signature"}).status_code == 422
    assert _chkey(client, ts_id, {**body, "unexpected": "x"}).status_code == 422
    for missing in ("signature", "new_key_signature", "new_tool_server_public_key", "signed_at"):
        assert _chkey(client, ts_id, {k: v for k, v in body.items() if k != missing}).status_code == 422, missing
    assert client.post("/api/v1/toolservers/not-a-number/chkey", json=body).status_code == 422

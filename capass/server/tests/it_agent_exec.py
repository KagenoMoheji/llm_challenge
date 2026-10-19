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
from capass_server.common.errors import ToolServerTimeoutError, ToolServerUnavailableError
from capass_server.common.tool_client import ToolServerResponse
from capass_server.models.entities import ApprovalStatus, TblAgentTool, TblRequestNonce
from testlib import EXEC_URL, exec_body, seed_agent, seed_agent_tool, seed_tool_server


def _post(client, agent_id, tool_endpoint, body):
    return client.post(f"/api/v1/agents/{agent_id}/exec/{tool_endpoint}", json=body)


def _setup(session_factory, agent_id="agent-1", tool_endpoint="psql_manager", token="proxy-token-1"):
    """承認済みのAIエージェントとツールサーバ、実行できるツールを用意し、AIエージェントの秘密鍵を返す。"""
    agent_priv, ts_priv = Ed25519PrivateKey.generate(), Ed25519PrivateKey.generate()
    seed_agent(session_factory, agent_priv, agent_id)
    seed_tool_server(session_factory, ts_priv)
    seed_agent_tool(session_factory, agent_id, tool_endpoint, ts_priv, token=token)
    return agent_priv, ts_priv


def _used_at(session_factory, agent_id="agent-1", tool_endpoint="psql_manager"):
    with session_factory() as db:
        return db.execute(select(TblAgentTool).where(TblAgentTool.agent_id == agent_id, TblAgentTool.tool_endpoint == tool_endpoint)).scalar_one().tool_used_at


# ---------- 成功 ----------
def test_exec_relays_to_tool_server_and_returns_its_result(client, session_factory, fake_tool_server):
    agent_priv, _ = _setup(session_factory)
    fake_tool_server.response = ToolServerResponse(200, '{"rows": [[1]]}'.encode(), "application/json")
    res = _post(client, "agent-1", "psql_manager", exec_body(agent_priv, "agent-1", "psql_manager", params={"sql": "SELECT 1"}))
    assert res.status_code == 200
    assert res.json() == {"rows": [[1]]}
    assert res.headers["content-type"].startswith("application/json")

    # ツールサーバへは、実行URLに、復号した(平文の)ツール代理トークンとAIエージェント情報、ツールパラメータを渡す
    assert len(fake_tool_server.calls) == 1
    call = fake_tool_server.calls[0]
    assert call["url"] == EXEC_URL
    assert call["token"] == "proxy-token-1"
    assert call["payload"] == {"agent_id": "agent-1", "tool_endpoint": "psql_manager", "params": {"sql": "SELECT 1"}}
    assert call["user_agent"].startswith("CaPass/")


def test_exec_updates_tool_used_at_on_success(client, session_factory, fake_tool_server):
    agent_priv, _ = _setup(session_factory)
    assert _used_at(session_factory) is None
    assert _post(client, "agent-1", "psql_manager", exec_body(agent_priv, "agent-1", "psql_manager")).status_code == 200
    assert _used_at(session_factory) is not None


def test_exec_with_japanese_endpoint_and_empty_params(client, session_factory, fake_tool_server):
    agent_priv, _ = _setup(session_factory, tool_endpoint="psql_部長ロール")
    body = exec_body(agent_priv, "agent-1", "psql_部長ロール", params={})
    assert _post(client, "agent-1", "psql_部長ロール", body).status_code == 200
    assert fake_tool_server.calls[0]["payload"]["tool_endpoint"] == "psql_部長ロール"


# ---------- ツールサーバの応答の中継 ----------
def test_exec_relays_4xx_from_tool_server(client, session_factory, fake_tool_server):
    agent_priv, _ = _setup(session_factory)
    fake_tool_server.response = ToolServerResponse(403, b'{"detail": "permission denied"}', "application/json")  # ツールサーバの「権限ありません」
    res = _post(client, "agent-1", "psql_manager", exec_body(agent_priv, "agent-1", "psql_manager"))
    assert res.status_code == 403
    assert res.json() == {"detail": "permission denied"}
    assert _used_at(session_factory) is None  # 成功していないので、利用日時は更新しない


def test_exec_maps_tool_server_401_to_403(client, session_factory, fake_tool_server):
    agent_priv, _ = _setup(session_factory)
    fake_tool_server.response = ToolServerResponse(401, b'{"detail": "invalid token"}', "application/json")
    res = _post(client, "agent-1", "psql_manager", exec_body(agent_priv, "agent-1", "psql_manager"))
    assert res.status_code == 403  # AIエージェント自身の認証失敗(401)と紛らわしいので、403にする
    assert res.json() == {"detail": "invalid token"}


def test_exec_maps_tool_server_5xx_and_3xx_to_502(client, session_factory, fake_tool_server):
    agent_priv, _ = _setup(session_factory)
    for status in (500, 503, 302):
        fake_tool_server.response = ToolServerResponse(status, b"internal details", "text/plain")
        res = _post(client, "agent-1", "psql_manager", exec_body(agent_priv, "agent-1", "psql_manager"))
        assert res.status_code == 502, status
        assert "internal details" not in res.text  # ツールサーバの内部情報は中継しない
    assert _used_at(session_factory) is None


def test_exec_maps_tool_server_connection_errors(client, session_factory, fake_tool_server):
    agent_priv, _ = _setup(session_factory)
    fake_tool_server.response = ToolServerUnavailableError()
    assert _post(client, "agent-1", "psql_manager", exec_body(agent_priv, "agent-1", "psql_manager")).status_code == 502
    fake_tool_server.response = ToolServerTimeoutError()
    assert _post(client, "agent-1", "psql_manager", exec_body(agent_priv, "agent-1", "psql_manager")).status_code == 504


# ---------- 権限ありません(ツールが無い/ロック/ツールサーバ未承認) ----------
def test_exec_unknown_endpoint_is_forbidden(client, session_factory, fake_tool_server):
    agent_priv, _ = _setup(session_factory)
    assert _post(client, "agent-1", "no_such_tool", exec_body(agent_priv, "agent-1", "no_such_tool")).status_code == 403
    assert fake_tool_server.calls == []


def test_exec_locked_tool_is_forbidden(client, session_factory, fake_tool_server):
    agent_priv, ts_priv = _setup(session_factory)
    seed_agent_tool(session_factory, "agent-1", "psql_locked", ts_priv, locked=True)
    assert _post(client, "agent-1", "psql_locked", exec_body(agent_priv, "agent-1", "psql_locked")).status_code == 403
    assert fake_tool_server.calls == []


def test_exec_tool_of_revoked_tool_server_is_forbidden(client, session_factory, fake_tool_server):
    agent_priv, _ = _setup(session_factory)
    revoked_priv = Ed25519PrivateKey.generate()
    seed_tool_server(session_factory, revoked_priv, ApprovalStatus.REVOKED, name="revoked-server")
    seed_agent_tool(session_factory, "agent-1", "tool_of_revoked", revoked_priv)
    assert _post(client, "agent-1", "tool_of_revoked", exec_body(agent_priv, "agent-1", "tool_of_revoked")).status_code == 403
    assert fake_tool_server.calls == []


def test_exec_other_agents_tool_is_forbidden(client, session_factory, fake_tool_server):
    agent_priv, ts_priv = _setup(session_factory, "agent-1", "tool_1")
    seed_agent(session_factory, Ed25519PrivateKey.generate(), "agent-2")
    seed_agent_tool(session_factory, "agent-2", "tool_2", ts_priv)
    assert _post(client, "agent-1", "tool_2", exec_body(agent_priv, "agent-1", "tool_2")).status_code == 403  # 他のAIエージェントのツールは実行できない
    assert fake_tool_server.calls == []


# ---------- 認証(署名) ----------
def test_exec_unknown_agent_is_unauthorized(client, session_factory, fake_tool_server):
    priv = Ed25519PrivateKey.generate()
    assert _post(client, "nobody", "psql_manager", exec_body(priv, "nobody", "psql_manager")).status_code == 401
    assert fake_tool_server.calls == []


def test_exec_signed_by_other_key_is_unauthorized(client, session_factory, fake_tool_server):
    _setup(session_factory)
    attacker = Ed25519PrivateKey.generate()  # agent_idを知っていても、秘密鍵が無ければ実行できない
    assert _post(client, "agent-1", "psql_manager", exec_body(attacker, "agent-1", "psql_manager")).status_code == 401
    assert fake_tool_server.calls == []


def test_exec_tampered_params_are_unauthorized(client, session_factory, fake_tool_server):
    agent_priv, _ = _setup(session_factory)
    body = exec_body(agent_priv, "agent-1", "psql_manager", params={"sql": "SELECT 1"})
    body["params"] = {"sql": "DROP TABLE users"}  # 署名後にパラメータを改ざん
    assert _post(client, "agent-1", "psql_manager", body).status_code == 401
    assert fake_tool_server.calls == []


def test_exec_signed_for_other_endpoint_is_unauthorized(client, session_factory, fake_tool_server):
    agent_priv, ts_priv = _setup(session_factory)
    seed_agent_tool(session_factory, "agent-1", "psql_terminal_admin", ts_priv)
    body = exec_body(agent_priv, "agent-1", "psql_manager")  # psql_manager用の署名を、別のツールへ使い回す
    assert _post(client, "agent-1", "psql_terminal_admin", body).status_code == 401
    assert fake_tool_server.calls == []


def test_exec_signed_for_other_agent_is_unauthorized(client, session_factory, fake_tool_server):
    agent_priv, ts_priv = _setup(session_factory, "agent-1")
    seed_agent(session_factory, Ed25519PrivateKey.generate(), "agent-2")
    seed_agent_tool(session_factory, "agent-2", "psql_manager", ts_priv)
    body = exec_body(agent_priv, "agent-1", "psql_manager")
    assert _post(client, "agent-2", "psql_manager", body).status_code == 401
    assert fake_tool_server.calls == []


def test_exec_expired_signature_is_unauthorized(client, session_factory, fake_tool_server):
    agent_priv, _ = _setup(session_factory)
    body = exec_body(agent_priv, "agent-1", "psql_manager", signed_at=int(time.time()) - SIGNATURE_MAX_SKEW_SEC - 60)
    assert _post(client, "agent-1", "psql_manager", body).status_code == 401
    assert fake_tool_server.calls == []


def test_exec_pending_or_revoked_agent_is_forbidden(client, session_factory, fake_tool_server):
    for agent_id, status in (("agent-pending", ApprovalStatus.PENDING), ("agent-revoked", ApprovalStatus.REVOKED)):
        priv = Ed25519PrivateKey.generate()
        seed_agent(session_factory, priv, agent_id, status)
        assert _post(client, agent_id, "psql_manager", exec_body(priv, agent_id, "psql_manager")).status_code == 403
    assert fake_tool_server.calls == []


# ---------- リプレイ防止(nonce) ----------
def test_exec_replayed_request_is_rejected(client, session_factory, fake_tool_server):
    agent_priv, _ = _setup(session_factory)
    body = exec_body(agent_priv, "agent-1", "psql_manager")
    assert _post(client, "agent-1", "psql_manager", body).status_code == 200
    res = _post(client, "agent-1", "psql_manager", body)  # 盗聴した署名付きリクエストの再送
    assert res.status_code == 401
    assert res.json()["detail"] == "nonce has already been used"
    assert len(fake_tool_server.calls) == 1  # 2回目はツールサーバへ中継されない


def test_exec_same_nonce_for_different_agents_is_ok(client, session_factory, fake_tool_server):
    agent_priv, ts_priv = _setup(session_factory, "agent-1")
    agent2_priv = Ed25519PrivateKey.generate()
    seed_agent(session_factory, agent2_priv, "agent-2")
    seed_agent_tool(session_factory, "agent-2", "psql_manager", ts_priv)
    nonce = "shared-nonce-0123456789"
    assert _post(client, "agent-1", "psql_manager", exec_body(agent_priv, "agent-1", "psql_manager", nonce=nonce)).status_code == 200
    assert _post(client, "agent-2", "psql_manager", exec_body(agent2_priv, "agent-2", "psql_manager", nonce=nonce)).status_code == 200


def test_exec_new_nonce_each_time_is_ok(client, session_factory, fake_tool_server):
    agent_priv, _ = _setup(session_factory)
    for _ in range(3):
        assert _post(client, "agent-1", "psql_manager", exec_body(agent_priv, "agent-1", "psql_manager")).status_code == 200


def test_exec_consumes_nonce_even_when_permission_is_denied(client, session_factory, fake_tool_server):
    agent_priv, _ = _setup(session_factory)
    body = exec_body(agent_priv, "agent-1", "no_such_tool")
    assert _post(client, "agent-1", "no_such_tool", body).status_code == 403
    assert _post(client, "agent-1", "no_such_tool", body).status_code == 401  # nonceは消費済み


def test_exec_deletes_expired_nonces(client, session_factory, fake_tool_server):
    from datetime import datetime, timedelta, timezone
    agent_priv, _ = _setup(session_factory)
    with session_factory() as db:
        db.add(TblRequestNonce(agent_id="agent-1", nonce="expired-nonce-0123456789", expires_at=datetime.now(timezone.utc) - timedelta(seconds=1)))
        db.commit()
    assert _post(client, "agent-1", "psql_manager", exec_body(agent_priv, "agent-1", "psql_manager")).status_code == 200
    with session_factory() as db:
        nonces = [n.nonce for n in db.execute(select(TblRequestNonce)).scalars().all()]
    assert "expired-nonce-0123456789" not in nonces  # 期限切れのnonceは削除される
    assert len(nonces) == 1


def test_exec_unauthenticated_requests_do_not_consume_nonce(client, session_factory, fake_tool_server):
    _setup(session_factory)
    attacker = Ed25519PrivateKey.generate()
    assert _post(client, "agent-1", "psql_manager", exec_body(attacker, "agent-1", "psql_manager")).status_code == 401
    with session_factory() as db:
        assert db.execute(select(TblRequestNonce)).scalars().all() == []  # 認証に失敗したリクエストは、nonceを記録しない(DBを肥大化させない)


# ---------- 入力の形式 ----------
def test_exec_invalid_input_is_unprocessable(client, session_factory, fake_tool_server):
    agent_priv, _ = _setup(session_factory)
    for bad_nonce in ("short", "has space 0123456789abc", "x" * 200):
        body = exec_body(agent_priv, "agent-1", "psql_manager", nonce=bad_nonce)
        assert _post(client, "agent-1", "psql_manager", body).status_code == 422, bad_nonce
    body = exec_body(agent_priv, "agent-1", "psql_manager")
    body["unexpected"] = "x"
    assert _post(client, "agent-1", "psql_manager", body).status_code == 422
    body = exec_body(agent_priv, "agent-1", "psql_manager")
    body["params"] = "not-an-object"  # paramsはJSONオブジェクト
    assert _post(client, "agent-1", "psql_manager", body).status_code == 422
    body = exec_body(agent_priv, "agent-1", "psql_manager")
    del body["params"]
    assert _post(client, "agent-1", "psql_manager", body).status_code == 422
    assert fake_tool_server.calls == []

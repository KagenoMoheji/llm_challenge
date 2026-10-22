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
from capass_server.common.config import SIGNATURE_MAX_SKEW_SEC, TOKEN_MAX_AGE_SEC
from capass_server.common.crypto import decrypt_token
from capass_server.models.entities import ApprovalStatus, TblAgentTool, TblRequestNonce
from testlib import chtkn_body, exec_body, seed_agent, seed_agent_tool, seed_tool_server


def _chtkn(client, agent_id, tool_endpoint, body):
    return client.post(f"/api/v1/agents/{agent_id}/chtkn/{tool_endpoint}", json=body)


def _setup(session_factory, status=ApprovalStatus.APPROVED, locked=False):
    """承認済みのAIエージェントと、(指定のステータスの)ツールサーバ、そのツールサーバのツール(トークンは old-token)を用意する。
    (AIエージェントの秘密鍵, ツールサーバの秘密鍵)を返す。"""
    agent_priv, ts_priv = Ed25519PrivateKey.generate(), Ed25519PrivateKey.generate()
    seed_agent(session_factory, agent_priv, "agent-1")
    seed_tool_server(session_factory, ts_priv, status)
    seed_agent_tool(session_factory, "agent-1", "psql_manager", ts_priv, token="old-token", locked=locked)
    return agent_priv, ts_priv


def _row(session_factory, tool_endpoint="psql_manager", agent_id="agent-1"):
    with session_factory() as db:
        return db.execute(select(TblAgentTool).where(TblAgentTool.agent_id == agent_id, TblAgentTool.tool_endpoint == tool_endpoint)).scalar_one()


# ---------- 成功 ----------
def test_chtkn_updates_token_and_updated_at(client, session_factory):
    _, ts_priv = _setup(session_factory)
    before = _row(session_factory)
    res = _chtkn(client, "agent-1", "psql_manager", chtkn_body(ts_priv, "agent-1", "psql_manager", token="new-token-1"))
    assert res.status_code == 200
    data = res.json()
    assert (data["tool_endpoint"], data["agent_id"], data["locked"]) == ("psql_manager", "agent-1", False)
    assert data["token_max_age_sec"] == TOKEN_MAX_AGE_SEC  # ツールサーバが、次の更新までの間隔を決める目安
    assert "tool_proxy_token" not in data and "new-token-1" not in res.text  # トークンは返さない

    after = _row(session_factory)
    assert after.tool_proxy_token_encrypted != "new-token-1" and "new-token-1" not in after.tool_proxy_token_encrypted  # 暗号化して保存
    assert decrypt_token(after.tool_proxy_token_encrypted) == "new-token-1"
    assert decrypt_token(before.tool_proxy_token_encrypted) == "old-token"
    updated_at = after.tool_proxy_token_updated_at if after.tool_proxy_token_updated_at.tzinfo else after.tool_proxy_token_updated_at.replace(tzinfo=timezone.utc)
    assert (datetime.now(timezone.utc) - updated_at).total_seconds() < 60
    assert after.tool_proxy_token_updated_at >= before.tool_proxy_token_updated_at


def test_chtkn_does_not_change_other_columns(client, session_factory):
    _, ts_priv = _setup(session_factory)
    before = _row(session_factory)
    assert _chtkn(client, "agent-1", "psql_manager", chtkn_body(ts_priv, "agent-1", "psql_manager")).status_code == 200
    after = _row(session_factory)
    for column in ("tool_endpoint", "context", "params_schema", "agent_id", "locked", "tool_used_at", "tool_server_public_key", "created_at"):
        assert getattr(after, column) == getattr(before, column), column


def test_chtkn_only_changes_the_specified_tool(client, session_factory):
    _, ts_priv = _setup(session_factory)
    seed_agent_tool(session_factory, "agent-1", "psql_terminal_admin", ts_priv, token="other-old-token")
    assert _chtkn(client, "agent-1", "psql_manager", chtkn_body(ts_priv, "agent-1", "psql_manager", token="new-token")).status_code == 200
    assert decrypt_token(_row(session_factory, "psql_terminal_admin").tool_proxy_token_encrypted) == "other-old-token"


def test_chtkn_can_be_repeated_with_new_nonce(client, session_factory):
    _, ts_priv = _setup(session_factory)
    for i in range(3):  # 定期更新ジョブは、N分ごとに繰り返し呼ぶ
        assert _chtkn(client, "agent-1", "psql_manager", chtkn_body(ts_priv, "agent-1", "psql_manager", token=f"token-{i}")).status_code == 200
    assert decrypt_token(_row(session_factory).tool_proxy_token_encrypted) == "token-2"


def test_exec_uses_the_renewed_token(client, session_factory, fake_tool_server):
    agent_priv, ts_priv = _setup(session_factory)
    assert _chtkn(client, "agent-1", "psql_manager", chtkn_body(ts_priv, "agent-1", "psql_manager", token="renewed-token")).status_code == 200
    res = client.post("/api/v1/agents/agent-1/exec/psql_manager", json=exec_body(agent_priv, "agent-1", "psql_manager"))
    assert res.status_code == 200
    assert fake_tool_server.calls[0]["token"] == "renewed-token"  # ツールサーバへは、更新後のトークンを渡す


def test_chtkn_keeps_locked_tool_locked(client, session_factory):
    _, ts_priv = _setup(session_factory, locked=True)
    res = _chtkn(client, "agent-1", "psql_manager", chtkn_body(ts_priv, "agent-1", "psql_manager", token="new-token"))
    assert res.status_code == 200  # ロック中でも、トークンは更新できる
    assert res.json()["locked"] is True
    row = _row(session_factory)
    assert row.locked is True  # ロックは解除されない(ロックの解除は、別の操作)
    assert decrypt_token(row.tool_proxy_token_encrypted) == "new-token"


# ---------- 署名 ----------
def test_chtkn_tampered_body_is_unauthorized(client, session_factory):
    _, ts_priv = _setup(session_factory)
    body = chtkn_body(ts_priv, "agent-1", "psql_manager", token="new-token")
    body["tool_proxy_token"] = "attacker-token"  # 署名後に、トークンをすり替える
    assert _chtkn(client, "agent-1", "psql_manager", body).status_code == 401
    assert decrypt_token(_row(session_factory).tool_proxy_token_encrypted) == "old-token"


def test_chtkn_signed_for_other_tool_or_agent_is_unauthorized(client, session_factory):
    _, ts_priv = _setup(session_factory)
    seed_agent_tool(session_factory, "agent-1", "psql_terminal_admin", ts_priv)
    seed_agent(session_factory, Ed25519PrivateKey.generate(), "agent-2")
    seed_agent_tool(session_factory, "agent-2", "psql_manager", ts_priv)
    body = chtkn_body(ts_priv, "agent-1", "psql_manager")
    assert _chtkn(client, "agent-1", "psql_terminal_admin", body).status_code == 401  # 別のツールへの使い回し
    assert _chtkn(client, "agent-2", "psql_manager", body).status_code == 401  # 別のAIエージェントへの使い回し


def test_chtkn_expired_signature_is_unauthorized(client, session_factory):
    _, ts_priv = _setup(session_factory)
    body = chtkn_body(ts_priv, "agent-1", "psql_manager", signed_at=int(time.time()) - SIGNATURE_MAX_SKEW_SEC - 60)
    assert _chtkn(client, "agent-1", "psql_manager", body).status_code == 401


def test_chtkn_replay_is_rejected_and_cannot_roll_back_the_token(client, session_factory):
    _, ts_priv = _setup(session_factory)
    first = chtkn_body(ts_priv, "agent-1", "psql_manager", token="token-1")
    assert _chtkn(client, "agent-1", "psql_manager", first).status_code == 200
    assert _chtkn(client, "agent-1", "psql_manager", chtkn_body(ts_priv, "agent-1", "psql_manager", token="token-2")).status_code == 200
    res = _chtkn(client, "agent-1", "psql_manager", first)  # 盗聴した古い更新リクエストの再送
    assert res.status_code == 401
    assert res.json()["detail"] == "nonce has already been used"
    assert decrypt_token(_row(session_factory).tool_proxy_token_encrypted) == "token-2"  # 古いトークンに、巻き戻らない


# ---------- 認可(誰が更新できるか) ----------
def test_chtkn_by_unregistered_key_is_forbidden_and_leaks_nothing(client, session_factory):
    _setup(session_factory)
    attacker = Ed25519PrivateKey.generate()  # 署名は正当だが、登録されていない(未承認の)鍵
    for endpoint in ("psql_manager", "no_such_tool"):
        assert _chtkn(client, "agent-1", endpoint, chtkn_body(attacker, "agent-1", endpoint)).status_code == 403  # ツールの有無で、応答が変わらない
    with session_factory() as db:
        assert db.execute(select(TblRequestNonce)).scalars().all() == []  # 認証できない相手のnonceは、記録しない


def test_chtkn_by_other_approved_tool_server_is_not_found(client, session_factory):
    _, ts_priv = _setup(session_factory)
    other_priv = Ed25519PrivateKey.generate()
    seed_tool_server(session_factory, other_priv, name="other-server")  # 承認済みの、別のツールサーバ
    res = _chtkn(client, "agent-1", "psql_manager", chtkn_body(other_priv, "agent-1", "psql_manager", token="attacker-token"))
    assert res.status_code == 404  # 他のツールサーバのツールは、更新できない(「存在しない」と同じ扱い)
    assert decrypt_token(_row(session_factory).tool_proxy_token_encrypted) == "old-token"


def test_chtkn_unknown_tool_or_agent_is_not_found(client, session_factory):
    _, ts_priv = _setup(session_factory)
    assert _chtkn(client, "agent-1", "no_such_tool", chtkn_body(ts_priv, "agent-1", "no_such_tool")).status_code == 404
    assert _chtkn(client, "nobody", "psql_manager", chtkn_body(ts_priv, "nobody", "psql_manager")).status_code == 404


def test_chtkn_pending_or_revoked_tool_server_is_forbidden(client, session_factory):
    for status in (ApprovalStatus.PENDING, ApprovalStatus.REVOKED):
        agent_priv, ts_priv = Ed25519PrivateKey.generate(), Ed25519PrivateKey.generate()
        agent_id = f"agent-{status.value}"
        seed_agent(session_factory, agent_priv, agent_id)
        seed_tool_server(session_factory, ts_priv, status, name=f"server-{status.value}")
        seed_agent_tool(session_factory, agent_id, "psql_manager", ts_priv, token="old-token")
        res = _chtkn(client, agent_id, "psql_manager", chtkn_body(ts_priv, agent_id, "psql_manager"))
        assert res.status_code == 403, status  # 承認が取り消されたツールサーバは、更新できない
        assert decrypt_token(_row(session_factory, agent_id=agent_id).tool_proxy_token_encrypted) == "old-token"


# ---------- 入力の形式 ----------
def test_chtkn_invalid_input_is_unprocessable(client, session_factory):
    _, ts_priv = _setup(session_factory)
    body = chtkn_body(ts_priv, "agent-1", "psql_manager")
    assert _chtkn(client, "agent-1", "psql_manager", {**body, "tool_proxy_token": ""}).status_code == 422
    assert _chtkn(client, "agent-1", "psql_manager", {**body, "nonce": "short"}).status_code == 422
    assert _chtkn(client, "agent-1", "psql_manager", {**body, "tool_server_public_key": "not-a-valid-key"}).status_code == 422
    assert _chtkn(client, "agent-1", "psql_manager", {**body, "unexpected": "x"}).status_code == 422
    for missing in ("tool_proxy_token", "tool_server_public_key", "nonce", "signed_at", "signature"):
        assert _chtkn(client, "agent-1", "psql_manager", {k: v for k, v in body.items() if k != missing}).status_code == 422, missing

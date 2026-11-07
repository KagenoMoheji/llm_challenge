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
from capass_server.models.entities import ApprovalStatus, TblRequestNonce, TblTool
from testlib import chtkn_body, exec_body, seed_agent, seed_agent_tool, seed_tool_server


def _chtkn(client, tool_endpoint, body):
    return client.post(f"/api/v1/tools/{tool_endpoint}/chtkn", json=body)


def _setup(session_factory, status=ApprovalStatus.APPROVED, locked=False):
    """(指定のステータスの)ツールサーバと、そのツール psql_manager(トークンは old-token)と、そのツールを割り当てられたAIエージェント2つを用意する。
    (ツールサーバの秘密鍵, {agent_id: AIエージェントの秘密鍵})を返す。"""
    ts_priv = Ed25519PrivateKey.generate()
    seed_tool_server(session_factory, ts_priv, status)
    agents = {}
    for agent_id in ("agent-1", "agent-2"):
        agents[agent_id] = Ed25519PrivateKey.generate()
        seed_agent(session_factory, agents[agent_id], agent_id)
        seed_agent_tool(session_factory, agent_id, "psql_manager", ts_priv, token="old-token", locked=locked)
    return ts_priv, agents


def _tool(session_factory, tool_endpoint="psql_manager"):
    with session_factory() as db:
        return db.execute(select(TblTool).where(TblTool.tool_endpoint == tool_endpoint)).scalar_one()


# ---------- 成功 ----------
def test_chtkn_updates_token_and_updated_at(client, session_factory):
    ts_priv, _ = _setup(session_factory)
    before = _tool(session_factory)
    res = _chtkn(client, "psql_manager", chtkn_body(ts_priv, "psql_manager", token="new-token-1"))
    assert res.status_code == 200
    data = res.json()
    assert (data["tool_endpoint"], data["locked"]) == ("psql_manager", False)
    assert data["token_max_age_sec"] == TOKEN_MAX_AGE_SEC  # ツールサーバが、次の更新までの間隔を決める目安
    assert "tool_proxy_token" not in data and "new-token-1" not in res.text  # トークンは返さない

    after = _tool(session_factory)
    assert after.tool_proxy_token_encrypted != "new-token-1" and "new-token-1" not in after.tool_proxy_token_encrypted  # 暗号化して保存
    assert decrypt_token(after.tool_proxy_token_encrypted) == "new-token-1"
    assert decrypt_token(before.tool_proxy_token_encrypted) == "old-token"
    updated_at = after.tool_proxy_token_updated_at if after.tool_proxy_token_updated_at.tzinfo else after.tool_proxy_token_updated_at.replace(tzinfo=timezone.utc)
    assert (datetime.now(timezone.utc) - updated_at).total_seconds() < 60
    assert after.tool_proxy_token_updated_at >= before.tool_proxy_token_updated_at


def test_one_chtkn_updates_the_token_for_all_agents_of_the_tool(client, session_factory, fake_tool_server):
    ts_priv, agents = _setup(session_factory)
    assert _chtkn(client, "psql_manager", chtkn_body(ts_priv, "psql_manager", token="renewed-token")).status_code == 200  # 1回の更新で
    for agent_id, priv in agents.items():  # ツールを割り当てられた、全てのAIエージェントに反映される(ロール単位のトークン)
        assert client.post(f"/api/v1/agents/{agent_id}/exec/psql_manager", json=exec_body(priv, agent_id, "psql_manager")).status_code == 200
    assert [c["token"] for c in fake_tool_server.calls] == ["renewed-token", "renewed-token"]


def test_chtkn_does_not_change_other_columns(client, session_factory):
    ts_priv, _ = _setup(session_factory)
    before = _tool(session_factory)
    assert _chtkn(client, "psql_manager", chtkn_body(ts_priv, "psql_manager")).status_code == 200
    after = _tool(session_factory)
    for column in ("tool_endpoint", "context", "params_schema", "tool_server_id", "locked", "created_at"):
        assert getattr(after, column) == getattr(before, column), column


def test_chtkn_only_changes_the_specified_tool(client, session_factory):
    ts_priv, _ = _setup(session_factory)
    seed_agent_tool(session_factory, "agent-1", "psql_terminal_admin", ts_priv, token="other-old-token")
    assert _chtkn(client, "psql_manager", chtkn_body(ts_priv, "psql_manager", token="new-token")).status_code == 200
    assert decrypt_token(_tool(session_factory, "psql_terminal_admin").tool_proxy_token_encrypted) == "other-old-token"


def test_chtkn_can_be_repeated_with_new_nonce(client, session_factory):
    ts_priv, _ = _setup(session_factory)
    for i in range(3):  # 定期更新ジョブは、N分ごとに繰り返し呼ぶ
        assert _chtkn(client, "psql_manager", chtkn_body(ts_priv, "psql_manager", token=f"token-{i}")).status_code == 200
    assert decrypt_token(_tool(session_factory).tool_proxy_token_encrypted) == "token-2"


def test_chtkn_keeps_locked_tool_locked(client, session_factory):
    ts_priv, _ = _setup(session_factory, locked=True)
    res = _chtkn(client, "psql_manager", chtkn_body(ts_priv, "psql_manager", token="new-token"))
    assert res.status_code == 200  # ロック中でも、トークンは更新できる
    assert res.json()["locked"] is True
    row = _tool(session_factory)
    assert row.locked is True  # ロックは解除されない(ロックの解除は、別の操作)
    assert decrypt_token(row.tool_proxy_token_encrypted) == "new-token"


# ---------- 署名 ----------
def test_chtkn_tampered_body_is_unauthorized(client, session_factory):
    ts_priv, _ = _setup(session_factory)
    body = chtkn_body(ts_priv, "psql_manager", token="new-token")
    body["tool_proxy_token"] = "attacker-token"  # 署名後に、トークンをすり替える
    assert _chtkn(client, "psql_manager", body).status_code == 401
    assert decrypt_token(_tool(session_factory).tool_proxy_token_encrypted) == "old-token"


def test_chtkn_signed_for_other_tool_is_unauthorized(client, session_factory):
    ts_priv, _ = _setup(session_factory)
    seed_agent_tool(session_factory, "agent-1", "psql_terminal_admin", ts_priv)
    assert _chtkn(client, "psql_terminal_admin", chtkn_body(ts_priv, "psql_manager")).status_code == 401  # 別のツールへの使い回し


def test_chtkn_expired_signature_is_unauthorized(client, session_factory):
    ts_priv, _ = _setup(session_factory)
    body = chtkn_body(ts_priv, "psql_manager", signed_at=int(time.time()) - SIGNATURE_MAX_SKEW_SEC - 60)
    assert _chtkn(client, "psql_manager", body).status_code == 401


def test_chtkn_replay_is_rejected_and_cannot_roll_back_the_token(client, session_factory):
    ts_priv, _ = _setup(session_factory)
    first = chtkn_body(ts_priv, "psql_manager", token="token-1")
    assert _chtkn(client, "psql_manager", first).status_code == 200
    assert _chtkn(client, "psql_manager", chtkn_body(ts_priv, "psql_manager", token="token-2")).status_code == 200
    res = _chtkn(client, "psql_manager", first)  # 盗聴した古い更新リクエストの再送
    assert res.status_code == 401
    assert res.json()["detail"] == "nonce has already been used"
    assert decrypt_token(_tool(session_factory).tool_proxy_token_encrypted) == "token-2"  # 古いトークンに、巻き戻らない


# ---------- 認可(誰が更新できるか) ----------
def test_chtkn_by_unregistered_key_is_forbidden_and_leaks_nothing(client, session_factory):
    _setup(session_factory)
    attacker = Ed25519PrivateKey.generate()  # 署名は正当だが、登録されていない(未承認の)鍵
    for endpoint in ("psql_manager", "no_such_tool"):
        assert _chtkn(client, endpoint, chtkn_body(attacker, endpoint)).status_code == 403  # ツールの有無で、応答が変わらない
    with session_factory() as db:
        assert db.execute(select(TblRequestNonce)).scalars().all() == []  # 認証できない相手のnonceは、記録しない


def test_chtkn_by_other_approved_tool_server_is_not_found(client, session_factory):
    _setup(session_factory)
    other_priv = Ed25519PrivateKey.generate()
    seed_tool_server(session_factory, other_priv, name="other-server")  # 承認済みの、別のツールサーバ
    res = _chtkn(client, "psql_manager", chtkn_body(other_priv, "psql_manager", token="attacker-token"))
    assert res.status_code == 404  # 他のツールサーバのツールは、更新できない(「存在しない」と同じ扱い)
    assert decrypt_token(_tool(session_factory).tool_proxy_token_encrypted) == "old-token"


def test_chtkn_unknown_tool_is_not_found(client, session_factory):
    ts_priv, _ = _setup(session_factory)
    assert _chtkn(client, "no_such_tool", chtkn_body(ts_priv, "no_such_tool")).status_code == 404


def test_chtkn_pending_revoked_reserved_or_standby_tool_server_is_forbidden(client, session_factory):
    for status in (ApprovalStatus.PENDING, ApprovalStatus.REVOKED, ApprovalStatus.RESERVED, ApprovalStatus.STANDBY):
        ts_priv = Ed25519PrivateKey.generate()
        seed_tool_server(session_factory, ts_priv, status, name=f"server-{status.value}", expires_in_sec=3600)
        endpoint = f"tool_{status.value}"
        seed_agent(session_factory, Ed25519PrivateKey.generate(), f"agent-{status.value}")
        seed_agent_tool(session_factory, f"agent-{status.value}", endpoint, ts_priv, token="old-token")
        assert _chtkn(client, endpoint, chtkn_body(ts_priv, endpoint)).status_code == 403, status  # アクティブ(承認済み)なツールサーバだけが、更新できる
        assert decrypt_token(_tool(session_factory, endpoint).tool_proxy_token_encrypted) == "old-token"


# ---------- 入力の形式 ----------
def test_chtkn_invalid_input_is_unprocessable(client, session_factory):
    ts_priv, _ = _setup(session_factory)
    body = chtkn_body(ts_priv, "psql_manager")
    assert _chtkn(client, "psql_manager", {**body, "tool_proxy_token": ""}).status_code == 422
    assert _chtkn(client, "psql_manager", {**body, "nonce": "short"}).status_code == 422
    assert _chtkn(client, "psql_manager", {**body, "tool_server_public_key": "not-a-valid-key"}).status_code == 422
    assert _chtkn(client, "psql_manager", {**body, "unexpected": "x"}).status_code == 422
    for missing in ("tool_proxy_token", "tool_server_public_key", "nonce", "signed_at", "signature"):
        assert _chtkn(client, "psql_manager", {k: v for k, v in body.items() if k != missing}).status_code == 422, missing

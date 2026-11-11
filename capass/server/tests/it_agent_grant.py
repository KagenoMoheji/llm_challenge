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
from capass_server.common.signature import SIGN_CONTEXT_AGENT_GRANT_APPROVE
from capass_server.models.entities import ApprovalStatus, TblAgentTool, TblTool, TblToolServer
from testlib import (
    ADMIN_EMAIL,
    APPLICANT_EMAIL,
    approve_body,
    exec_body,
    grant_body,
    list_tools_headers,
    revoke_body,
    seed_admin,
    seed_agent,
    seed_agent_tool,
    seed_tool,
    seed_tool_server,
)


def _grant(client, agent_id, tool_endpoint, body):
    return client.post(f"/api/v1/agents/{agent_id}/grant/{tool_endpoint}", json=body)


def _approve(client, agent_id, tool_endpoint, body):
    return client.post(f"/api/v1/agents/{agent_id}/grant/{tool_endpoint}/approve", json=body)


def _revoke(client, agent_id, tool_endpoint, body):
    return client.post(f"/api/v1/agents/{agent_id}/revoke/{tool_endpoint}", json=body)


def _approve_body(admin_priv, agent_id, tool_endpoint, signed_at=None):
    return approve_body(admin_priv, SIGN_CONTEXT_AGENT_GRANT_APPROVE, {"agent_id": agent_id, "tool_endpoint": tool_endpoint}, signed_at)


def _setup(session_factory):
    """承認済みのAIエージェント(agent-1)と、承認済みツールサーバのツール(psql_manager)を用意する。(AIエージェントの秘密鍵, ツールサーバの秘密鍵)を返す。"""
    agent_priv, ts_priv = Ed25519PrivateKey.generate(), Ed25519PrivateKey.generate()
    seed_agent(session_factory, agent_priv, "agent-1")
    ts_id = seed_tool_server(session_factory, ts_priv)
    seed_tool(session_factory, "psql_manager", ts_id, token="proxy-token-1")
    return agent_priv, ts_priv


def _tool_server_id(session_factory):
    with session_factory() as db:
        return db.execute(select(TblToolServer.id)).scalars().first()


def _grant_row(session_factory, agent_id="agent-1", tool_endpoint="psql_manager"):
    with session_factory() as db:
        stmt = select(TblAgentTool).join(TblTool, TblTool.id == TblAgentTool.tool_id).where(TblAgentTool.agent_id == agent_id, TblTool.tool_endpoint == tool_endpoint)
        return db.execute(stmt).scalar_one_or_none()


# ---------- grant(申請) ----------
def test_grant_creates_pending_request_and_tool_is_not_usable_yet(client, session_factory, fake_tool_server):
    agent_priv, _ = _setup(session_factory)
    res = _grant(client, "agent-1", "psql_manager", grant_body(agent_priv, "agent-1", "psql_manager"))
    assert res.status_code == 201
    data = res.json()
    assert (data["agent_id"], data["tool_endpoint"], data["status"], data["applicant_email"]) == ("agent-1", "psql_manager", "pending", APPLICANT_EMAIL)
    row = _grant_row(session_factory)
    assert (row.status, row.approver_email, row.approved_at, row.locked, row.tool_used_at) == (ApprovalStatus.PENDING, None, None, False, None)
    # 承認されるまでは、一覧に出ず、実行もできない
    assert client.get("/api/v1/agents/agent-1/tools", headers=list_tools_headers(agent_priv, "agent-1")).json()["tools"] == []
    assert client.post("/api/v1/agents/agent-1/exec/psql_manager", json=exec_body(agent_priv, "agent-1", "psql_manager")).status_code == 403
    assert fake_tool_server.calls == []


def test_grant_then_approve_makes_the_tool_usable(client, session_factory, fake_tool_server, admin_priv):
    agent_priv, _ = _setup(session_factory)
    assert _grant(client, "agent-1", "psql_manager", grant_body(agent_priv, "agent-1", "psql_manager")).status_code == 201
    res = _approve(client, "agent-1", "psql_manager", _approve_body(admin_priv, "agent-1", "psql_manager"))
    assert res.status_code == 200
    data = res.json()
    assert (data["status"], data["approver_email"], data["applicant_email"]) == ("approved", ADMIN_EMAIL, APPLICANT_EMAIL)
    row = _grant_row(session_factory)
    assert (row.status, row.approver_email) == (ApprovalStatus.APPROVED, ADMIN_EMAIL)
    assert row.approved_at is not None
    tools = client.get("/api/v1/agents/agent-1/tools", headers=list_tools_headers(agent_priv, "agent-1")).json()["tools"]
    assert [t["tool_endpoint"] for t in tools] == ["psql_manager"]
    assert client.post("/api/v1/agents/agent-1/exec/psql_manager", json=exec_body(agent_priv, "agent-1", "psql_manager")).status_code == 200


def test_grant_duplicate_request_is_conflict(client, session_factory, admin_priv):
    agent_priv, _ = _setup(session_factory)
    assert _grant(client, "agent-1", "psql_manager", grant_body(agent_priv, "agent-1", "psql_manager")).status_code == 201
    assert _grant(client, "agent-1", "psql_manager", grant_body(agent_priv, "agent-1", "psql_manager")).status_code == 409  # 申請中
    assert _approve(client, "agent-1", "psql_manager", _approve_body(admin_priv, "agent-1", "psql_manager")).status_code == 200
    assert _grant(client, "agent-1", "psql_manager", grant_body(agent_priv, "agent-1", "psql_manager")).status_code == 409  # 承認済み


def test_grant_can_be_requested_again_after_revoke(client, session_factory, admin_priv):
    agent_priv, _ = _setup(session_factory)
    assert _grant(client, "agent-1", "psql_manager", grant_body(agent_priv, "agent-1", "psql_manager")).status_code == 201
    assert _approve(client, "agent-1", "psql_manager", _approve_body(admin_priv, "agent-1", "psql_manager")).status_code == 200
    assert _revoke(client, "agent-1", "psql_manager", revoke_body(admin_priv, "agent-1", "psql_manager")).status_code == 200
    res = _grant(client, "agent-1", "psql_manager", grant_body(agent_priv, "agent-1", "psql_manager", email="new-applicant@example.com"))
    assert res.status_code == 201  # 取り消された割り当ては、再申請できる
    row = _grant_row(session_factory)
    assert (row.status, row.applicant_email, row.approver_email, row.approved_at) == (ApprovalStatus.PENDING, "new-applicant@example.com", None, None)  # 承認は、やり直し


def test_one_tool_can_be_granted_to_many_agents(client, session_factory, admin_priv):
    agent_priv, _ = _setup(session_factory)
    agent2_priv = Ed25519PrivateKey.generate()
    seed_agent(session_factory, agent2_priv, "agent-2")
    for agent_id, priv in (("agent-1", agent_priv), ("agent-2", agent2_priv)):
        assert _grant(client, agent_id, "psql_manager", grant_body(priv, agent_id, "psql_manager")).status_code == 201
        assert _approve(client, agent_id, "psql_manager", _approve_body(admin_priv, agent_id, "psql_manager")).status_code == 200
    with session_factory() as db:
        assert len(db.execute(select(TblTool)).scalars().all()) == 1  # ツール(トークン)は1つ
        assert len(db.execute(select(TblAgentTool)).scalars().all()) == 2  # 割り当ては、AIエージェントごと


def test_grant_unknown_tool_or_tool_of_unapproved_server_is_not_found(client, session_factory):
    agent_priv, _ = _setup(session_factory)
    assert _grant(client, "agent-1", "no_such_tool", grant_body(agent_priv, "agent-1", "no_such_tool")).status_code == 404
    revoked_priv = Ed25519PrivateKey.generate()
    revoked_id = seed_tool_server(session_factory, revoked_priv, ApprovalStatus.REVOKED, name="revoked-server")
    seed_tool(session_factory, "tool_of_revoked", revoked_id)
    assert _grant(client, "agent-1", "tool_of_revoked", grant_body(agent_priv, "agent-1", "tool_of_revoked")).status_code == 404  # 承認が取り消されたツールサーバのツールは、存在しないものとして扱う


def test_grant_authentication_and_agent_status(client, session_factory):
    agent_priv, _ = _setup(session_factory)
    attacker = Ed25519PrivateKey.generate()
    assert _grant(client, "agent-1", "psql_manager", grant_body(attacker, "agent-1", "psql_manager")).status_code == 401  # agent_idを知っていても、秘密鍵が無ければ申請できない
    assert _grant(client, "nobody", "psql_manager", grant_body(attacker, "nobody", "psql_manager")).status_code == 401  # 存在しないagent_idは、署名不正と区別しない
    body = grant_body(agent_priv, "agent-1", "psql_manager")
    body["applicant_email"] = "evil@example.com"  # 署名後に改ざん
    assert _grant(client, "agent-1", "psql_manager", body).status_code == 401
    assert _grant(client, "agent-1", "psql_manager", grant_body(agent_priv, "agent-1", "psql_manager", signed_at=int(time.time()) - SIGNATURE_MAX_SKEW_SEC - 60)).status_code == 401
    seed_agent(session_factory, Ed25519PrivateKey.generate(), "agent-other")
    assert _grant(client, "agent-other", "psql_manager", grant_body(agent_priv, "agent-1", "psql_manager")).status_code == 401  # 別のAIエージェント向けの署名の使い回し
    seed_tool(session_factory, "other_tool", _tool_server_id(session_factory))
    assert _grant(client, "agent-1", "other_tool", grant_body(agent_priv, "agent-1", "psql_manager")).status_code == 401  # 別のツール向けの署名の使い回し
    for status in (ApprovalStatus.PENDING, ApprovalStatus.REVOKED):  # 承認されていないAIエージェントは、申請できない
        priv = Ed25519PrivateKey.generate()
        agent_id = f"agent-{status.value}"
        seed_agent(session_factory, priv, agent_id, status)
        assert _grant(client, agent_id, "psql_manager", grant_body(priv, agent_id, "psql_manager")).status_code == 403, status


def test_grant_invalid_input_is_unprocessable(client, session_factory):
    agent_priv, _ = _setup(session_factory)
    body = grant_body(agent_priv, "agent-1", "psql_manager")
    for bad in ("not-an-email", "a@b", ""):
        assert _grant(client, "agent-1", "psql_manager", grant_body(agent_priv, "agent-1", "psql_manager", email=bad)).status_code == 422, bad
    assert _grant(client, "agent-1", "psql_manager", {**body, "unexpected": "x"}).status_code == 422
    assert _grant(client, "agent-1", "psql_manager", {k: v for k, v in body.items() if k != "applicant_email"}).status_code == 422


# ---------- approve(承認) ----------
def test_approve_is_idempotent_and_keeps_first_approver(client, session_factory, admin_priv):
    agent_priv, _ = _setup(session_factory)
    assert _grant(client, "agent-1", "psql_manager", grant_body(agent_priv, "agent-1", "psql_manager")).status_code == 201
    assert _approve(client, "agent-1", "psql_manager", _approve_body(admin_priv, "agent-1", "psql_manager")).status_code == 200
    second_admin = Ed25519PrivateKey.generate()
    seed_admin(session_factory, second_admin, email="second-admin@example.com")
    res = _approve(client, "agent-1", "psql_manager", _approve_body(second_admin, "agent-1", "psql_manager"))
    assert res.status_code == 200
    assert res.json()["approver_email"] == ADMIN_EMAIL  # 2回目の承認では、最初の承認者が書き換わらない


def test_approve_by_non_admin_or_inactive_admin_is_forbidden(client, session_factory, admin_priv):
    agent_priv, _ = _setup(session_factory)
    assert _grant(client, "agent-1", "psql_manager", grant_body(agent_priv, "agent-1", "psql_manager")).status_code == 201
    assert _approve(client, "agent-1", "psql_manager", _approve_body(Ed25519PrivateKey.generate(), "agent-1", "psql_manager")).status_code == 403  # tbl_adminに無い鍵
    assert _approve(client, "agent-1", "psql_manager", _approve_body(agent_priv, "agent-1", "psql_manager")).status_code == 403  # 申請者自身(AIエージェントの鍵)は、承認できない
    inactive = Ed25519PrivateKey.generate()
    seed_admin(session_factory, inactive, email="inactive@example.com", is_active=False)
    assert _approve(client, "agent-1", "psql_manager", _approve_body(inactive, "agent-1", "psql_manager")).status_code == 403
    assert _grant_row(session_factory).status == ApprovalStatus.PENDING


def test_approve_unknown_grant_tool_or_revoked_state(client, session_factory, admin_priv):
    agent_priv, _ = _setup(session_factory)
    assert _approve(client, "agent-1", "psql_manager", _approve_body(admin_priv, "agent-1", "psql_manager")).status_code == 404  # 申請が無い
    assert _approve(client, "agent-1", "no_such_tool", _approve_body(admin_priv, "agent-1", "no_such_tool")).status_code == 404  # ツールが無い
    assert _grant(client, "agent-1", "psql_manager", grant_body(agent_priv, "agent-1", "psql_manager")).status_code == 201
    assert _approve(client, "agent-1", "psql_manager", _approve_body(admin_priv, "agent-1", "psql_manager")).status_code == 200
    assert _revoke(client, "agent-1", "psql_manager", revoke_body(admin_priv, "agent-1", "psql_manager")).status_code == 200
    assert _approve(client, "agent-1", "psql_manager", _approve_body(admin_priv, "agent-1", "psql_manager")).status_code == 409  # 取り消された割り当ては、承認できない(再申請が必要)


def test_approve_signature_checks(client, session_factory, admin_priv):
    agent_priv, ts_priv = _setup(session_factory)
    seed_agent_tool(session_factory, "agent-1", "other_tool", ts_priv, grant_status=ApprovalStatus.PENDING)
    assert _grant(client, "agent-1", "psql_manager", grant_body(agent_priv, "agent-1", "psql_manager")).status_code == 201
    assert _approve(client, "agent-1", "psql_manager", _approve_body(admin_priv, "agent-1", "other_tool")).status_code == 401  # 別のツール向けの署名の使い回し
    assert _approve(client, "agent-1", "psql_manager", _approve_body(admin_priv, "agent-2", "psql_manager")).status_code == 401  # 別のAIエージェント向けの署名の使い回し
    expired = _approve_body(admin_priv, "agent-1", "psql_manager", signed_at=int(time.time()) - SIGNATURE_MAX_SKEW_SEC - 60)
    assert _approve(client, "agent-1", "psql_manager", expired).status_code == 401
    assert _grant_row(session_factory).status == ApprovalStatus.PENDING


# ---------- revoke(取り消し) ----------
def _approved_grant(client, session_factory, admin_priv):
    agent_priv, ts_priv = _setup(session_factory)
    assert _grant(client, "agent-1", "psql_manager", grant_body(agent_priv, "agent-1", "psql_manager")).status_code == 201
    assert _approve(client, "agent-1", "psql_manager", _approve_body(admin_priv, "agent-1", "psql_manager")).status_code == 200
    return agent_priv, ts_priv


def test_revoke_by_admin_stops_the_tool(client, session_factory, fake_tool_server, admin_priv):
    agent_priv, _ = _approved_grant(client, session_factory, admin_priv)
    res = _revoke(client, "agent-1", "psql_manager", revoke_body(admin_priv, "agent-1", "psql_manager"))
    assert res.status_code == 200
    assert res.json()["status"] == "revoked"
    assert client.get("/api/v1/agents/agent-1/tools", headers=list_tools_headers(agent_priv, "agent-1")).json()["tools"] == []
    assert client.post("/api/v1/agents/agent-1/exec/psql_manager", json=exec_body(agent_priv, "agent-1", "psql_manager")).status_code == 403
    assert fake_tool_server.calls == []


def test_revoke_by_the_tool_owner_server(client, session_factory, admin_priv):
    _, ts_priv = _approved_grant(client, session_factory, admin_priv)
    assert _revoke(client, "agent-1", "psql_manager", revoke_body(ts_priv, "agent-1", "psql_manager")).status_code == 200  # ツールの所有者(ツールサーバ)は、自分のツールの割り当てを、取り消せる
    assert _grant_row(session_factory).status == ApprovalStatus.REVOKED


def test_revoke_is_idempotent_and_does_not_change_other_grants(client, session_factory, admin_priv):
    _, ts_priv = _approved_grant(client, session_factory, admin_priv)
    seed_agent(session_factory, Ed25519PrivateKey.generate(), "agent-2")
    seed_agent_tool(session_factory, "agent-2", "psql_manager", ts_priv)
    assert _revoke(client, "agent-1", "psql_manager", revoke_body(admin_priv, "agent-1", "psql_manager")).status_code == 200
    assert _revoke(client, "agent-1", "psql_manager", revoke_body(admin_priv, "agent-1", "psql_manager")).status_code == 200
    assert _grant_row(session_factory, "agent-2").status == ApprovalStatus.APPROVED  # 他のAIエージェントへの割り当ては、そのまま


def test_revoke_by_unauthorized_signers_is_forbidden_and_leaks_nothing(client, session_factory, admin_priv):
    agent_priv, _ = _approved_grant(client, session_factory, admin_priv)
    other_server = Ed25519PrivateKey.generate()
    seed_tool_server(session_factory, other_server, name="other-server")  # 承認済みだが、このツールの所有者ではないツールサーバ
    for signer in (other_server, agent_priv, Ed25519PrivateKey.generate()):  # 別のツールサーバ、AIエージェント自身、無関係の鍵
        for endpoint in ("psql_manager", "no_such_tool"):
            assert _revoke(client, "agent-1", endpoint, revoke_body(signer, "agent-1", endpoint)).status_code == 403  # ツールの有無で、応答が変わらない
    assert _grant_row(session_factory).status == ApprovalStatus.APPROVED
    inactive = Ed25519PrivateKey.generate()
    seed_admin(session_factory, inactive, email="inactive@example.com", is_active=False)
    assert _revoke(client, "agent-1", "psql_manager", revoke_body(inactive, "agent-1", "psql_manager")).status_code == 403


def test_revoke_unknown_grant_or_tool_is_not_found_for_authorized_signers(client, session_factory, admin_priv):
    _, ts_priv = _setup(session_factory)
    assert _revoke(client, "agent-1", "psql_manager", revoke_body(admin_priv, "agent-1", "psql_manager")).status_code == 404  # 割り当てが無い
    assert _revoke(client, "agent-1", "psql_manager", revoke_body(ts_priv, "agent-1", "psql_manager")).status_code == 404
    assert _revoke(client, "agent-1", "no_such_tool", revoke_body(admin_priv, "agent-1", "no_such_tool")).status_code == 404  # 管理者には、ツールが無いことも伝える


def test_revoke_signature_checks(client, session_factory, admin_priv):
    _approved_grant(client, session_factory, admin_priv)
    body = revoke_body(admin_priv, "agent-1", "psql_manager")
    assert _revoke(client, "agent-1", "psql_manager", {**body, "signer_public_key": "not-a-valid-key"}).status_code == 422
    assert _revoke(client, "agent-2", "psql_manager", body).status_code == 401  # 別のAIエージェント向けの署名の使い回し
    assert _revoke(client, "agent-1", "other_tool", body).status_code == 401  # 別のツール向けの署名の使い回し
    expired = revoke_body(admin_priv, "agent-1", "psql_manager", signed_at=int(time.time()) - SIGNATURE_MAX_SKEW_SEC - 60)
    assert _revoke(client, "agent-1", "psql_manager", expired).status_code == 401
    forged = {**body, "signer_public_key": revoke_body(Ed25519PrivateKey.generate(), "agent-1", "psql_manager")["signer_public_key"]}  # 管理者の署名を、別の鍵の署名に見せかける
    assert _revoke(client, "agent-1", "psql_manager", forged).status_code == 401
    assert _grant_row(session_factory).status == ApprovalStatus.APPROVED

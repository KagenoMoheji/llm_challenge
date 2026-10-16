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
from capass_server.common.signature import SIGN_CONTEXT_AGENT_APPROVE
from capass_server.models.entities import ApprovalStatus, TblAgent
from testlib import ADMIN_EMAIL, APPLICANT_EMAIL, agent_register_body, approve_body, pub_b64, seed_admin, seed_agent

REGISTER_PATH = "/api/v1/agents/register"


def _approve_path(agent_id):
    return f"/api/v1/agents/{agent_id}/approve"


def _approve_body(admin_priv, agent_id, signed_at=None):
    return approve_body(admin_priv, SIGN_CONTEXT_AGENT_APPROVE, {"agent_id": agent_id}, signed_at)


# ---------- agents/register ----------
def test_register_ok_is_pending(client, session_factory):
    priv = Ed25519PrivateKey.generate()
    res = client.post(REGISTER_PATH, json=agent_register_body(priv))
    assert res.status_code == 201
    data = res.json()
    assert data["agent_id"] == "agent-1"
    assert data["status"] == "pending"
    assert data["applicant_email"] == APPLICANT_EMAIL
    with session_factory() as db:
        row = db.execute(select(TblAgent)).scalar_one()
        assert row.agent_public_key == pub_b64(priv)
        assert row.status == ApprovalStatus.PENDING
        assert row.applicant_email == APPLICANT_EMAIL
        assert row.approver_email is None
        assert row.approved_at is None


def test_register_duplicate_agent_id_is_conflict(client):
    priv = Ed25519PrivateKey.generate()
    assert client.post(REGISTER_PATH, json=agent_register_body(priv)).status_code == 201
    assert client.post(REGISTER_PATH, json=agent_register_body(priv)).status_code == 409  # リプレイも409
    other = Ed25519PrivateKey.generate()
    assert client.post(REGISTER_PATH, json=agent_register_body(other)).status_code == 409  # 別の鍵でも、同じagent_idは登録できない


def test_register_duplicate_public_key_is_conflict(client):
    priv = Ed25519PrivateKey.generate()
    assert client.post(REGISTER_PATH, json=agent_register_body(priv, agent_id="agent-1")).status_code == 201
    assert client.post(REGISTER_PATH, json=agent_register_body(priv, agent_id="agent-2")).status_code == 409  # 1つの鍵は1つのagentにのみ紐づく


def test_register_tampered_body_is_unauthorized(client):
    priv = Ed25519PrivateKey.generate()
    body = agent_register_body(priv)
    body["agent_id"] = "agent-evil"  # 署名後に改ざん
    assert client.post(REGISTER_PATH, json=body).status_code == 401
    body = agent_register_body(priv)
    body["applicant_email"] = "evil@example.com"  # メアドも署名対象
    assert client.post(REGISTER_PATH, json=body).status_code == 401


def test_register_expired_signature_is_unauthorized(client):
    priv = Ed25519PrivateKey.generate()
    body = agent_register_body(priv, signed_at=int(time.time()) - SIGNATURE_MAX_SKEW_SEC - 60)
    assert client.post(REGISTER_PATH, json=body).status_code == 401


def test_register_invalid_input_is_unprocessable(client):
    priv = Ed25519PrivateKey.generate()
    body = agent_register_body(priv, agent_id="bad/agent id")  # 使えない文字(スペース、スラッシュ)
    assert client.post(REGISTER_PATH, json=body).status_code == 422
    body = agent_register_body(priv)
    body["agent_public_key"] = "not-a-valid-key"
    assert client.post(REGISTER_PATH, json=body).status_code == 422
    body = agent_register_body(priv)
    del body["applicant_email"]  # 申請者メアドは必須
    assert client.post(REGISTER_PATH, json=body).status_code == 422


def test_register_invalid_email_is_unprocessable(client):
    priv = Ed25519PrivateKey.generate()
    for bad in ("not-an-email", "a@b", "a b@example.com", "@example.com", ""):
        assert client.post(REGISTER_PATH, json=agent_register_body(priv, email=bad)).status_code == 422, bad


# ---------- agents/{agent_id}/approve ----------
def test_approve_ok_records_approver_email(client, session_factory, admin_priv):
    seed_agent(session_factory, Ed25519PrivateKey.generate(), "agent-1", ApprovalStatus.PENDING)
    res = client.post(_approve_path("agent-1"), json=_approve_body(admin_priv, "agent-1"))
    assert res.status_code == 200
    data = res.json()
    assert data["status"] == "approved"
    assert data["approver_email"] == ADMIN_EMAIL
    with session_factory() as db:
        row = db.execute(select(TblAgent)).scalar_one()
        assert row.status == ApprovalStatus.APPROVED
        assert row.approved_at is not None
        assert row.approver_email == ADMIN_EMAIL


def test_register_then_approve_flow(client, admin_priv):
    priv = Ed25519PrivateKey.generate()
    assert client.post(REGISTER_PATH, json=agent_register_body(priv)).status_code == 201
    res = client.post(_approve_path("agent-1"), json=_approve_body(admin_priv, "agent-1"))
    assert res.status_code == 200
    assert res.json()["agent_public_key"] == pub_b64(priv)


def test_approve_is_idempotent_and_keeps_first_approver(client, session_factory, admin_priv):
    seed_agent(session_factory, Ed25519PrivateKey.generate(), "agent-1", ApprovalStatus.PENDING)
    assert client.post(_approve_path("agent-1"), json=_approve_body(admin_priv, "agent-1")).status_code == 200
    second_admin = Ed25519PrivateKey.generate()
    seed_admin(session_factory, second_admin, email="second-admin@example.com")
    res = client.post(_approve_path("agent-1"), json=_approve_body(second_admin, "agent-1"))
    assert res.status_code == 200
    assert res.json()["approver_email"] == ADMIN_EMAIL  # 2回目の承認では、最初の承認者が書き換わらない


def test_approve_by_non_admin_is_forbidden(client, session_factory, admin_priv):
    seed_agent(session_factory, Ed25519PrivateKey.generate(), "agent-1", ApprovalStatus.PENDING)
    not_admin = Ed25519PrivateKey.generate()  # 署名は正当だが、tbl_adminに無い鍵
    assert client.post(_approve_path("agent-1"), json=_approve_body(not_admin, "agent-1")).status_code == 403
    with session_factory() as db:
        row = db.execute(select(TblAgent)).scalar_one()
        assert row.status == ApprovalStatus.PENDING
        assert row.approver_email is None


def test_approve_by_inactive_admin_is_forbidden(client, session_factory):
    inactive = Ed25519PrivateKey.generate()
    seed_admin(session_factory, inactive, is_active=False)  # 無効化された管理者
    seed_agent(session_factory, Ed25519PrivateKey.generate(), "agent-1", ApprovalStatus.PENDING)
    assert client.post(_approve_path("agent-1"), json=_approve_body(inactive, "agent-1")).status_code == 403


def test_approve_signed_for_other_agent_is_unauthorized(client, session_factory, admin_priv):
    seed_agent(session_factory, Ed25519PrivateKey.generate(), "agent-1", ApprovalStatus.PENDING)
    seed_agent(session_factory, Ed25519PrivateKey.generate(), "agent-2", ApprovalStatus.PENDING)
    body = _approve_body(admin_priv, "agent-2")  # agent-2用の署名を、agent-1へ使い回す
    assert client.post(_approve_path("agent-1"), json=body).status_code == 401


def test_approve_expired_signature_is_unauthorized(client, session_factory, admin_priv):
    seed_agent(session_factory, Ed25519PrivateKey.generate(), "agent-1", ApprovalStatus.PENDING)
    body = _approve_body(admin_priv, "agent-1", signed_at=int(time.time()) - SIGNATURE_MAX_SKEW_SEC - 60)
    assert client.post(_approve_path("agent-1"), json=body).status_code == 401


def test_approve_unknown_agent_is_not_found(client, admin_priv):
    assert client.post(_approve_path("nobody"), json=_approve_body(admin_priv, "nobody")).status_code == 404


def test_approve_revoked_is_conflict(client, session_factory, admin_priv):
    seed_agent(session_factory, Ed25519PrivateKey.generate(), "agent-1", ApprovalStatus.REVOKED)
    assert client.post(_approve_path("agent-1"), json=_approve_body(admin_priv, "agent-1")).status_code == 409

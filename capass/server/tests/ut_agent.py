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
from capass_server.common.config import SIGNATURE_MAX_SKEW_SEC
from capass_server.common.signature import SIGN_CONTEXT_AGENT_APPROVE, SIGN_CONTEXT_AGENT_REGISTER
from capass_server.models.entities import ApprovalStatus, TblAgent
from sqlalchemy import select
from testlib import pub_b64, seed_agent, signed_body

REGISTER_PATH = "/api/v1/agents/register"


def _register_body(priv, agent_id="agent-1", signed_at=None):
    fields = {"agent_id": agent_id, "agent_public_key": pub_b64(priv)}
    return signed_body(priv, SIGN_CONTEXT_AGENT_REGISTER, fields, signed_at=signed_at)


def _approve_path(agent_id):
    return f"/api/v1/agents/{agent_id}/approve"


def _approve_body(admin_priv, agent_id, signed_at=None):
    fields = {"admin_public_key": pub_b64(admin_priv)}
    return signed_body(admin_priv, SIGN_CONTEXT_AGENT_APPROVE, fields, path_params={"agent_id": agent_id}, signed_at=signed_at)


# ---------- agents/register ----------
def test_register_ok_is_pending(client, session_factory):
    priv = Ed25519PrivateKey.generate()
    res = client.post(REGISTER_PATH, json=_register_body(priv))
    assert res.status_code == 201
    data = res.json()
    assert data["agent_id"] == "agent-1"
    assert data["status"] == "pending"
    with session_factory() as db:
        row = db.execute(select(TblAgent)).scalar_one()
        assert row.agent_public_key == pub_b64(priv)
        assert row.status == ApprovalStatus.PENDING
        assert row.approved_at is None


def test_register_duplicate_agent_id_is_conflict(client):
    priv = Ed25519PrivateKey.generate()
    assert client.post(REGISTER_PATH, json=_register_body(priv)).status_code == 201
    assert client.post(REGISTER_PATH, json=_register_body(priv)).status_code == 409  # リプレイも409
    other = Ed25519PrivateKey.generate()
    assert client.post(REGISTER_PATH, json=_register_body(other)).status_code == 409  # 別の鍵でも、同じagent_idは登録できない


def test_register_duplicate_public_key_is_conflict(client):
    priv = Ed25519PrivateKey.generate()
    assert client.post(REGISTER_PATH, json=_register_body(priv, agent_id="agent-1")).status_code == 201
    assert client.post(REGISTER_PATH, json=_register_body(priv, agent_id="agent-2")).status_code == 409  # 1つの鍵は1つのagentにのみ紐づく


def test_register_tampered_body_is_unauthorized(client):
    priv = Ed25519PrivateKey.generate()
    body = _register_body(priv)
    body["agent_id"] = "agent-evil"  # 署名後に改ざん
    assert client.post(REGISTER_PATH, json=body).status_code == 401


def test_register_expired_signature_is_unauthorized(client):
    priv = Ed25519PrivateKey.generate()
    body = _register_body(priv, signed_at=int(time.time()) - SIGNATURE_MAX_SKEW_SEC - 60)
    assert client.post(REGISTER_PATH, json=body).status_code == 401


def test_register_invalid_input_is_unprocessable(client):
    priv = Ed25519PrivateKey.generate()
    body = _register_body(priv, agent_id="bad/agent id")  # 使えない文字(スペース、スラッシュ)
    assert client.post(REGISTER_PATH, json=body).status_code == 422
    body = _register_body(priv)
    body["agent_public_key"] = "not-a-valid-key"
    assert client.post(REGISTER_PATH, json=body).status_code == 422


# ---------- agents/{agent_id}/approve ----------
def test_approve_ok(client, session_factory, admin_priv):
    seed_agent(session_factory, Ed25519PrivateKey.generate(), "agent-1", ApprovalStatus.PENDING)
    res = client.post(_approve_path("agent-1"), json=_approve_body(admin_priv, "agent-1"))
    assert res.status_code == 200
    assert res.json()["status"] == "approved"
    with session_factory() as db:
        row = db.execute(select(TblAgent)).scalar_one()
        assert row.status == ApprovalStatus.APPROVED
        assert row.approved_at is not None


def test_register_then_approve_flow(client, admin_priv):
    priv = Ed25519PrivateKey.generate()
    assert client.post(REGISTER_PATH, json=_register_body(priv)).status_code == 201
    res = client.post(_approve_path("agent-1"), json=_approve_body(admin_priv, "agent-1"))
    assert res.status_code == 200
    assert res.json()["agent_public_key"] == pub_b64(priv)


def test_approve_is_idempotent(client, session_factory, admin_priv):
    seed_agent(session_factory, Ed25519PrivateKey.generate(), "agent-1", ApprovalStatus.PENDING)
    assert client.post(_approve_path("agent-1"), json=_approve_body(admin_priv, "agent-1")).status_code == 200
    assert client.post(_approve_path("agent-1"), json=_approve_body(admin_priv, "agent-1")).status_code == 200


def test_approve_by_non_admin_is_forbidden(client, session_factory, admin_priv):
    seed_agent(session_factory, Ed25519PrivateKey.generate(), "agent-1", ApprovalStatus.PENDING)
    not_admin = Ed25519PrivateKey.generate()  # 署名は正当だが、管理者の鍵ではない
    assert client.post(_approve_path("agent-1"), json=_approve_body(not_admin, "agent-1")).status_code == 403
    with session_factory() as db:
        assert db.execute(select(TblAgent)).scalar_one().status == ApprovalStatus.PENDING


def test_approve_signed_for_other_agent_is_unauthorized(client, session_factory, admin_priv):
    seed_agent(session_factory, Ed25519PrivateKey.generate(), "agent-1", ApprovalStatus.PENDING)
    seed_agent(session_factory, Ed25519PrivateKey.generate(), "agent-2", ApprovalStatus.PENDING)
    body = _approve_body(admin_priv, "agent-2")  # agent-2用の署名を、agent-1へ使い回す
    assert client.post(_approve_path("agent-1"), json=body).status_code == 401


def test_approve_unknown_agent_is_not_found(client, admin_priv):
    assert client.post(_approve_path("nobody"), json=_approve_body(admin_priv, "nobody")).status_code == 404


def test_approve_revoked_is_conflict(client, session_factory, admin_priv):
    seed_agent(session_factory, Ed25519PrivateKey.generate(), "agent-1", ApprovalStatus.REVOKED)
    assert client.post(_approve_path("agent-1"), json=_approve_body(admin_priv, "agent-1")).status_code == 409

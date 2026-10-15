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
from capass_server.common.signature import SIGN_CONTEXT_TOOLSERVER_APPROVE, SIGN_CONTEXT_TOOLSERVER_REGISTER
from capass_server.models.entities import ApprovalStatus, TblToolServer
from capass_server.services import signed_request
from testlib import pub_b64, seed_tool_server, signed_body

REGISTER_PATH = "/api/v1/toolservers/register"


def _register_body(priv, name="社内ツールサーバA", signed_at=None):
    fields = {"tool_server_public_key": pub_b64(priv), "tool_server_name": name}
    return signed_body(priv, SIGN_CONTEXT_TOOLSERVER_REGISTER, fields, signed_at=signed_at)


def _approve_path(toolserver_id):
    return f"/api/v1/toolservers/{toolserver_id}/approve"


def _approve_body(admin_priv, toolserver_id, signed_at=None):
    fields = {"admin_public_key": pub_b64(admin_priv)}
    return signed_body(admin_priv, SIGN_CONTEXT_TOOLSERVER_APPROVE, fields, path_params={"toolserver_id": toolserver_id}, signed_at=signed_at)


# ---------- toolservers/register ----------
def test_register_ok_is_pending(client, session_factory):
    priv = Ed25519PrivateKey.generate()
    res = client.post(REGISTER_PATH, json=_register_body(priv))
    assert res.status_code == 201
    data = res.json()
    assert data["status"] == "pending"
    assert data["tool_server_name"] == "社内ツールサーバA"
    assert data["tool_server_public_key"] == pub_b64(priv)
    with session_factory() as db:
        row = db.get(TblToolServer, data["toolserver_id"])
        assert row.status == ApprovalStatus.PENDING
        assert row.approved_at is None


def test_register_duplicate_public_key_is_conflict(client):
    priv = Ed25519PrivateKey.generate()
    assert client.post(REGISTER_PATH, json=_register_body(priv)).status_code == 201
    assert client.post(REGISTER_PATH, json=_register_body(priv)).status_code == 409  # リプレイも409


def test_register_tampered_body_is_unauthorized(client):
    priv = Ed25519PrivateKey.generate()
    body = _register_body(priv)
    body["tool_server_name"] = "偽の名称"  # 署名後に改ざん
    assert client.post(REGISTER_PATH, json=body).status_code == 401


def test_register_expired_signature_is_unauthorized(client):
    priv = Ed25519PrivateKey.generate()
    body = _register_body(priv, signed_at=int(time.time()) - SIGNATURE_MAX_SKEW_SEC - 60)
    assert client.post(REGISTER_PATH, json=body).status_code == 401


def test_register_signed_by_other_key_is_unauthorized(client):
    priv, other = Ed25519PrivateKey.generate(), Ed25519PrivateKey.generate()
    body = _register_body(priv)
    body["tool_server_public_key"] = pub_b64(other)  # 署名した鍵と申告した公開鍵が不一致(鍵の所持証明に失敗)
    assert client.post(REGISTER_PATH, json=body).status_code == 401


def test_register_invalid_input_is_unprocessable(client):
    priv = Ed25519PrivateKey.generate()
    body = _register_body(priv)
    body["tool_server_public_key"] = "not-a-valid-key"
    assert client.post(REGISTER_PATH, json=body).status_code == 422
    body = _register_body(priv)
    body["unexpected"] = "x"
    assert client.post(REGISTER_PATH, json=body).status_code == 422


# ---------- toolservers/{toolserver_id}/approve ----------
def test_approve_ok(client, session_factory, admin_priv):
    ts_id = seed_tool_server(session_factory, Ed25519PrivateKey.generate(), ApprovalStatus.PENDING)
    res = client.post(_approve_path(ts_id), json=_approve_body(admin_priv, ts_id))
    assert res.status_code == 200
    assert res.json()["status"] == "approved"
    with session_factory() as db:
        row = db.get(TblToolServer, ts_id)
        assert row.status == ApprovalStatus.APPROVED
        assert row.approved_at is not None


def test_register_then_approve_flow(client, admin_priv):
    priv = Ed25519PrivateKey.generate()
    ts_id = client.post(REGISTER_PATH, json=_register_body(priv)).json()["toolserver_id"]
    res = client.post(_approve_path(ts_id), json=_approve_body(admin_priv, ts_id))
    assert res.status_code == 200
    assert res.json()["tool_server_public_key"] == pub_b64(priv)


def test_approve_is_idempotent(client, session_factory, admin_priv):
    ts_id = seed_tool_server(session_factory, Ed25519PrivateKey.generate(), ApprovalStatus.PENDING)
    assert client.post(_approve_path(ts_id), json=_approve_body(admin_priv, ts_id)).status_code == 200
    assert client.post(_approve_path(ts_id), json=_approve_body(admin_priv, ts_id)).status_code == 200


def test_approve_by_non_admin_is_forbidden(client, session_factory, admin_priv):
    ts_id = seed_tool_server(session_factory, Ed25519PrivateKey.generate(), ApprovalStatus.PENDING)
    not_admin = Ed25519PrivateKey.generate()  # 署名は正当だが、管理者の鍵ではない
    res = client.post(_approve_path(ts_id), json=_approve_body(not_admin, ts_id))
    assert res.status_code == 403
    with session_factory() as db:
        assert db.get(TblToolServer, ts_id).status == ApprovalStatus.PENDING


def test_approve_when_no_admin_configured_is_forbidden(client, session_factory, monkeypatch):
    monkeypatch.setattr(signed_request, "ADMIN_PUBLIC_KEYS", [])  # 管理者が未設定なら、承認は全て拒否される
    ts_id = seed_tool_server(session_factory, Ed25519PrivateKey.generate(), ApprovalStatus.PENDING)
    assert client.post(_approve_path(ts_id), json=_approve_body(Ed25519PrivateKey.generate(), ts_id)).status_code == 403


def test_approve_signed_for_other_id_is_unauthorized(client, session_factory, admin_priv):
    ts_id = seed_tool_server(session_factory, Ed25519PrivateKey.generate(), ApprovalStatus.PENDING)
    body = _approve_body(admin_priv, ts_id + 100)  # 別のtoolserver_idに対する署名の使い回し
    assert client.post(_approve_path(ts_id), json=body).status_code == 401


def test_approve_expired_signature_is_unauthorized(client, session_factory, admin_priv):
    ts_id = seed_tool_server(session_factory, Ed25519PrivateKey.generate(), ApprovalStatus.PENDING)
    body = _approve_body(admin_priv, ts_id, signed_at=int(time.time()) - SIGNATURE_MAX_SKEW_SEC - 60)
    assert client.post(_approve_path(ts_id), json=body).status_code == 401


def test_approve_unknown_id_is_not_found(client, admin_priv):
    assert client.post(_approve_path(999), json=_approve_body(admin_priv, 999)).status_code == 404


def test_approve_revoked_is_conflict(client, session_factory, admin_priv):
    ts_id = seed_tool_server(session_factory, Ed25519PrivateKey.generate(), ApprovalStatus.REVOKED)
    assert client.post(_approve_path(ts_id), json=_approve_body(admin_priv, ts_id)).status_code == 409

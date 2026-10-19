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
from capass_server.common.signature import SIGN_CONTEXT_TOOLSERVER_APPROVE
from capass_server.models.entities import ApprovalStatus, TblToolServer
from capass_server.services import tool_server as tool_server_service
from testlib import ADMIN_EMAIL, APPLICANT_EMAIL, EXEC_URL, approve_body, pub_b64, seed_admin, seed_tool_server, toolserver_register_body

REGISTER_PATH = "/api/v1/toolservers/register"


def _approve_path(toolserver_id):
    return f"/api/v1/toolservers/{toolserver_id}/approve"


def _approve_body(admin_priv, toolserver_id, signed_at=None):
    return approve_body(admin_priv, SIGN_CONTEXT_TOOLSERVER_APPROVE, {"toolserver_id": toolserver_id}, signed_at)


# ---------- toolservers/register ----------
def test_register_ok_is_pending(client, session_factory):
    priv = Ed25519PrivateKey.generate()
    res = client.post(REGISTER_PATH, json=toolserver_register_body(priv))
    assert res.status_code == 201
    data = res.json()
    assert data["status"] == "pending"
    assert data["tool_server_name"] == "社内ツールサーバA"
    assert data["applicant_email"] == APPLICANT_EMAIL
    assert data["tool_server_exec_url"] == EXEC_URL
    assert data["tool_server_public_key"] == pub_b64(priv)
    with session_factory() as db:
        row = db.get(TblToolServer, data["toolserver_id"])
        assert row.exec_url == EXEC_URL
        assert row.status == ApprovalStatus.PENDING
        assert row.applicant_email == APPLICANT_EMAIL
        assert row.approver_email is None
        assert row.approved_at is None


def test_register_duplicate_public_key_is_conflict(client):
    priv = Ed25519PrivateKey.generate()
    assert client.post(REGISTER_PATH, json=toolserver_register_body(priv)).status_code == 201
    assert client.post(REGISTER_PATH, json=toolserver_register_body(priv)).status_code == 409  # リプレイも409


def test_register_tampered_body_is_unauthorized(client):
    priv = Ed25519PrivateKey.generate()
    body = toolserver_register_body(priv)
    body["tool_server_name"] = "偽の名称"  # 署名後に改ざん
    assert client.post(REGISTER_PATH, json=body).status_code == 401
    body = toolserver_register_body(priv)
    body["applicant_email"] = "evil@example.com"  # メアドも署名対象
    assert client.post(REGISTER_PATH, json=body).status_code == 401
    body = toolserver_register_body(priv)
    body["tool_server_exec_url"] = "https://evil.example.com/exec"  # 実行URLも署名対象(承認後に差し替えられない)
    assert client.post(REGISTER_PATH, json=body).status_code == 401


def test_register_expired_signature_is_unauthorized(client):
    priv = Ed25519PrivateKey.generate()
    body = toolserver_register_body(priv, signed_at=int(time.time()) - SIGNATURE_MAX_SKEW_SEC - 60)
    assert client.post(REGISTER_PATH, json=body).status_code == 401


def test_register_signed_by_other_key_is_unauthorized(client):
    priv, other = Ed25519PrivateKey.generate(), Ed25519PrivateKey.generate()
    body = toolserver_register_body(priv)
    body["tool_server_public_key"] = pub_b64(other)  # 署名した鍵と申告した公開鍵が不一致(鍵の所持証明に失敗)
    assert client.post(REGISTER_PATH, json=body).status_code == 401


def test_register_invalid_input_is_unprocessable(client):
    priv = Ed25519PrivateKey.generate()
    body = toolserver_register_body(priv)
    body["tool_server_public_key"] = "not-a-valid-key"
    assert client.post(REGISTER_PATH, json=body).status_code == 422
    body = toolserver_register_body(priv)
    body["unexpected"] = "x"
    assert client.post(REGISTER_PATH, json=body).status_code == 422
    body = toolserver_register_body(priv)
    del body["applicant_email"]  # 申請者メアドは必須
    assert client.post(REGISTER_PATH, json=body).status_code == 422
    body = toolserver_register_body(priv)
    del body["tool_server_exec_url"]  # 実行URLも必須
    assert client.post(REGISTER_PATH, json=body).status_code == 422


def test_register_invalid_email_is_unprocessable(client):
    priv = Ed25519PrivateKey.generate()
    for bad in ("not-an-email", "a@b", "a b@example.com", "@example.com", ""):
        assert client.post(REGISTER_PATH, json=toolserver_register_body(priv, email=bad)).status_code == 422, bad


def test_register_invalid_exec_url_is_unprocessable(client):
    priv = Ed25519PrivateKey.generate()
    for bad in ("ftp://example.com/exec", "example.com/exec", "https://exa mple.com", "file:///etc/passwd", ""):
        assert client.post(REGISTER_PATH, json=toolserver_register_body(priv, exec_url=bad)).status_code == 422, bad


def test_register_http_exec_url_is_rejected_unless_allowed(client, monkeypatch):
    priv = Ed25519PrivateKey.generate()
    monkeypatch.setattr(tool_server_service, "TOOL_SERVER_ALLOW_HTTP", False)
    res = client.post(REGISTER_PATH, json=toolserver_register_body(priv, exec_url="http://localhost:9000/capass/exec"))
    assert res.status_code == 422
    assert "https" in res.json()["detail"]
    monkeypatch.setattr(tool_server_service, "TOOL_SERVER_ALLOW_HTTP", True)  # ローカル開発用の設定
    assert client.post(REGISTER_PATH, json=toolserver_register_body(priv, exec_url="http://localhost:9000/capass/exec")).status_code == 201


# ---------- toolservers/{toolserver_id}/approve ----------
def test_approve_ok_records_approver_email(client, session_factory, admin_priv):
    ts_id = seed_tool_server(session_factory, Ed25519PrivateKey.generate(), ApprovalStatus.PENDING)
    res = client.post(_approve_path(ts_id), json=_approve_body(admin_priv, ts_id))
    assert res.status_code == 200
    data = res.json()
    assert data["status"] == "approved"
    assert data["approver_email"] == ADMIN_EMAIL
    with session_factory() as db:
        row = db.get(TblToolServer, ts_id)
        assert row.status == ApprovalStatus.APPROVED
        assert row.approved_at is not None
        assert row.approver_email == ADMIN_EMAIL


def test_register_then_approve_flow(client, admin_priv):
    priv = Ed25519PrivateKey.generate()
    ts_id = client.post(REGISTER_PATH, json=toolserver_register_body(priv)).json()["toolserver_id"]
    res = client.post(_approve_path(ts_id), json=_approve_body(admin_priv, ts_id))
    assert res.status_code == 200
    assert res.json()["tool_server_public_key"] == pub_b64(priv)


def test_approve_is_idempotent_and_keeps_first_approver(client, session_factory, admin_priv):
    ts_id = seed_tool_server(session_factory, Ed25519PrivateKey.generate(), ApprovalStatus.PENDING)
    assert client.post(_approve_path(ts_id), json=_approve_body(admin_priv, ts_id)).status_code == 200
    second_admin = Ed25519PrivateKey.generate()
    seed_admin(session_factory, second_admin, email="second-admin@example.com")
    res = client.post(_approve_path(ts_id), json=_approve_body(second_admin, ts_id))
    assert res.status_code == 200
    assert res.json()["approver_email"] == ADMIN_EMAIL  # 2回目の承認では、最初の承認者が書き換わらない


def test_approve_by_second_admin_records_that_admin(client, session_factory, admin_priv):
    # tbl_adminに追加した管理者は、アプリを再起動しなくても承認できる
    second_admin = Ed25519PrivateKey.generate()
    seed_admin(session_factory, second_admin, email="second-admin@example.com")
    ts_id = seed_tool_server(session_factory, Ed25519PrivateKey.generate(), ApprovalStatus.PENDING)
    res = client.post(_approve_path(ts_id), json=_approve_body(second_admin, ts_id))
    assert res.status_code == 200
    assert res.json()["approver_email"] == "second-admin@example.com"


def test_approve_by_non_admin_is_forbidden(client, session_factory, admin_priv):
    ts_id = seed_tool_server(session_factory, Ed25519PrivateKey.generate(), ApprovalStatus.PENDING)
    not_admin = Ed25519PrivateKey.generate()  # 署名は正当だが、tbl_adminに無い鍵
    res = client.post(_approve_path(ts_id), json=_approve_body(not_admin, ts_id))
    assert res.status_code == 403
    with session_factory() as db:
        row = db.get(TblToolServer, ts_id)
        assert row.status == ApprovalStatus.PENDING
        assert row.approver_email is None


def test_approve_by_inactive_admin_is_forbidden(client, session_factory):
    inactive = Ed25519PrivateKey.generate()
    seed_admin(session_factory, inactive, is_active=False)  # 無効化された管理者
    ts_id = seed_tool_server(session_factory, Ed25519PrivateKey.generate(), ApprovalStatus.PENDING)
    assert client.post(_approve_path(ts_id), json=_approve_body(inactive, ts_id)).status_code == 403


def test_approve_when_no_admin_registered_is_forbidden(client, session_factory):
    ts_id = seed_tool_server(session_factory, Ed25519PrivateKey.generate(), ApprovalStatus.PENDING)  # tbl_adminが空なら、承認は全て拒否される
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

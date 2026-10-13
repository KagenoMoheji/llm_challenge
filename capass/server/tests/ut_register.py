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

# その他のモジュールやROOTPATHのディレクトリ起点の相対パスでのimport
import base64
from datetime import datetime, timezone
import pytest
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey
from cryptography.hazmat.primitives.serialization import Encoding, PublicFormat
from fastapi.testclient import TestClient
from sqlalchemy import create_engine, select
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool
from capass_server.common.config import SIGNATURE_MAX_SKEW_SEC
from capass_server.common.crypto import decrypt_token
from capass_server.common.db import Base, get_db
from capass_server.common.signature import SIGN_CONTEXT_REGISTER, build_signing_message
from capass_server.main import app
from capass_server.models.entities import TblAgentTool, TblToolServer, ToolServerStatus

# DBはテスト用のインメモリSQLiteに差し替える(PostgreSQLの起動は不要)
test_engine = create_engine("sqlite://", connect_args={"check_same_thread": False}, poolclass=StaticPool)
TestSession = sessionmaker(bind=test_engine, autoflush=False, expire_on_commit=False)


def _override_get_db():
    db = TestSession()
    try:
        yield db
    finally:
        db.close()


@pytest.fixture(autouse=True)
def _db():
    Base.metadata.create_all(test_engine)
    app.dependency_overrides[get_db] = _override_get_db
    yield
    app.dependency_overrides.pop(get_db, None)
    Base.metadata.drop_all(test_engine)


client = TestClient(app)


def _pub_b64(priv: Ed25519PrivateKey) -> str:
    return base64.b64encode(priv.public_key().public_bytes(Encoding.Raw, PublicFormat.Raw)).decode()


def _add_tool_server(priv: Ed25519PrivateKey, status: ToolServerStatus = ToolServerStatus.APPROVED) -> None:
    """tbl_tool_serverに、ツールサーバ公開鍵を指定の承認ステータスで登録する(管理者による承認の代わり)。"""
    now = datetime.now(timezone.utc)
    with TestSession() as db:
        db.add(
            TblToolServer(
                tool_server_public_key=_pub_b64(priv),
                tool_server_name="test-tool-server",
                status=status.value,
                created_at=now,
                approved_at=now if status == ToolServerStatus.APPROVED else None,
            )
        )
        db.commit()


def _signed_body(priv: Ed25519PrivateKey, **overrides) -> dict:
    body = {
        "tool_endpoint": "cli://db/query",
        "context": "DBに対してSELECTを実行する",
        "tool_proxy_token": "proxy-token-1",
        "agent_id": "agent-1",
        "tool_server_public_key": _pub_b64(priv),
        "signed_at": int(time.time()),
    }
    body.update(overrides)
    message = build_signing_message(SIGN_CONTEXT_REGISTER, body)
    body["signature"] = base64.b64encode(priv.sign(message)).decode()
    return body


def test_register_ok():
    priv = Ed25519PrivateKey.generate()
    _add_tool_server(priv)
    res = client.post("/api/v1/register", json=_signed_body(priv))
    assert res.status_code == 201
    data = res.json()
    assert data["tool_endpoint"] == "cli://db/query"
    assert data["agent_id"] == "agent-1"
    assert "tool_proxy_token" not in data  # トークンはレスポンスに含めない

    with TestSession() as db:
        rows = db.execute(select(TblAgentTool)).scalars().all()
        assert len(rows) == 1
        assert rows[0].locked is False
        assert rows[0].tool_used_at is None
        assert rows[0].tool_server_public_key == _pub_b64(priv)
        # トークンは暗号化して保存され、復号すると元の平文に戻る
        assert rows[0].tool_proxy_token_encrypted != "proxy-token-1"
        assert "proxy-token-1" not in rows[0].tool_proxy_token_encrypted
        assert decrypt_token(rows[0].tool_proxy_token_encrypted) == "proxy-token-1"


def test_register_duplicate_is_conflict():
    priv = Ed25519PrivateKey.generate()
    _add_tool_server(priv)
    assert client.post("/api/v1/register", json=_signed_body(priv)).status_code == 201
    # 同一リクエストの再送(リプレイ)も、別鍵による同一[ツールエンドポイント/AIエージェント]の登録も409
    assert client.post("/api/v1/register", json=_signed_body(priv)).status_code == 409
    other = Ed25519PrivateKey.generate()
    _add_tool_server(other)  # 承認済みの別ツールサーバでも、同一の[ツールエンドポイント/AIエージェント]は登録できない
    assert client.post("/api/v1/register", json=_signed_body(other)).status_code == 409


def test_register_same_endpoint_other_agent_is_ok():
    priv = Ed25519PrivateKey.generate()
    _add_tool_server(priv)
    assert client.post("/api/v1/register", json=_signed_body(priv, agent_id="agent-1")).status_code == 201
    assert client.post("/api/v1/register", json=_signed_body(priv, agent_id="agent-2")).status_code == 201


def test_register_multiple_roles_for_same_agent_is_ok():
    # 同じツール(psql)を、DBユーザ(ロール)ごとに別のツールエンドポイントとして、同じAIエージェントへ登録できる
    priv = Ed25519PrivateKey.generate()
    _add_tool_server(priv)
    for endpoint, token in (("psql_manager", "token-manager"), ("psql_terminal_admin", "token-terminal-admin")):
        body = _signed_body(priv, tool_endpoint=endpoint, tool_proxy_token=token, agent_id="agent-1")
        assert client.post("/api/v1/register", json=body).status_code == 201
    with TestSession() as db:
        rows = db.execute(select(TblAgentTool).where(TblAgentTool.agent_id == "agent-1")).scalars().all()
        assert sorted(r.tool_endpoint for r in rows) == ["psql_manager", "psql_terminal_admin"]


def test_register_unknown_tool_server_is_forbidden():
    priv = Ed25519PrivateKey.generate()  # tbl_tool_serverに未登録の公開鍵(署名自体は正当)
    res = client.post("/api/v1/register", json=_signed_body(priv))
    assert res.status_code == 403
    with TestSession() as db:
        assert db.execute(select(TblAgentTool)).scalars().all() == []


def test_register_pending_or_revoked_tool_server_is_forbidden():
    pending = Ed25519PrivateKey.generate()
    _add_tool_server(pending, ToolServerStatus.PENDING)
    assert client.post("/api/v1/register", json=_signed_body(pending)).status_code == 403
    revoked = Ed25519PrivateKey.generate()
    _add_tool_server(revoked, ToolServerStatus.REVOKED)
    assert client.post("/api/v1/register", json=_signed_body(revoked)).status_code == 403


def test_register_invalid_signature_takes_precedence_over_approval_check():
    priv = Ed25519PrivateKey.generate()  # 未承認でも、署名が不正ならまず401(承認状況を未認証の相手に知らせない)
    body = _signed_body(priv)
    body["tool_proxy_token"] = "evil-token"
    assert client.post("/api/v1/register", json=body).status_code == 401


def test_register_tampered_body_is_unauthorized():
    priv = Ed25519PrivateKey.generate()
    body = _signed_body(priv)
    body["tool_proxy_token"] = "evil-token"  # 署名後に改ざん
    assert client.post("/api/v1/register", json=body).status_code == 401


def test_register_signed_by_other_key_is_unauthorized():
    priv = Ed25519PrivateKey.generate()
    other = Ed25519PrivateKey.generate()
    body = _signed_body(priv)
    body["tool_server_public_key"] = _pub_b64(other)  # 署名した鍵と、申告した公開鍵が不一致
    assert client.post("/api/v1/register", json=body).status_code == 401


def test_register_expired_signature_is_unauthorized():
    priv = Ed25519PrivateKey.generate()
    body = _signed_body(priv, signed_at=int(time.time()) - SIGNATURE_MAX_SKEW_SEC - 60)
    assert client.post("/api/v1/register", json=body).status_code == 401


def test_register_invalid_public_key_is_unprocessable():
    priv = Ed25519PrivateKey.generate()
    body = _signed_body(priv)
    body["tool_server_public_key"] = "not-a-valid-key"
    assert client.post("/api/v1/register", json=body).status_code == 422


def test_register_unknown_field_is_unprocessable():
    priv = Ed25519PrivateKey.generate()
    body = _signed_body(priv)
    body["unexpected"] = "x"
    assert client.post("/api/v1/register", json=body).status_code == 422

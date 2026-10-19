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
import pytest
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool
from capass_server.common.db import Base, get_db
from capass_server.common.tool_client import ToolServerResponse
from capass_server.controllers import dependencies
from capass_server.main import app
from capass_server.services import agent_exec
from testlib import seed_admin

# DBはテスト用のインメモリSQLiteに差し替える(PostgreSQLの起動は不要)
_test_engine = create_engine("sqlite://", connect_args={"check_same_thread": False}, poolclass=StaticPool)
_TestSession = sessionmaker(bind=_test_engine, autoflush=False, expire_on_commit=False)


def _override_get_db():
    db = _TestSession()
    try:
        yield db
    finally:
        db.close()


@pytest.fixture
def session_factory():
    """DBを差し替えてテーブルを作成し、テスト後に破棄する。テスト内でDBを直接参照/登録するためのセッションファクトリを返す。"""
    Base.metadata.create_all(_test_engine)
    app.dependency_overrides[get_db] = _override_get_db
    yield _TestSession
    app.dependency_overrides.pop(get_db, None)
    Base.metadata.drop_all(_test_engine)


@pytest.fixture
def client(session_factory):
    return TestClient(app)


@pytest.fixture
def admin_priv(session_factory):
    """CaPassサーバ管理者の鍵ペアを作り、tbl_adminに登録する(admin@example.com)。秘密鍵を返す。"""
    priv = Ed25519PrivateKey.generate()
    seed_admin(session_factory, priv)
    return priv


@pytest.fixture(autouse=True)
def _disable_rate_limit(monkeypatch):
    """初回登録APIのレート制限は、既定ではテストで無効にする(レート制限のテストでは、個別に有効化する)。"""
    monkeypatch.setattr(dependencies, "RATE_LIMIT_ENABLED", False)


class FakeToolServer:
    """ツールサーバへの実際のHTTP通信の代わりに使う。呼び出しを記録し、responseに設定した応答を返す(例外を設定すれば、それを送出する)。"""

    def __init__(self) -> None:
        self.calls: list[dict] = []
        self.response: ToolServerResponse | Exception = ToolServerResponse(200, b'{"result": "ok"}', "application/json")

    def __call__(self, url, token, payload, timeout_sec, max_response_bytes, user_agent="CaPass") -> ToolServerResponse:
        self.calls.append({"url": url, "token": token, "payload": payload, "timeout_sec": timeout_sec, "max_response_bytes": max_response_bytes, "user_agent": user_agent})
        if isinstance(self.response, Exception):
            raise self.response
        return self.response


@pytest.fixture
def fake_tool_server(monkeypatch):
    """agent_execがツールサーバを呼ぶ処理(call_tool_server)を、FakeToolServerに差し替える。"""
    fake = FakeToolServer()
    monkeypatch.setattr(agent_exec, "call_tool_server", fake)
    return fake

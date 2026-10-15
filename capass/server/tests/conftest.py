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
from capass_server.main import app
from capass_server.services import signed_request
from testlib import pub_b64

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
def admin_priv(monkeypatch):
    """CaPassサーバ管理者の鍵ペアを作り、その公開鍵を管理者の公開鍵(ADMIN_PUBLIC_KEYS)として差し替える。秘密鍵を返す。"""
    priv = Ed25519PrivateKey.generate()
    monkeypatch.setattr(signed_request, "ADMIN_PUBLIC_KEYS", [pub_b64(priv)])
    return priv

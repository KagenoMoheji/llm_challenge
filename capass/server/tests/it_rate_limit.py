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
from capass_server.common.rate_limit import SlidingWindowRateLimiter
from capass_server.common.signature import SIGN_CONTEXT_TOOLSERVER_APPROVE
from capass_server.controllers import dependencies
from testlib import agent_register_body, approve_body, toolserver_register_body

TOOLSERVER_REGISTER = "/api/v1/toolservers/register"
AGENT_REGISTER = "/api/v1/agents/register"


@pytest.fixture
def limited(monkeypatch):
    """レート制限を有効にする(1つのIPにつき、60秒間に2回まで)。"""
    monkeypatch.setattr(dependencies, "RATE_LIMIT_ENABLED", True)
    monkeypatch.setattr(dependencies, "register_rate_limiter", SlidingWindowRateLimiter(2, 60))


def _toolserver(client, headers=None):
    return client.post(TOOLSERVER_REGISTER, json=toolserver_register_body(Ed25519PrivateKey.generate()), headers=headers)


def _agent(client, agent_id, headers=None):
    return client.post(AGENT_REGISTER, json=agent_register_body(Ed25519PrivateKey.generate(), agent_id=agent_id), headers=headers)


def test_register_is_limited_per_client_ip(client, limited):
    assert _toolserver(client).status_code == 201
    assert _toolserver(client).status_code == 201
    res = _toolserver(client)
    assert res.status_code == 429
    assert int(res.headers["Retry-After"]) >= 1
    assert res.json()["detail"] == "too many requests"


def test_budget_is_shared_between_toolserver_and_agent_register(client, limited):
    assert _toolserver(client).status_code == 201
    assert _agent(client, "agent-1").status_code == 201
    assert _agent(client, "agent-2").status_code == 429
    assert _toolserver(client).status_code == 429


def test_invalid_requests_also_consume_the_budget(client, limited):
    for _ in range(2):
        assert client.post(TOOLSERVER_REGISTER, json={"bad": "body"}).status_code == 422
    assert _toolserver(client).status_code == 429


def test_limit_is_not_applied_without_enabling(client):
    for _ in range(20):  # 既定のテスト設定(レート制限は無効)
        assert _toolserver(client).status_code == 201


def test_x_forwarded_for_is_ignored_without_trusted_proxy(client, limited):
    assert _toolserver(client, {"X-Forwarded-For": "1.1.1.1"}).status_code == 201
    assert _toolserver(client, {"X-Forwarded-For": "2.2.2.2"}).status_code == 201
    assert _toolserver(client, {"X-Forwarded-For": "3.3.3.3"}).status_code == 429  # ヘッダーを変えても、制限は回避できない


def test_x_forwarded_for_is_used_with_trusted_proxy(client, limited, monkeypatch):
    monkeypatch.setattr(dependencies, "TRUSTED_PROXY_COUNT", 1)
    assert _toolserver(client, {"X-Forwarded-For": "10.0.0.1"}).status_code == 201
    assert _toolserver(client, {"X-Forwarded-For": "10.0.0.1"}).status_code == 201
    assert _toolserver(client, {"X-Forwarded-For": "10.0.0.1"}).status_code == 429
    assert _toolserver(client, {"X-Forwarded-For": "10.0.0.2"}).status_code == 201  # 別のクライアントは、別の枠
    # クライアントが左側に偽装したIPを付けても、右端(プロキシが追加した実際の接続元)で判定される
    assert _toolserver(client, {"X-Forwarded-For": "9.9.9.9, 10.0.0.1"}).status_code == 429


def test_approve_is_not_rate_limited(client, limited, admin_priv):
    for _ in range(5):
        body = approve_body(admin_priv, SIGN_CONTEXT_TOOLSERVER_APPROVE, {"toolserver_id": 999})
        assert client.post("/api/v1/toolservers/999/approve", json=body).status_code == 404  # 429ではない

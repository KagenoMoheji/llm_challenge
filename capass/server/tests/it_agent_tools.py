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
from capass_server.models.entities import ApprovalStatus
from testlib import PARAMS_SCHEMA, list_tools_headers, seed_agent, seed_agent_tool, seed_tool_server


def _get(client, agent_id, headers):
    return client.get(f"/api/v1/agents/{agent_id}/tools", headers=headers)


def _setup(session_factory, agent_id="agent-1"):
    """承認済みのAIエージェントとツールサーバを用意し、(AIエージェントの秘密鍵, ツールサーバの秘密鍵)を返す。"""
    agent_priv, ts_priv = Ed25519PrivateKey.generate(), Ed25519PrivateKey.generate()
    seed_agent(session_factory, agent_priv, agent_id)
    seed_tool_server(session_factory, ts_priv)
    return agent_priv, ts_priv


def test_list_tools_ok_sorted_by_endpoint(client, session_factory):
    agent_priv, ts_priv = _setup(session_factory)
    seed_agent_tool(session_factory, "agent-1", "psql_terminal_admin", ts_priv, context="端末管理者ロールでpsql")
    seed_agent_tool(session_factory, "agent-1", "psql_manager", ts_priv, context="部長ロールでpsql")
    res = _get(client, "agent-1", list_tools_headers(agent_priv, "agent-1"))
    assert res.status_code == 200
    data = res.json()
    assert data["agent_id"] == "agent-1"
    assert data["tools"] == [
        {"tool_endpoint": "psql_manager", "context": "部長ロールでpsql", "params_schema": PARAMS_SCHEMA},
        {"tool_endpoint": "psql_terminal_admin", "context": "端末管理者ロールでpsql", "params_schema": PARAMS_SCHEMA},
    ]  # AIエージェントが、実行時のparamsの組み立て方を分かるよう、paramsのスキーマも返す
    assert "tool_proxy_token" not in res.text  # トークンは返さない


def test_list_tools_excludes_locked_tools(client, session_factory):
    agent_priv, ts_priv = _setup(session_factory)
    seed_agent_tool(session_factory, "agent-1", "tool_a", ts_priv)
    seed_agent_tool(session_factory, "agent-1", "tool_locked", ts_priv, locked=True)
    tools = _get(client, "agent-1", list_tools_headers(agent_priv, "agent-1")).json()["tools"]
    assert [t["tool_endpoint"] for t in tools] == ["tool_a"]


def test_list_tools_excludes_tools_of_unapproved_tool_server(client, session_factory):
    agent_priv, ts_priv = _setup(session_factory)
    revoked_priv = Ed25519PrivateKey.generate()
    seed_tool_server(session_factory, revoked_priv, ApprovalStatus.REVOKED, name="revoked-server")
    seed_agent_tool(session_factory, "agent-1", "tool_ok", ts_priv)
    seed_agent_tool(session_factory, "agent-1", "tool_of_revoked", revoked_priv)
    tools = _get(client, "agent-1", list_tools_headers(agent_priv, "agent-1")).json()["tools"]
    assert [t["tool_endpoint"] for t in tools] == ["tool_ok"]  # 承認が取り消されたツールサーバのツールは使えない


def test_list_tools_only_returns_own_tools(client, session_factory):
    agent_priv, ts_priv = _setup(session_factory, "agent-1")
    seed_agent(session_factory, Ed25519PrivateKey.generate(), "agent-2")
    seed_agent_tool(session_factory, "agent-1", "tool_1", ts_priv)
    seed_agent_tool(session_factory, "agent-2", "tool_2", ts_priv)
    tools = _get(client, "agent-1", list_tools_headers(agent_priv, "agent-1")).json()["tools"]
    assert [t["tool_endpoint"] for t in tools] == ["tool_1"]


def test_list_tools_without_executable_tools_returns_empty_list(client, session_factory):
    agent_priv, ts_priv = _setup(session_factory)
    res = _get(client, "agent-1", list_tools_headers(agent_priv, "agent-1"))  # ツールが1件も無い場合は、エラーではなく空のリスト
    assert res.status_code == 200
    assert res.json() == {"agent_id": "agent-1", "tools": []}
    seed_agent_tool(session_factory, "agent-1", "tool_locked", ts_priv, locked=True)
    assert _get(client, "agent-1", list_tools_headers(agent_priv, "agent-1")).json()["tools"] == []  # ロックされたものだけでも同様


def test_list_tools_returns_each_tools_own_params_schema(client, session_factory):
    agent_priv, ts_priv = _setup(session_factory)
    no_params = {"type": "object", "properties": {}}
    seed_agent_tool(session_factory, "agent-1", "tool_a", ts_priv, params_schema=PARAMS_SCHEMA)
    seed_agent_tool(session_factory, "agent-1", "tool_b", ts_priv, params_schema=no_params)
    tools = {t["tool_endpoint"]: t["params_schema"] for t in _get(client, "agent-1", list_tools_headers(agent_priv, "agent-1")).json()["tools"]}
    assert tools == {"tool_a": PARAMS_SCHEMA, "tool_b": no_params}


def test_list_tools_unknown_agent_is_unauthorized(client, session_factory):
    priv = Ed25519PrivateKey.generate()
    assert _get(client, "nobody", list_tools_headers(priv, "nobody")).status_code == 401  # 署名不正と区別しない(AIエージェントの有無を知らせない)


def test_list_tools_signed_by_other_key_is_unauthorized(client, session_factory):
    agent_priv, ts_priv = _setup(session_factory)
    seed_agent_tool(session_factory, "agent-1", "tool_a", ts_priv)
    attacker = Ed25519PrivateKey.generate()
    assert _get(client, "agent-1", list_tools_headers(attacker, "agent-1")).status_code == 401  # agent_idを知っていても、秘密鍵が無ければ使えない


def test_list_tools_signed_for_other_agent_is_unauthorized(client, session_factory):
    agent_priv, ts_priv = _setup(session_factory, "agent-1")
    seed_agent(session_factory, Ed25519PrivateKey.generate(), "agent-2")
    headers = list_tools_headers(agent_priv, "agent-1")
    assert _get(client, "agent-2", headers).status_code == 401  # agent-1用の署名を、agent-2へ使い回す


def test_list_tools_expired_signature_is_unauthorized(client, session_factory):
    agent_priv, _ = _setup(session_factory)
    headers = list_tools_headers(agent_priv, "agent-1", signed_at=int(time.time()) - SIGNATURE_MAX_SKEW_SEC - 60)
    assert _get(client, "agent-1", headers).status_code == 401


def test_list_tools_pending_or_revoked_agent_is_forbidden(client, session_factory):
    for agent_id, status in (("agent-pending", ApprovalStatus.PENDING), ("agent-revoked", ApprovalStatus.REVOKED)):
        priv = Ed25519PrivateKey.generate()
        seed_agent(session_factory, priv, agent_id, status)
        assert _get(client, agent_id, list_tools_headers(priv, agent_id)).status_code == 403


def test_list_tools_requires_signature_headers(client, session_factory):
    _setup(session_factory)
    assert _get(client, "agent-1", {}).status_code == 422

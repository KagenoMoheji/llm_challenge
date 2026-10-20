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
from capass_server.common.crypto import decrypt_token
from capass_server.common.signature import SIGN_CONTEXT_AGENT_ADDTOOL
from capass_server.models.entities import ApprovalStatus, TblAgentTool
from testlib import PARAMS_SCHEMA, pub_b64, seed_agent, seed_tool_server, signed_body


def _body(tool_server_priv, agent_id="agent-1", signed_at=None, **overrides):
    fields = {
        "tool_endpoint": "db_query",
        "context": "DBに対してSELECTを実行する",
        "params_schema": PARAMS_SCHEMA,
        "tool_proxy_token": "proxy-token-1",
        "tool_server_public_key": pub_b64(tool_server_priv),
    }
    fields.update(overrides)
    return signed_body(tool_server_priv, SIGN_CONTEXT_AGENT_ADDTOOL, fields, path_params={"agent_id": agent_id}, signed_at=signed_at)


def _post(client, agent_id, body):
    return client.post(f"/api/v1/agents/{agent_id}/addtool", json=body)


def _setup(session_factory, agent_id="agent-1"):
    """承認済みのツールサーバとAIエージェントを用意する。ツールサーバの秘密鍵を返す。"""
    ts_priv = Ed25519PrivateKey.generate()
    seed_tool_server(session_factory, ts_priv)
    seed_agent(session_factory, Ed25519PrivateKey.generate(), agent_id)
    return ts_priv


def test_addtool_ok(client, session_factory):
    ts_priv = _setup(session_factory)
    res = _post(client, "agent-1", _body(ts_priv))
    assert res.status_code == 201
    data = res.json()
    assert data["tool_endpoint"] == "db_query"
    assert data["agent_id"] == "agent-1"
    assert "tool_proxy_token" not in data  # トークンはレスポンスに含めない

    with session_factory() as db:
        row = db.execute(select(TblAgentTool)).scalar_one()
        assert row.locked is False
        assert row.tool_used_at is None
        assert row.tool_server_public_key == pub_b64(ts_priv)
        assert row.params_schema == PARAMS_SCHEMA  # paramsのスキーマも保存される
        # トークンは暗号化して保存され、復号すると元の平文に戻る
        assert row.tool_proxy_token_encrypted != "proxy-token-1"
        assert "proxy-token-1" not in row.tool_proxy_token_encrypted
        assert decrypt_token(row.tool_proxy_token_encrypted) == "proxy-token-1"


def test_addtool_duplicate_is_conflict(client, session_factory):
    ts_priv = _setup(session_factory)
    assert _post(client, "agent-1", _body(ts_priv)).status_code == 201
    assert _post(client, "agent-1", _body(ts_priv)).status_code == 409  # リプレイも409
    other = Ed25519PrivateKey.generate()
    seed_tool_server(session_factory, other, name="other-tool-server")
    assert _post(client, "agent-1", _body(other)).status_code == 409  # 承認済みの別ツールサーバでも、同一の[ツールエンドポイント/AIエージェント]は登録できない


def test_addtool_same_endpoint_other_agent_is_ok(client, session_factory):
    ts_priv = _setup(session_factory, "agent-1")
    seed_agent(session_factory, Ed25519PrivateKey.generate(), "agent-2")
    assert _post(client, "agent-1", _body(ts_priv, "agent-1")).status_code == 201
    assert _post(client, "agent-2", _body(ts_priv, "agent-2")).status_code == 201


def test_addtool_multiple_roles_for_same_agent_is_ok(client, session_factory):
    # 同じツール(psql)を、DBユーザ(ロール)ごとに別のツールエンドポイントとして、同じAIエージェントへ追加できる
    ts_priv = _setup(session_factory)
    for endpoint, token in (("psql_manager", "token-manager"), ("psql_terminal_admin", "token-terminal-admin")):
        assert _post(client, "agent-1", _body(ts_priv, tool_endpoint=endpoint, tool_proxy_token=token)).status_code == 201
    with session_factory() as db:
        rows = db.execute(select(TblAgentTool).where(TblAgentTool.agent_id == "agent-1")).scalars().all()
        assert sorted(r.tool_endpoint for r in rows) == ["psql_manager", "psql_terminal_admin"]


def test_addtool_unknown_tool_server_is_forbidden(client, session_factory):
    seed_agent(session_factory, Ed25519PrivateKey.generate(), "agent-1")
    unknown = Ed25519PrivateKey.generate()  # tbl_tool_serverに未登録(署名自体は正当)
    assert _post(client, "agent-1", _body(unknown)).status_code == 403
    with session_factory() as db:
        assert db.execute(select(TblAgentTool)).scalars().all() == []


def test_addtool_pending_or_revoked_tool_server_is_forbidden(client, session_factory):
    seed_agent(session_factory, Ed25519PrivateKey.generate(), "agent-1")
    pending, revoked = Ed25519PrivateKey.generate(), Ed25519PrivateKey.generate()
    seed_tool_server(session_factory, pending, ApprovalStatus.PENDING, name="pending")
    seed_tool_server(session_factory, revoked, ApprovalStatus.REVOKED, name="revoked")
    assert _post(client, "agent-1", _body(pending)).status_code == 403
    assert _post(client, "agent-1", _body(revoked)).status_code == 403


def test_addtool_unknown_agent_is_not_found(client, session_factory):
    ts_priv = Ed25519PrivateKey.generate()
    seed_tool_server(session_factory, ts_priv)
    assert _post(client, "nobody", _body(ts_priv, "nobody")).status_code == 404


def test_addtool_pending_or_revoked_agent_is_forbidden(client, session_factory):
    ts_priv = Ed25519PrivateKey.generate()
    seed_tool_server(session_factory, ts_priv)
    seed_agent(session_factory, Ed25519PrivateKey.generate(), "agent-pending", ApprovalStatus.PENDING)
    seed_agent(session_factory, Ed25519PrivateKey.generate(), "agent-revoked", ApprovalStatus.REVOKED)
    assert _post(client, "agent-pending", _body(ts_priv, "agent-pending")).status_code == 403
    assert _post(client, "agent-revoked", _body(ts_priv, "agent-revoked")).status_code == 403


def test_addtool_invalid_signature_takes_precedence_over_approval_check(client, session_factory):
    seed_agent(session_factory, Ed25519PrivateKey.generate(), "agent-1")
    unknown = Ed25519PrivateKey.generate()  # 未承認でも、署名が不正ならまず401(承認状況を未認証の相手に知らせない)
    body = _body(unknown)
    body["tool_proxy_token"] = "evil-token"
    assert _post(client, "agent-1", body).status_code == 401


def test_addtool_tampered_body_is_unauthorized(client, session_factory):
    ts_priv = _setup(session_factory)
    body = _body(ts_priv)
    body["tool_proxy_token"] = "evil-token"  # 署名後に改ざん
    assert _post(client, "agent-1", body).status_code == 401


def test_addtool_signed_for_other_agent_is_unauthorized(client, session_factory):
    ts_priv = _setup(session_factory, "agent-1")
    seed_agent(session_factory, Ed25519PrivateKey.generate(), "agent-2")
    body = _body(ts_priv, "agent-1")  # agent-1用の署名を、agent-2へ使い回す
    assert _post(client, "agent-2", body).status_code == 401


def test_addtool_signed_by_other_key_is_unauthorized(client, session_factory):
    ts_priv = _setup(session_factory)
    other = Ed25519PrivateKey.generate()
    body = _body(ts_priv)
    body["tool_server_public_key"] = pub_b64(other)  # 署名した鍵と、申告した公開鍵が不一致
    assert _post(client, "agent-1", body).status_code == 401


def test_addtool_expired_signature_is_unauthorized(client, session_factory):
    ts_priv = _setup(session_factory)
    body = _body(ts_priv, signed_at=int(time.time()) - SIGNATURE_MAX_SKEW_SEC - 60)
    assert _post(client, "agent-1", body).status_code == 401


def test_addtool_invalid_input_is_unprocessable(client, session_factory):
    ts_priv = _setup(session_factory)
    body = _body(ts_priv)
    body["tool_server_public_key"] = "not-a-valid-key"
    assert _post(client, "agent-1", body).status_code == 422
    body = _body(ts_priv)
    body["unexpected"] = "x"
    assert _post(client, "agent-1", body).status_code == 422
    body = _body(ts_priv)
    body["agent_id"] = "agent-1"  # agent_idはURLパスで指定する(ボディでは受け付けない)
    assert _post(client, "agent-1", body).status_code == 422
    for bad_endpoint in ("cli://db/query", "has space", "a/b"):  # URLパス exec/{tool_endpoint} に使えない文字(スラッシュ・空白)
        assert _post(client, "agent-1", _body(ts_priv, tool_endpoint=bad_endpoint)).status_code == 422, bad_endpoint


def test_addtool_japanese_endpoint_is_ok(client, session_factory):
    ts_priv = _setup(session_factory)
    assert _post(client, "agent-1", _body(ts_priv, tool_endpoint="psql_部長ロール")).status_code == 201


def test_addtool_tampered_params_schema_is_unauthorized(client, session_factory):
    ts_priv = _setup(session_factory)
    body = _body(ts_priv)
    body["params_schema"] = {"type": "object", "properties": {"sql": {"type": "string", "description": "改ざん"}}}  # 署名後にスキーマを改ざん
    assert _post(client, "agent-1", body).status_code == 401


def test_addtool_params_schema_is_required(client, session_factory):
    ts_priv = _setup(session_factory)
    fields = {"tool_endpoint": "db_query", "context": "x", "tool_proxy_token": "t", "tool_server_public_key": pub_b64(ts_priv)}
    body = signed_body(ts_priv, SIGN_CONTEXT_AGENT_ADDTOOL, fields, path_params={"agent_id": "agent-1"})  # params_schemaが無い
    assert _post(client, "agent-1", body).status_code == 422


def test_addtool_tool_without_parameters_is_ok(client, session_factory):
    ts_priv = _setup(session_factory)
    schema = {"type": "object", "properties": {}}  # パラメータが無いツール
    assert _post(client, "agent-1", _body(ts_priv, params_schema=schema)).status_code == 201


def test_addtool_rich_params_schema_is_ok(client, session_factory):
    ts_priv = _setup(session_factory)
    schema = {
        "type": "object",
        "properties": {
            "sql": {"type": "string", "description": "実行するSQL文", "minLength": 1, "examples": ["SELECT 1"]},
            "limit": {"type": "integer", "description": "取得する最大行数(1〜1000)", "minimum": 1, "maximum": 1000, "default": 100},
            "format": {"type": "string", "description": "出力形式", "enum": ["json", "csv"]},
        },
        "required": ["sql"],
        "additionalProperties": False,
    }
    assert _post(client, "agent-1", _body(ts_priv, params_schema=schema)).status_code == 201


def test_addtool_invalid_params_schema_is_unprocessable(client, session_factory):
    ts_priv = _setup(session_factory)
    described = {"type": "string", "description": "説明"}
    invalid_schemas = {
        "root is not object": {"type": "array", "items": {}},
        "no type": {"properties": {"a": described}},
        "no properties": {"type": "object"},
        "properties is not an object": {"type": "object", "properties": ["a"]},
        "property without description": {"type": "object", "properties": {"a": {"type": "string"}}},
        "property with empty description": {"type": "object", "properties": {"a": {"type": "string", "description": "  "}}},
        "property is not an object": {"type": "object", "properties": {"a": True}},
        "not a valid JSON Schema": {"type": "object", "properties": {"a": {"type": "no-such-type", "description": "x"}}},
        "invalid keyword value": {"type": "object", "properties": {"a": described}, "required": "a"},
        "external ref": {"type": "object", "properties": {"a": {"$ref": "https://evil.example.com/schema.json", "description": "x"}}},
        "external ref in nested list": {"type": "object", "properties": {"a": {"anyOf": [{"$ref": "http://evil.example.com/s"}], "description": "x"}}},
        "too large": {"type": "object", "properties": {"a": {"type": "string", "description": "x" * 20000}}},
    }
    for label, schema in invalid_schemas.items():
        assert _post(client, "agent-1", _body(ts_priv, params_schema=schema)).status_code == 422, label


def test_addtool_local_ref_in_params_schema_is_ok(client, session_factory):
    ts_priv = _setup(session_factory)
    schema = {
        "type": "object",
        "properties": {"user": {"$ref": "#/$defs/user", "description": "対象のユーザ"}},
        "$defs": {"user": {"type": "object", "properties": {"id": {"type": "integer", "description": "ユーザID"}}}},
    }
    assert _post(client, "agent-1", _body(ts_priv, params_schema=schema)).status_code == 201  # スキーマ内の参照("#"から始まる)は使える

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
from capass_server.common.config import SIGNATURE_MAX_SKEW_SEC, TOKEN_MAX_AGE_SEC
from capass_server.common.crypto import decrypt_token
from capass_server.models.entities import ApprovalStatus, TblAgentTool, TblTool
from testlib import PARAMS_SCHEMA, pub_b64, seed_tool_server, tool_add_body

PATH = "/api/v1/tools/addtool"


def _setup(session_factory, status=ApprovalStatus.APPROVED):
    """ツールサーバを用意して、(toolserver_id, 秘密鍵)を返す。"""
    priv = Ed25519PrivateKey.generate()
    return seed_tool_server(session_factory, priv, status), priv


def test_addtool_ok(client, session_factory):
    ts_id, ts_priv = _setup(session_factory)
    res = client.post(PATH, json=tool_add_body(ts_priv, token="proxy-token-1"))
    assert res.status_code == 201
    data = res.json()
    assert data["tool_endpoint"] == "db_query"
    assert data["token_max_age_sec"] == TOKEN_MAX_AGE_SEC  # ツールサーバが、トークンを更新する間隔の目安(これより短い間隔で更新する)
    assert "tool_proxy_token" not in data  # トークンはレスポンスに含めない

    with session_factory() as db:
        row = db.execute(select(TblTool)).scalar_one()
        assert row.tool_server_id == ts_id
        assert row.locked is False
        assert row.params_schema == PARAMS_SCHEMA
        # トークンは暗号化して保存され、復号すると元の平文に戻る
        assert row.tool_proxy_token_encrypted != "proxy-token-1" and "proxy-token-1" not in row.tool_proxy_token_encrypted
        assert decrypt_token(row.tool_proxy_token_encrypted) == "proxy-token-1"
        assert db.execute(select(TblAgentTool)).scalars().all() == []  # 登録しただけでは、どのAIエージェントにも割り当てられない


def test_addtool_duplicate_endpoint_is_conflict(client, session_factory):
    _, ts_priv = _setup(session_factory)
    assert client.post(PATH, json=tool_add_body(ts_priv)).status_code == 201
    assert client.post(PATH, json=tool_add_body(ts_priv)).status_code == 409  # リプレイも409
    other = Ed25519PrivateKey.generate()
    seed_tool_server(session_factory, other, name="other-server")
    assert client.post(PATH, json=tool_add_body(other)).status_code == 409  # 別の承認済みツールサーバでも、ツールエンドポイントは、全体で一意


def test_addtool_multiple_roles_are_separate_tools(client, session_factory):
    # 同じツール(psql)を、DBロールごとに、別のツールエンドポイント(別のトークン)として登録する
    _, ts_priv = _setup(session_factory)
    for endpoint, token in (("psql_manager", "token-manager"), ("psql_terminal_admin", "token-terminal-admin")):
        assert client.post(PATH, json=tool_add_body(ts_priv, tool_endpoint=endpoint, token=token)).status_code == 201
    with session_factory() as db:
        tokens = {t.tool_endpoint: decrypt_token(t.tool_proxy_token_encrypted) for t in db.execute(select(TblTool)).scalars().all()}
    assert tokens == {"psql_manager": "token-manager", "psql_terminal_admin": "token-terminal-admin"}


def test_addtool_by_unapproved_tool_server_is_forbidden(client, session_factory):
    unknown = Ed25519PrivateKey.generate()  # 未登録(署名自体は正当)
    assert client.post(PATH, json=tool_add_body(unknown)).status_code == 403
    for status in (ApprovalStatus.PENDING, ApprovalStatus.REVOKED, ApprovalStatus.RESERVED, ApprovalStatus.STANDBY):
        priv = Ed25519PrivateKey.generate()
        seed_tool_server(session_factory, priv, status, name=f"server-{status.value}", expires_in_sec=3600)
        assert client.post(PATH, json=tool_add_body(priv, tool_endpoint=f"tool_{status.value}")).status_code == 403, status  # 予約中・待機中のツールサーバも、まだ(もう)使えない
    with session_factory() as db:
        assert db.execute(select(TblTool)).scalars().all() == []


def test_addtool_invalid_signature_takes_precedence_over_approval_check(client, session_factory):
    unknown = Ed25519PrivateKey.generate()
    body = tool_add_body(unknown)
    body["tool_proxy_token"] = "evil-token"  # 署名後に改ざん。未承認でも、署名が不正ならまず401(承認状況を未認証の相手に知らせない)
    assert client.post(PATH, json=body).status_code == 401


def test_addtool_tampered_or_forged_requests_are_unauthorized(client, session_factory):
    _, ts_priv = _setup(session_factory)
    body = tool_add_body(ts_priv)
    body["tool_proxy_token"] = "evil-token"
    assert client.post(PATH, json=body).status_code == 401
    body = tool_add_body(ts_priv)
    body["params_schema"] = {"type": "object", "properties": {"sql": {"type": "string", "description": "改ざん"}}}  # 署名後にスキーマを改ざん
    assert client.post(PATH, json=body).status_code == 401
    body = tool_add_body(ts_priv)
    body["tool_server_public_key"] = pub_b64(Ed25519PrivateKey.generate())  # 署名した鍵と、申告した公開鍵が不一致
    assert client.post(PATH, json=body).status_code == 401
    assert client.post(PATH, json=tool_add_body(ts_priv, signed_at=int(time.time()) - SIGNATURE_MAX_SKEW_SEC - 60)).status_code == 401


def test_addtool_invalid_input_is_unprocessable(client, session_factory):
    _, ts_priv = _setup(session_factory)
    body = tool_add_body(ts_priv)
    assert client.post(PATH, json={**body, "tool_server_public_key": "not-a-valid-key"}).status_code == 422
    assert client.post(PATH, json={**body, "unexpected": "x"}).status_code == 422
    assert client.post(PATH, json={**body, "agent_id": "agent-1"}).status_code == 422  # ツールは、AIエージェントとは独立(割り当ては、別のAPI)
    for missing in ("tool_endpoint", "context", "params_schema", "tool_proxy_token", "tool_server_public_key"):
        assert client.post(PATH, json={k: v for k, v in body.items() if k != missing}).status_code == 422, missing
    for bad_endpoint in ("cli://db/query", "has space", "a/b"):  # URLパス exec/{tool_endpoint} に使えない文字(スラッシュ・空白)
        assert client.post(PATH, json=tool_add_body(ts_priv, tool_endpoint=bad_endpoint)).status_code == 422, bad_endpoint


def test_addtool_japanese_endpoint_is_ok(client, session_factory):
    _, ts_priv = _setup(session_factory)
    assert client.post(PATH, json=tool_add_body(ts_priv, tool_endpoint="psql_部長ロール")).status_code == 201


def test_addtool_params_schema_variants(client, session_factory):
    _, ts_priv = _setup(session_factory)
    schemas = {
        "no parameters": {"type": "object", "properties": {}},
        "rich": {
            "type": "object",
            "properties": {
                "sql": {"type": "string", "description": "実行するSQL文", "minLength": 1, "examples": ["SELECT 1"]},
                "limit": {"type": "integer", "description": "取得する最大行数(1〜1000)", "minimum": 1, "maximum": 1000, "default": 100},
                "format": {"type": "string", "description": "出力形式", "enum": ["json", "csv"]},
            },
            "required": ["sql"],
            "additionalProperties": False,
        },
        "local ref": {
            "type": "object",
            "properties": {"user": {"$ref": "#/$defs/user", "description": "対象のユーザ"}},
            "$defs": {"user": {"type": "object", "properties": {"id": {"type": "integer", "description": "ユーザID"}}}},
        },
        "parameter named pattern": {
            "type": "object",
            "properties": {"pattern": {"type": "string", "description": "検索する文字列"}},
            "required": ["pattern"],
            "examples": [{"pattern": "TODO"}],  # データの中の "pattern" は、キーワードではない
        },
    }
    for i, (label, schema) in enumerate(schemas.items()):
        assert client.post(PATH, json=tool_add_body(ts_priv, tool_endpoint=f"tool_{i}", params_schema=schema)).status_code == 201, label


def test_addtool_invalid_params_schema_is_unprocessable(client, session_factory):
    _, ts_priv = _setup(session_factory)
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
        "pattern keyword": {"type": "object", "properties": {"sql": {"type": "string", "description": "SQL", "pattern": "^SELECT .*"}}},
        "patternProperties keyword": {"type": "object", "properties": {}, "patternProperties": {"^x_": {"type": "string"}}},
        "pattern in nested schema": {"type": "object", "properties": {"a": {"type": "array", "description": "x", "items": {"type": "string", "pattern": "(a+)+$"}}}},
        "ref into data": {"type": "object", "properties": {"a": {"$ref": "#/examples/0", "description": "x"}}, "examples": [{"type": "string", "pattern": "(a+)+$"}]},
        "external ref": {"type": "object", "properties": {"a": {"$ref": "https://evil.example.com/schema.json", "description": "x"}}},
        "too large": {"type": "object", "properties": {"a": {"type": "string", "description": "x" * 20000}}},
    }
    for label, schema in invalid_schemas.items():
        assert client.post(PATH, json=tool_add_body(ts_priv, params_schema=schema)).status_code == 422, label

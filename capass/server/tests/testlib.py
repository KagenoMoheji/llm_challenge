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
import base64
import secrets
from datetime import datetime, timezone
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey
from cryptography.hazmat.primitives.serialization import Encoding, PublicFormat
from capass_server.common.crypto import encrypt_token
from capass_server.common.signature import (
    SIGN_CONTEXT_AGENT_EXEC,
    SIGN_CONTEXT_AGENT_LISTTOOLS,
    SIGN_CONTEXT_AGENT_REGISTER,
    SIGN_CONTEXT_TOOLSERVER_CHKEY_NEW,
    SIGN_CONTEXT_TOOLSERVER_CHKEY_OLD,
    SIGN_CONTEXT_TOOLSERVER_REGISTER,
    build_signing_message,
)
from capass_server.models.entities import ApprovalStatus, TblAdmin, TblAgent, TblAgentTool, TblToolServer

APPLICANT_EMAIL = "applicant@example.com"
ADMIN_EMAIL = "admin@example.com"
EXEC_URL = "https://toolserver.example.com/capass/exec"
# テスト用のparamsのスキーマ(JSON Schema)。sqlパラメータ(文字列、必須)だけを受け付ける
PARAMS_SCHEMA = {
    "type": "object",
    "properties": {"sql": {"type": "string", "description": "実行するSQL文(string)"}},
    "required": ["sql"],
    "additionalProperties": False,
}


def pub_b64(priv: Ed25519PrivateKey) -> str:
    return base64.b64encode(priv.public_key().public_bytes(Encoding.Raw, PublicFormat.Raw)).decode()


def signed_body(priv: Ed25519PrivateKey, sign_context: bytes, fields: dict, path_params: dict | None = None, signed_at: int | None = None) -> dict:
    """リクエストボディを作り、署名する(署名対象 = signature以外の全フィールド + URLパスのパラメータ)。"""
    body = {**fields, "signed_at": int(time.time()) if signed_at is None else signed_at}
    payload = {**body, **(path_params or {})}
    body["signature"] = base64.b64encode(priv.sign(build_signing_message(sign_context, payload))).decode()
    return body


def toolserver_register_body(priv: Ed25519PrivateKey, name: str = "社内ツールサーバA", email: str = APPLICANT_EMAIL, exec_url: str = EXEC_URL, signed_at: int | None = None) -> dict:
    fields = {"tool_server_public_key": pub_b64(priv), "tool_server_name": name, "tool_server_exec_url": exec_url, "applicant_email": email}
    return signed_body(priv, SIGN_CONTEXT_TOOLSERVER_REGISTER, fields, signed_at=signed_at)


def agent_register_body(priv: Ed25519PrivateKey, agent_id: str = "agent-1", email: str = APPLICANT_EMAIL, signed_at: int | None = None) -> dict:
    fields = {"agent_id": agent_id, "agent_public_key": pub_b64(priv), "applicant_email": email}
    return signed_body(priv, SIGN_CONTEXT_AGENT_REGISTER, fields, signed_at=signed_at)


def list_tools_headers(agent_priv: Ed25519PrivateKey, agent_id: str, signed_at: int | None = None) -> dict:
    """GET agents/{agent_id}/tools の署名ヘッダーを作る。署名対象は agent_id と signed_at。"""
    at = int(time.time()) if signed_at is None else signed_at
    message = build_signing_message(SIGN_CONTEXT_AGENT_LISTTOOLS, {"agent_id": agent_id, "signed_at": at})
    return {"X-CaPass-Signed-At": str(at), "X-CaPass-Signature": base64.b64encode(agent_priv.sign(message)).decode()}


def exec_body(agent_priv: Ed25519PrivateKey, agent_id: str, tool_endpoint: str, params: dict | None = None, nonce: str | None = None, signed_at: int | None = None) -> dict:
    fields = {"params": {"sql": "SELECT 1"} if params is None else params, "nonce": secrets.token_urlsafe(16) if nonce is None else nonce}
    return signed_body(agent_priv, SIGN_CONTEXT_AGENT_EXEC, fields, path_params={"agent_id": agent_id, "tool_endpoint": tool_endpoint}, signed_at=signed_at)


def chkey_body(old_priv: Ed25519PrivateKey, new_priv: Ed25519PrivateKey, toolserver_id: int, signed_at: int | None = None, old_context: bytes = SIGN_CONTEXT_TOOLSERVER_CHKEY_OLD, new_context: bytes = SIGN_CONTEXT_TOOLSERVER_CHKEY_NEW) -> dict:
    """ツールサーバのリプレース(chkey)のボディを作る。旧・新の鍵が、同じ内容(旧公開鍵・新公開鍵・toolserver_id・signed_at)に、それぞれ署名する。"""
    at = int(time.time()) if signed_at is None else signed_at
    payload = {"toolserver_id": toolserver_id, "old_tool_server_public_key": pub_b64(old_priv), "new_tool_server_public_key": pub_b64(new_priv), "signed_at": at}
    return {
        "new_tool_server_public_key": pub_b64(new_priv),
        "signed_at": at,
        "signature": base64.b64encode(old_priv.sign(build_signing_message(old_context, payload))).decode(),
        "new_key_signature": base64.b64encode(new_priv.sign(build_signing_message(new_context, payload))).decode(),
    }


def approve_body(admin_priv: Ed25519PrivateKey, sign_context: bytes, path_params: dict, signed_at: int | None = None) -> dict:
    fields = {"admin_public_key": pub_b64(admin_priv)}
    return signed_body(admin_priv, sign_context, fields, path_params=path_params, signed_at=signed_at)


def seed_admin(session_factory, priv: Ed25519PrivateKey, email: str = ADMIN_EMAIL, is_active: bool = True) -> None:
    """tbl_adminに管理者を直接登録する(管理者がSQLクライアントで登録する運用の代わり)。"""
    with session_factory() as db:
        db.add(TblAdmin(admin_email=email, admin_public_key=pub_b64(priv), is_active=is_active, created_at=datetime.now(timezone.utc)))
        db.commit()


def seed_tool_server(session_factory, priv: Ed25519PrivateKey, status: ApprovalStatus = ApprovalStatus.APPROVED, name: str = "test-tool-server") -> int:
    """tbl_tool_serverにレコードを直接登録する(登録API/承認APIを経由しない前提データ作成用)。idを返す。"""
    now = datetime.now(timezone.utc)
    approved = status == ApprovalStatus.APPROVED
    with session_factory() as db:
        row = TblToolServer(
            tool_server_public_key=pub_b64(priv),
            tool_server_name=name,
            exec_url=EXEC_URL,
            applicant_email=APPLICANT_EMAIL,
            approver_email=ADMIN_EMAIL if approved else None,
            status=status.value,
            created_at=now,
            approved_at=now if approved else None,
        )
        db.add(row)
        db.commit()
        return row.id


def seed_agent(session_factory, priv: Ed25519PrivateKey, agent_id: str = "agent-1", status: ApprovalStatus = ApprovalStatus.APPROVED) -> str:
    """tbl_agentにレコードを直接登録する(前提データ作成用)。agent_idを返す。"""
    now = datetime.now(timezone.utc)
    approved = status == ApprovalStatus.APPROVED
    with session_factory() as db:
        db.add(
            TblAgent(
                agent_id=agent_id,
                agent_public_key=pub_b64(priv),
                applicant_email=APPLICANT_EMAIL,
                approver_email=ADMIN_EMAIL if approved else None,
                status=status.value,
                created_at=now,
                approved_at=now if approved else None,
            )
        )
        db.commit()
    return agent_id


def seed_agent_tool(session_factory, agent_id: str, tool_endpoint: str, tool_server_priv: Ed25519PrivateKey, token: str = "proxy-token-1", context: str = "テスト用のツール", locked: bool = False, params_schema: dict | None = None) -> None:
    """tbl_agent_toolにレコードを直接登録する(addtool APIを経由しない前提データ作成用)。トークンは暗号化して保存する。"""
    now = datetime.now(timezone.utc)
    with session_factory() as db:
        db.add(
            TblAgentTool(
                tool_endpoint=tool_endpoint,
                context=context,
                params_schema=PARAMS_SCHEMA if params_schema is None else params_schema,
                agent_id=agent_id,
                tool_proxy_token_encrypted=encrypt_token(token),
                tool_proxy_token_updated_at=now,
                tool_used_at=None,
                locked=locked,
                tool_server_public_key=pub_b64(tool_server_priv),
                created_at=now,
            )
        )
        db.commit()

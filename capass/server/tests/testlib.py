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
from datetime import datetime, timezone
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey
from cryptography.hazmat.primitives.serialization import Encoding, PublicFormat
from capass_server.common.signature import (
    SIGN_CONTEXT_AGENT_REGISTER,
    SIGN_CONTEXT_TOOLSERVER_REGISTER,
    build_signing_message,
)
from capass_server.models.entities import ApprovalStatus, TblAdmin, TblAgent, TblToolServer

APPLICANT_EMAIL = "applicant@example.com"
ADMIN_EMAIL = "admin@example.com"


def pub_b64(priv: Ed25519PrivateKey) -> str:
    return base64.b64encode(priv.public_key().public_bytes(Encoding.Raw, PublicFormat.Raw)).decode()


def signed_body(priv: Ed25519PrivateKey, sign_context: bytes, fields: dict, path_params: dict | None = None, signed_at: int | None = None) -> dict:
    """リクエストボディを作り、署名する(署名対象 = signature以外の全フィールド + URLパスのパラメータ)。"""
    body = {**fields, "signed_at": int(time.time()) if signed_at is None else signed_at}
    payload = {**body, **(path_params or {})}
    body["signature"] = base64.b64encode(priv.sign(build_signing_message(sign_context, payload))).decode()
    return body


def toolserver_register_body(priv: Ed25519PrivateKey, name: str = "社内ツールサーバA", email: str = APPLICANT_EMAIL, signed_at: int | None = None) -> dict:
    fields = {"tool_server_public_key": pub_b64(priv), "tool_server_name": name, "applicant_email": email}
    return signed_body(priv, SIGN_CONTEXT_TOOLSERVER_REGISTER, fields, signed_at=signed_at)


def agent_register_body(priv: Ed25519PrivateKey, agent_id: str = "agent-1", email: str = APPLICANT_EMAIL, signed_at: int | None = None) -> dict:
    fields = {"agent_id": agent_id, "agent_public_key": pub_b64(priv), "applicant_email": email}
    return signed_body(priv, SIGN_CONTEXT_AGENT_REGISTER, fields, signed_at=signed_at)


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

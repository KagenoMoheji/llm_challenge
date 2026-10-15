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
from capass_server.common.signature import build_signing_message
from capass_server.models.entities import ApprovalStatus, TblAgent, TblToolServer


def pub_b64(priv: Ed25519PrivateKey) -> str:
    return base64.b64encode(priv.public_key().public_bytes(Encoding.Raw, PublicFormat.Raw)).decode()


def signed_body(priv: Ed25519PrivateKey, sign_context: bytes, fields: dict, path_params: dict | None = None, signed_at: int | None = None) -> dict:
    """リクエストボディを作り、署名する(署名対象 = signature以外の全フィールド + URLパスのパラメータ)。"""
    body = {**fields, "signed_at": int(time.time()) if signed_at is None else signed_at}
    payload = {**body, **(path_params or {})}
    body["signature"] = base64.b64encode(priv.sign(build_signing_message(sign_context, payload))).decode()
    return body


def seed_tool_server(session_factory, priv: Ed25519PrivateKey, status: ApprovalStatus = ApprovalStatus.APPROVED, name: str = "test-tool-server") -> int:
    """tbl_tool_serverにレコードを直接登録する(登録API/承認APIを経由しない前提データ作成用)。idを返す。"""
    now = datetime.now(timezone.utc)
    with session_factory() as db:
        row = TblToolServer(
            tool_server_public_key=pub_b64(priv),
            tool_server_name=name,
            status=status.value,
            created_at=now,
            approved_at=now if status == ApprovalStatus.APPROVED else None,
        )
        db.add(row)
        db.commit()
        return row.id


def seed_agent(session_factory, priv: Ed25519PrivateKey, agent_id: str = "agent-1", status: ApprovalStatus = ApprovalStatus.APPROVED) -> str:
    """tbl_agentにレコードを直接登録する(前提データ作成用)。agent_idを返す。"""
    now = datetime.now(timezone.utc)
    with session_factory() as db:
        db.add(
            TblAgent(
                agent_id=agent_id,
                agent_public_key=pub_b64(priv),
                status=status.value,
                created_at=now,
                approved_at=now if status == ApprovalStatus.APPROVED else None,
            )
        )
        db.commit()
    return agent_id

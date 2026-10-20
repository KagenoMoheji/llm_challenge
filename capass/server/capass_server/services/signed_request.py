import os
import inspect
import sys
import time
import traceback
PYPATH = os.path.dirname(os.path.abspath(inspect.getfile(inspect.currentframe())))
MODNAME = os.path.splitext(os.path.basename(inspect.getfile(inspect.currentframe())))[0]

# その他のモジュールやROOTPATHのディレクトリ起点の相対パスでのimport
from datetime import datetime, timezone
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session
from capass_server.common.config import SIGNATURE_MAX_SKEW_SEC
from capass_server.common.errors import (
    AgentNotApprovedError,
    InvalidSignatureError,
    NotAdminError,
    ReplayedRequestError,
    SignatureExpiredError,
)
from capass_server.common.signature import build_signing_message, is_within_skew, verify_ed25519
from capass_server.models import mappers
from capass_server.models.entities import ApprovalStatus, TblAdmin, TblAgent, TblRequestNonce


def verify_signed_request(public_key_b64: str, sign_context: bytes, payload: dict, signature_b64: str) -> None:
    """署名付きリクエストを検証する。署名時刻が許容範囲外ならSignatureExpiredError、署名が不正ならInvalidSignatureError。
    DB参照より先に呼び出し、未認証のリクエストに登録有無などを知らせないようにする。"""
    if not is_within_skew(payload["signed_at"], SIGNATURE_MAX_SKEW_SEC):
        raise SignatureExpiredError()
    message = build_signing_message(sign_context, payload)
    if not verify_ed25519(public_key_b64, message, signature_b64):
        raise InvalidSignatureError()


def verify_admin_request(db: Session, admin_public_key_b64: str, sign_context: bytes, payload: dict, signature_b64: str) -> TblAdmin:
    """管理者による署名付きリクエストを検証し、管理者のレコードを返す。
    署名の検証後に、署名した公開鍵がtbl_adminに登録された有効な管理者のものかを確認する(違えばNotAdminError)。"""
    verify_signed_request(admin_public_key_b64, sign_context, payload, signature_b64)
    admin = mappers.find_tbl_admin_by_public_key(db, admin_public_key_b64)
    if admin is None or not admin.is_active:
        raise NotAdminError()
    return admin


def verify_agent_request(db: Session, agent_id: str, sign_context: bytes, payload: dict, signature_b64: str) -> TblAgent:
    """AIエージェントによる署名付きリクエストを認証し、AIエージェントのレコードを返す。
    署名の検証には、tbl_agentに登録された(承認時に確認された)公開鍵を使う。

    存在しないagent_idは、署名不正と区別しない(InvalidSignatureError)。未認証の相手に、AIエージェントの有無を知らせないため。
    認証できた後に、承認済みでなければAgentNotApprovedErrorを送出する(認証済みの本人にだけ、自分のステータスを伝える)。
    """
    agent = mappers.find_tbl_agent_by_agent_id(db, agent_id)
    if agent is None:
        raise InvalidSignatureError()
    verify_signed_request(agent.agent_public_key, sign_context, payload, signature_b64)
    if agent.status != ApprovalStatus.APPROVED:
        raise AgentNotApprovedError(agent.status)
    return agent


def consume_request_nonce(db: Session, agent_id: str, nonce: str, signed_at: int) -> None:
    """nonceを使用済みとして記録する(リプレイ防止)。すでに使われていればReplayedRequestError。副作用のあるリクエスト(ツール実行など)に使う。
    nonceは、署名時刻が許容範囲を過ぎるまで(署名時刻でも拒否される時点まで)記録する。期限切れの記録は、ここで削除する。"""
    now = datetime.now(timezone.utc)
    expires_at = datetime.fromtimestamp(signed_at + SIGNATURE_MAX_SKEW_SEC, tz=timezone.utc)
    try:
        mappers.delete_expired_tbl_request_nonce(db, now)
        mappers.insert_tbl_request_nonce(db, TblRequestNonce(agent_id=agent_id, nonce=nonce, expires_at=expires_at))
        db.commit()
    except IntegrityError:
        db.rollback()
        raise ReplayedRequestError()

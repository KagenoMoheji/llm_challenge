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
from capass_server.common.crypto import encrypt_token
from capass_server.common.signature import build_signing_message, is_within_skew, verify_ed25519
from capass_server.models import mappers
from capass_server.models.entities import ToolRegistration
from capass_server.schemas.register import RegisterRequest
from capass_server.common.errors import (
    DuplicateRegistrationError,
    InvalidSignatureError,
    SignatureExpiredError,
)

# registの署名メッセージのプレフィックス(クライアント側と一致させること。変更時はバージョン部分を上げる)
SIGN_CONTEXT_REGISTER = b"capass-register-v1\n"


def register_tool(db: Session, req: RegisterRequest) -> ToolRegistration:
    """ツール/AIエージェント/ツールサーバ公開鍵を登録する。初回を含め、登録の都度、リクエスト内の公開鍵で署名を検証する。"""
    # 1. 署名時刻の検証(リプレイ対策)
    if not is_within_skew(req.signed_at, SIGNATURE_MAX_SKEW_SEC):
        raise SignatureExpiredError()

    # 2. 署名の検証(DB参照より先に行い、未認証のリクエストに登録有無を知らせない)
    message = build_signing_message(SIGN_CONTEXT_REGISTER, req.signed_payload())
    if not verify_ed25519(req.tool_server_public_key, message, req.signature):
        raise InvalidSignatureError()

    # 3. 重複チェック(同一の[ツールエンドポイント/AIエージェント]は新規登録不可。更新はchtkn/chkeyで行う)
    if mappers.find_tool_registration(db, req.tool_endpoint, req.agent_id) is not None:
        raise DuplicateRegistrationError()

    # 4. 登録(同時リクエストによる重複は、一意制約違反として検出する)
    now = datetime.now(timezone.utc)
    registration = ToolRegistration(
        tool_endpoint=req.tool_endpoint,
        context=req.context,
        agent_id=req.agent_id,
        tool_proxy_token_encrypted=encrypt_token(req.tool_proxy_token),
        tool_proxy_token_updated_at=now,
        tool_used_at=None,
        locked=False,
        tool_server_public_key=req.tool_server_public_key,
        created_at=now,
    )
    try:
        mappers.insert_tool_registration(db, registration)
        db.commit()
    except IntegrityError:
        db.rollback()
        raise DuplicateRegistrationError()
    return registration

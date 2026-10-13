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
from capass_server.common.signature import SIGN_CONTEXT_REGISTER, build_signing_message, is_within_skew, verify_ed25519
from capass_server.models import mappers
from capass_server.models.entities import TblAgentTool, ToolServerStatus
from capass_server.schemas.register import RegisterRequest
from capass_server.common.errors import (
    DuplicateRegistrationError,
    InvalidSignatureError,
    SignatureExpiredError,
    ToolServerNotApprovedError,
)


def register_tool(db: Session, req: RegisterRequest) -> TblAgentTool:
    """ツール/AIエージェント/ツールサーバ公開鍵を登録する。初回を含め、登録の都度、リクエスト内の公開鍵で署名を検証し、その公開鍵がCaPassサーバ管理者に承認済みかを確認する。"""
    # 1. 署名時刻の検証(リプレイ対策)
    if not is_within_skew(req.signed_at, SIGNATURE_MAX_SKEW_SEC):
        raise SignatureExpiredError()

    # 2. 署名の検証(DB参照より先に行い、未認証のリクエストに登録有無を知らせない)
    message = build_signing_message(SIGN_CONTEXT_REGISTER, req.signed_payload())
    if not verify_ed25519(req.tool_server_public_key, message, req.signature):
        raise InvalidSignatureError()

    # 3. ツールサーバ公開鍵の承認確認(署名検証済みなので、鍵の持ち主であることは確認できている。次に、管理者が承認した鍵かを確認する)
    tool_server = mappers.find_tbl_tool_server_by_public_key(db, req.tool_server_public_key)
    if tool_server is None or tool_server.status != ToolServerStatus.APPROVED:
        raise ToolServerNotApprovedError(None if tool_server is None else tool_server.status)

    # 4. 重複チェック(同一の[ツールエンドポイント/AIエージェント]は新規登録不可。更新はchtkn/chkeyで行う)
    if mappers.find_tbl_agent_tool(db, req.tool_endpoint, req.agent_id) is not None:
        raise DuplicateRegistrationError()

    # 5. 登録(同時リクエストによる重複は、一意制約違反として検出する)
    now = datetime.now(timezone.utc)
    agent_tool = TblAgentTool(
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
        mappers.insert_tbl_agent_tool(db, agent_tool)
        db.commit()
    except IntegrityError:
        db.rollback()
        raise DuplicateRegistrationError()
    return agent_tool

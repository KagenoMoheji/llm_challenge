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
from capass_server.common.errors import (
    DuplicateToolServerError,
    InvalidApprovalStateError,
    ToolServerNotFoundError,
)
from capass_server.common.signature import SIGN_CONTEXT_TOOLSERVER_APPROVE, SIGN_CONTEXT_TOOLSERVER_REGISTER
from capass_server.models import mappers
from capass_server.models.entities import ApprovalStatus, TblToolServer
from capass_server.schemas.approve import ApproveRequest
from capass_server.schemas.tool_server import ToolServerRegisterRequest
from capass_server.services.signed_request import verify_admin_request, verify_signed_request


def register_tool_server(db: Session, req: ToolServerRegisterRequest) -> TblToolServer:
    """ツールサーバ(公開鍵)を承認待ち(pending)で初回登録する。自身の公開鍵で署名を検証する(鍵の所持証明。登録してよい相手かの確認は、管理者の承認で行う)。"""
    # 1. 署名の検証
    verify_signed_request(req.tool_server_public_key, SIGN_CONTEXT_TOOLSERVER_REGISTER, req.signed_payload(), req.signature)

    # 2. 重複チェック(同一公開鍵は、承認ステータスによらず再登録できない)
    existing = mappers.find_tbl_tool_server_by_public_key(db, req.tool_server_public_key)
    if existing is not None:
        raise DuplicateToolServerError(existing.status)

    # 3. 登録(同時リクエストによる重複は、一意制約違反として検出する)
    tool_server = TblToolServer(
        tool_server_public_key=req.tool_server_public_key,
        tool_server_name=req.tool_server_name,
        status=ApprovalStatus.PENDING.value,
        created_at=datetime.now(timezone.utc),
        approved_at=None,
    )
    try:
        mappers.insert_tbl_tool_server(db, tool_server)
        db.commit()
    except IntegrityError:
        db.rollback()
        raise DuplicateToolServerError()
    return tool_server


def approve_tool_server(db: Session, tool_server_id: int, req: ApproveRequest) -> TblToolServer:
    """ツールサーバを承認する(CaPassサーバ管理者のみ)。pending→approved。承認済みなら何もせず成功(冪等)。revokedは承認できない。"""
    # 1. 管理者の署名の検証(URLパスのtoolserver_idも署名対象)
    verify_admin_request(
        req.admin_public_key,
        SIGN_CONTEXT_TOOLSERVER_APPROVE,
        req.signed_payload(toolserver_id=tool_server_id),
        req.signature,
    )

    # 2. 対象の取得と状態遷移
    tool_server = mappers.find_tbl_tool_server_by_id(db, tool_server_id)
    if tool_server is None:
        raise ToolServerNotFoundError()
    if tool_server.status == ApprovalStatus.APPROVED:
        return tool_server
    if tool_server.status != ApprovalStatus.PENDING:
        raise InvalidApprovalStateError(tool_server.status)

    tool_server.status = ApprovalStatus.APPROVED.value
    tool_server.approved_at = datetime.now(timezone.utc)
    db.commit()
    return tool_server

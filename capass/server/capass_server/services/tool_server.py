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
from capass_server.common.config import TOOL_SERVER_ALLOW_HTTP
from capass_server.common.errors import (
    DuplicateToolServerError,
    InvalidApprovalStateError,
    InvalidNewKeySignatureError,
    InvalidSignatureError,
    InvalidToolServerUrlError,
    ToolServerNotApprovedError,
    ToolServerNotFoundError,
)
from capass_server.common.signature import (
    SIGN_CONTEXT_TOOLSERVER_APPROVE,
    SIGN_CONTEXT_TOOLSERVER_CHKEY_NEW,
    SIGN_CONTEXT_TOOLSERVER_CHKEY_OLD,
    SIGN_CONTEXT_TOOLSERVER_REGISTER,
)
from capass_server.models import mappers
from capass_server.models.entities import ApprovalStatus, TblToolServer
from capass_server.schemas.approve import ApproveRequest
from capass_server.schemas.tool_server import ToolServerChangeKeyRequest, ToolServerRegisterRequest
from capass_server.services.signed_request import verify_admin_request, verify_signed_request


def register_tool_server(db: Session, req: ToolServerRegisterRequest) -> TblToolServer:
    """ツールサーバ(公開鍵)を承認待ち(pending)で初回登録する。自身の公開鍵で署名を検証する(鍵の所持証明。登録してよい相手かの確認は、管理者の承認で行う)。"""
    # 1. 署名の検証
    verify_signed_request(req.tool_server_public_key, SIGN_CONTEXT_TOOLSERVER_REGISTER, req.signed_payload(), req.signature)

    # 2. 実行URLの確認(既定ではhttpsのみ。ローカル開発などでhttpを使う場合は、設定 TOOL_SERVER_ALLOW_HTTP で許可する)
    if not TOOL_SERVER_ALLOW_HTTP and not req.tool_server_exec_url.lower().startswith("https://"):
        raise InvalidToolServerUrlError()

    # 3. 重複チェック(同一公開鍵は、承認ステータスによらず再登録できない)
    existing = mappers.find_tbl_tool_server_by_public_key(db, req.tool_server_public_key)
    if existing is not None:
        raise DuplicateToolServerError(existing.status)

    # 4. 登録(同時リクエストによる重複は、一意制約違反として検出する)
    tool_server = TblToolServer(
        tool_server_public_key=req.tool_server_public_key,
        tool_server_name=req.tool_server_name,
        exec_url=req.tool_server_exec_url,
        applicant_email=req.applicant_email,
        approver_email=None,
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
    admin = verify_admin_request(
        db,
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
    tool_server.approver_email = admin.admin_email  # 承認した管理者のメアドを記録する
    db.commit()
    return tool_server


def change_tool_server_key(db: Session, tool_server_id: int, req: ToolServerChangeKeyRequest) -> TblToolServer:
    """ツールサーバのリプレース: 登録されているツールサーバの公開鍵を、新しい公開鍵に更新する(承認のやり直しは不要)。

    旧ツールサーバ(現在登録されている鍵)と、新ツールサーバ(新しい鍵)の、両方の署名が必要。
    ツールサーバのレコード(ステータス、名称、実行URL)は引き継がれ、そのツールサーバのツール(tbl_agent_tool)の公開鍵も、新しい鍵に更新される。
    実行URLは変わらないので、新ツールサーバは、同じURLで受け付けること(DNSやロードバランサの切り替えなど)。
    """
    # 1. 対象の取得。存在しないtoolserver_idは、署名不正と区別しない(未認証の相手に、IDの有無を知らせないため)
    tool_server = mappers.find_tbl_tool_server_by_id(db, tool_server_id)
    if tool_server is None:
        raise InvalidSignatureError()
    old_public_key = tool_server.tool_server_public_key

    # 2. 署名の検証。旧→新の順(旧の署名で、まず登録元ツールサーバと確認できてから、新の署名を検証する)。
    #    署名対象は、旧・新で同じ内容(旧公開鍵は、サーバに登録されている値を使う)
    payload = req.signed_payload(toolserver_id=tool_server_id, old_tool_server_public_key=old_public_key)
    verify_signed_request(old_public_key, SIGN_CONTEXT_TOOLSERVER_CHKEY_OLD, payload, req.signature)
    try:
        verify_signed_request(req.new_tool_server_public_key, SIGN_CONTEXT_TOOLSERVER_CHKEY_NEW, payload, req.new_key_signature)
    except InvalidSignatureError:
        raise InvalidNewKeySignatureError()

    # 3. 承認済みのツールサーバだけが、リプレースできる
    if tool_server.status != ApprovalStatus.APPROVED:
        raise ToolServerNotApprovedError(tool_server.status)

    # 4. 新しい公開鍵が、すでに登録されていない(現在の公開鍵と同じ場合を含む)
    existing = mappers.find_tbl_tool_server_by_public_key(db, req.new_tool_server_public_key)
    if existing is not None:
        raise DuplicateToolServerError(existing.status)

    # 5. 更新(公開鍵が、検証した旧公開鍵のままの場合だけ)。tbl_agent_toolの公開鍵は、外部キーのON UPDATE CASCADEで追従する
    try:
        if not mappers.update_tbl_tool_server_public_key(db, tool_server_id, old_public_key, req.new_tool_server_public_key):
            db.rollback()
            raise InvalidSignatureError()  # 検証してから更新するまでの間に、別のリクエストが公開鍵を更新した
        db.commit()
    except IntegrityError:
        db.rollback()
        raise DuplicateToolServerError()
    db.refresh(tool_server)
    return tool_server

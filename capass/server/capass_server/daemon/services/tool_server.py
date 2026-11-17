import os
import inspect
import sys
import time
import traceback
PYPATH = os.path.dirname(os.path.abspath(inspect.getfile(inspect.currentframe())))
MODNAME = os.path.splitext(os.path.basename(inspect.getfile(inspect.currentframe())))[0]

# その他のモジュールやROOTPATHのディレクトリ起点の相対パスでのimport
from datetime import datetime, timedelta, timezone
from typing import NamedTuple
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session
from capass_server.common.config import TOOL_SERVER_ALLOW_HTTP, TOOL_SERVER_RESERVATION_TTL_SEC, TOOL_SERVER_STANDBY_TTL_SEC
from capass_server.common.errors import (
    DuplicateToolServerError,
    InvalidApprovalStateError,
    InvalidNewKeySignatureError,
    InvalidSignatureError,
    InvalidToolServerUrlError,
    ReplacementNotAllowedError,
    ToolServerNotApprovedError,
    ToolServerNotFoundError,
)
from capass_server.common.signature import (
    SIGN_CONTEXT_TOOLSERVER_APPROVE,
    SIGN_CONTEXT_TOOLSERVER_REGISTER,
    SIGN_CONTEXT_TOOLSERVER_REPLACE_ACTIVATE_NEW,
    SIGN_CONTEXT_TOOLSERVER_REPLACE_ACTIVATE_OLD,
    SIGN_CONTEXT_TOOLSERVER_REPLACE_RESERVE,
    SIGN_CONTEXT_TOOLSERVER_REPLACE_ROLLBACK,
)
from capass_server.models import mappers
from capass_server.models.entities import ApprovalStatus, TblToolServer
from capass_server.schemas.approve import ApproveRequest
from capass_server.schemas.tool_server import (
    ToolServerRegisterRequest,
    ToolServerReplaceActivateRequest,
    ToolServerReplaceReserveRequest,
    ToolServerReplaceRollbackRequest,
)
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


# ---------- ツールサーバのリプレース(reserve → activate → rollback) ----------
# 旧ツールサーバ(ステータス: approved)を、新ツールサーバ(後継)へ、置き換える。
#   reserve : CaPassサーバ管理者が、新ツールサーバ(実行URLと公開鍵)を、旧の後継として、事前に承認する。新は reserved(期限つき)
#   activate: 旧・新の両方の署名で、ツールを新へ付け替える。新が approved、旧が standby(期限つき)になる
#   rollback: 旧の署名だけで、ツールを旧へ戻す。旧が approved、新が standby(期限つき)になる
# 切り替え・切り戻しは、ツールサーバ側だけで、すぐ行える。送り先は、管理者が事前に承認した(実行URL, 公開鍵)の間でしか、変えられない。


class ReplacementResult(NamedTuple):
    active: TblToolServer  # アクティブ(approved)になったツールサーバ
    standby: TblToolServer  # 待機中(standby)になったツールサーバ
    standby_until: datetime  # 待機中のツールサーバへ、切り替え(切り戻し)できる期限
    moved_tools: int  # 付け替えたツールの数


def _is_expired(expires_at: datetime | None, now: datetime) -> bool:
    if expires_at is None:
        return True
    if expires_at.tzinfo is None:  # SQLiteなどは、タイムゾーンなしで返す(保存しているのは、UTC)
        expires_at = expires_at.replace(tzinfo=timezone.utc)
    return expires_at <= now


def _switch_active_tool_server(db: Session, current: TblToolServer, target: TblToolServer, target_expected_status: ApprovalStatus, now: datetime) -> ReplacementResult:
    """アクティブなツールサーバを、currentからtargetへ切り替える。currentは待機中(standby)に、targetはアクティブ(approved)になり、ツールを付け替える。
    ステータスは、期待した値のままの場合だけ更新する(並行して別のリクエストが切り替えていたら、全て取り消す)。"""
    standby_until = now + timedelta(seconds=TOOL_SERVER_STANDBY_TTL_SEC)
    current_updated = mappers.update_tbl_tool_server_status(db, current.id, ApprovalStatus.APPROVED.value, ApprovalStatus.STANDBY.value, standby_until)
    target_updated = mappers.update_tbl_tool_server_status(db, target.id, target_expected_status.value, ApprovalStatus.APPROVED.value, None)
    if not (current_updated and target_updated):
        db.rollback()
        raise ReplacementNotAllowedError("the tool server status was changed by another request")
    moved_tools = mappers.move_tbl_tool_to_tool_server(db, current.id, target.id)
    db.commit()
    return ReplacementResult(active=target, standby=current, standby_until=standby_until, moved_tools=moved_tools)


def reserve_tool_server_replacement(db: Session, predecessor_id: int, req: ToolServerReplaceReserveRequest) -> TblToolServer:
    """新ツールサーバを、旧ツールサーバ(predecessor_id)の後継として、予約(reserved)する(CaPassサーバ管理者のみ)。"""
    # 1. 管理者の署名の検証(URLパスのtoolserver_idも署名対象。管理者は、申告された実行URLと公開鍵に、署名する)
    admin = verify_admin_request(
        db,
        req.admin_public_key,
        SIGN_CONTEXT_TOOLSERVER_REPLACE_RESERVE,
        req.signed_payload(toolserver_id=predecessor_id),
        req.signature,
    )

    # 2. 実行URLの確認(register と同じ。既定ではhttpsのみ。プライベートIPのURLも使える)
    if not TOOL_SERVER_ALLOW_HTTP and not req.new_tool_server_exec_url.lower().startswith("https://"):
        raise InvalidToolServerUrlError()

    # 3. 旧ツールサーバ(アクティブ)の確認と、重複の確認
    predecessor = mappers.find_tbl_tool_server_by_id(db, predecessor_id)
    if predecessor is None:
        raise ToolServerNotFoundError()
    if predecessor.status != ApprovalStatus.APPROVED:
        raise ReplacementNotAllowedError(f"the tool server is not active (status: {predecessor.status})")
    now = datetime.now(timezone.utc)
    if mappers.find_tbl_tool_server_reserved_successor(db, predecessor.id, now) is not None:
        raise ReplacementNotAllowedError("a reservation already exists for the tool server")
    existing = mappers.find_tbl_tool_server_by_public_key(db, req.new_tool_server_public_key)
    if existing is not None:
        raise DuplicateToolServerError(existing.status)

    # 4. 予約(承認済みの後継として登録する。期限を過ぎると、切り替えられない)
    successor = TblToolServer(
        tool_server_public_key=req.new_tool_server_public_key,
        tool_server_name=req.new_tool_server_name,
        exec_url=req.new_tool_server_exec_url,
        applicant_email=req.applicant_email,
        approver_email=admin.admin_email,
        status=ApprovalStatus.RESERVED.value,
        replaces_tool_server_id=predecessor.id,
        status_expires_at=now + timedelta(seconds=TOOL_SERVER_RESERVATION_TTL_SEC),
        created_at=now,
        approved_at=now,
    )
    try:
        mappers.insert_tbl_tool_server(db, successor)
        db.commit()
    except IntegrityError:
        db.rollback()
        raise DuplicateToolServerError()
    return successor


def activate_tool_server_replacement(db: Session, predecessor_id: int, req: ToolServerReplaceActivateRequest) -> ReplacementResult:
    """予約済みの新ツールサーバへ、ツールを切り替える。旧ツールサーバ(predecessor_id)と、新ツールサーバの、両方の署名が必要。
    新ツールサーバは、予約(reserved)または待機中(standby。切り戻した後の、再切り替え)で、期限内であること。"""
    # 1. 対象の取得。存在しないtoolserver_idは、署名不正と区別しない(未認証の相手に、IDの有無を知らせないため)
    predecessor = mappers.find_tbl_tool_server_by_id(db, predecessor_id)
    if predecessor is None:
        raise InvalidSignatureError()
    old_public_key = predecessor.tool_server_public_key

    # 2. 署名の検証。旧→新の順(旧の署名で、まず登録元と確認できてから、新の署名を検証する)。署名対象は、旧・新で同じ内容
    payload = req.signed_payload(toolserver_id=predecessor_id, old_tool_server_public_key=old_public_key)
    verify_signed_request(old_public_key, SIGN_CONTEXT_TOOLSERVER_REPLACE_ACTIVATE_OLD, payload, req.signature)
    try:
        verify_signed_request(req.new_tool_server_public_key, SIGN_CONTEXT_TOOLSERVER_REPLACE_ACTIVATE_NEW, payload, req.new_key_signature)
    except InvalidSignatureError:
        raise InvalidNewKeySignatureError()

    # 3. 旧がアクティブで、新が、旧の後継として承認済み(予約、または待機中)で、期限内であること
    if predecessor.status != ApprovalStatus.APPROVED:
        raise ToolServerNotApprovedError(predecessor.status)
    successor = mappers.find_tbl_tool_server_by_public_key(db, req.new_tool_server_public_key)
    if (
        successor is None
        or successor.replaces_tool_server_id != predecessor.id
        or successor.status not in (ApprovalStatus.RESERVED, ApprovalStatus.STANDBY)
    ):
        raise ReplacementNotAllowedError("no reservation for the new public key")
    now = datetime.now(timezone.utc)
    if _is_expired(successor.status_expires_at, now):
        raise ReplacementNotAllowedError("the reservation has expired" if successor.status == ApprovalStatus.RESERVED else "the standby period has expired")

    # 4. 切り替え
    return _switch_active_tool_server(db, predecessor, successor, ApprovalStatus(successor.status), now)


def rollback_tool_server_replacement(db: Session, predecessor_id: int, req: ToolServerReplaceRollbackRequest) -> ReplacementResult:
    """旧ツールサーバ(predecessor_id。待機中)へ、ツールを切り戻す。新ツールサーバに不具合があっても使えるよう、旧ツールサーバの署名だけでよい。"""
    # 1. 対象の取得(存在しないtoolserver_idは、署名不正と区別しない)と、旧ツールサーバの署名の検証
    predecessor = mappers.find_tbl_tool_server_by_id(db, predecessor_id)
    if predecessor is None:
        raise InvalidSignatureError()
    old_public_key = predecessor.tool_server_public_key
    payload = req.signed_payload(toolserver_id=predecessor_id, tool_server_public_key=old_public_key)
    verify_signed_request(old_public_key, SIGN_CONTEXT_TOOLSERVER_REPLACE_ROLLBACK, payload, req.signature)

    # 2. 旧が待機中(standby)で、期限内で、アクティブな後継があること
    now = datetime.now(timezone.utc)
    if predecessor.status != ApprovalStatus.STANDBY:
        raise ReplacementNotAllowedError("the tool server is not in standby")
    if _is_expired(predecessor.status_expires_at, now):
        raise ReplacementNotAllowedError("the standby period has expired")
    successor = mappers.find_tbl_tool_server_active_successor(db, predecessor.id)
    if successor is None:
        raise ReplacementNotAllowedError("no active successor to roll back from")

    # 3. 切り戻し(後継を待機中に、旧をアクティブにする)
    return _switch_active_tool_server(db, successor, predecessor, ApprovalStatus.STANDBY, now)

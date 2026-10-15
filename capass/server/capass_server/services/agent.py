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
from capass_server.common.errors import AgentNotFoundError, DuplicateAgentError, InvalidApprovalStateError
from capass_server.common.signature import SIGN_CONTEXT_AGENT_APPROVE, SIGN_CONTEXT_AGENT_REGISTER
from capass_server.models import mappers
from capass_server.models.entities import ApprovalStatus, TblAgent
from capass_server.schemas.agent import AgentRegisterRequest
from capass_server.schemas.approve import ApproveRequest
from capass_server.services.signed_request import verify_admin_request, verify_signed_request


def register_agent(db: Session, req: AgentRegisterRequest) -> TblAgent:
    """AIエージェント(公開鍵)を承認待ち(pending)で初回登録する。自身の公開鍵で署名を検証する(鍵の所持証明。登録してよい相手かの確認は、管理者の承認で行う)。"""
    # 1. 署名の検証
    verify_signed_request(req.agent_public_key, SIGN_CONTEXT_AGENT_REGISTER, req.signed_payload(), req.signature)

    # 2. 重複チェック(同一のagent_idは、承認ステータスによらず再登録できない。公開鍵の重複は一意制約で検出する)
    if mappers.find_tbl_agent_by_agent_id(db, req.agent_id) is not None:
        raise DuplicateAgentError()

    # 3. 登録
    agent = TblAgent(
        agent_id=req.agent_id,
        agent_public_key=req.agent_public_key,
        status=ApprovalStatus.PENDING.value,
        created_at=datetime.now(timezone.utc),
        approved_at=None,
    )
    try:
        mappers.insert_tbl_agent(db, agent)
        db.commit()
    except IntegrityError:
        db.rollback()
        raise DuplicateAgentError()
    return agent


def approve_agent(db: Session, agent_id: str, req: ApproveRequest) -> TblAgent:
    """AIエージェントを承認する(CaPassサーバ管理者のみ)。pending→approved。承認済みなら何もせず成功(冪等)。revokedは承認できない。"""
    # 1. 管理者の署名の検証(URLパスのagent_idも署名対象)
    verify_admin_request(
        req.admin_public_key,
        SIGN_CONTEXT_AGENT_APPROVE,
        req.signed_payload(agent_id=agent_id),
        req.signature,
    )

    # 2. 対象の取得と状態遷移
    agent = mappers.find_tbl_agent_by_agent_id(db, agent_id)
    if agent is None:
        raise AgentNotFoundError()
    if agent.status == ApprovalStatus.APPROVED:
        return agent
    if agent.status != ApprovalStatus.PENDING:
        raise InvalidApprovalStateError(agent.status)

    agent.status = ApprovalStatus.APPROVED.value
    agent.approved_at = datetime.now(timezone.utc)
    db.commit()
    return agent

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
from capass_server.common.crypto import encrypt_token
from capass_server.common.errors import (
    AgentNotApprovedError,
    AgentNotFoundError,
    DuplicateAgentToolError,
    ToolServerNotApprovedError,
)
from capass_server.common.signature import SIGN_CONTEXT_AGENT_ADDTOOL
from capass_server.models import mappers
from capass_server.models.entities import ApprovalStatus, TblAgentTool
from capass_server.schemas.agent import AgentAddToolRequest
from capass_server.services.signed_request import verify_signed_request


def add_tool_to_agent(db: Session, agent_id: str, req: AgentAddToolRequest) -> TblAgentTool:
    """AIエージェントにツールを追加する。承認済みツールサーバの署名を検証し、承認済みのAIエージェントにのみ追加できる。"""
    # 1. 署名の検証(DB参照より先に行い、未認証のリクエストに登録有無を知らせない。URLパスのagent_idも署名対象)
    verify_signed_request(
        req.tool_server_public_key,
        SIGN_CONTEXT_AGENT_ADDTOOL,
        req.signed_payload(agent_id=agent_id),
        req.signature,
    )

    # 2. ツールサーバ公開鍵の承認確認(署名検証済みなので、鍵の持ち主であることは確認できている。次に、管理者が承認した鍵かを確認する)
    tool_server = mappers.find_tbl_tool_server_by_public_key(db, req.tool_server_public_key)
    if tool_server is None or tool_server.status != ApprovalStatus.APPROVED:
        raise ToolServerNotApprovedError(None if tool_server is None else tool_server.status)

    # 3. AIエージェントの存在・承認確認
    agent = mappers.find_tbl_agent_by_agent_id(db, agent_id)
    if agent is None:
        raise AgentNotFoundError()
    if agent.status != ApprovalStatus.APPROVED:
        raise AgentNotApprovedError(agent.status)

    # 4. 重複チェック(同一の[ツールエンドポイント/AIエージェント]は新規登録不可。更新はchtkn/chkeyで行う)
    if mappers.find_tbl_agent_tool(db, req.tool_endpoint, agent_id) is not None:
        raise DuplicateAgentToolError()

    # 5. 登録(同時リクエストによる重複は、一意制約違反として検出する)
    now = datetime.now(timezone.utc)
    agent_tool = TblAgentTool(
        tool_endpoint=req.tool_endpoint,
        context=req.context,
        agent_id=agent_id,
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
        raise DuplicateAgentToolError()
    return agent_tool

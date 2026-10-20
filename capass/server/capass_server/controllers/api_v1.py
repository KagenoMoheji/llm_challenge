import os
import inspect
import sys
import time
import traceback
PYPATH = os.path.dirname(os.path.abspath(inspect.getfile(inspect.currentframe())))
MODNAME = os.path.splitext(os.path.basename(inspect.getfile(inspect.currentframe())))[0]

# その他のモジュールやROOTPATHのディレクトリ起点の相対パスでのimport
from typing import Annotated
from fastapi import APIRouter, Depends, Header, Response
from sqlalchemy.orm import Session
from capass_server.common.db import get_db
from capass_server.common.globals import HEADER_SIGNATURE, HEADER_SIGNED_AT
from capass_server.controllers.dependencies import rate_limit_register
from capass_server.schemas.agent import (
    AgentAddToolRequest,
    AgentAddToolResponse,
    AgentApproveResponse,
    AgentExecRequest,
    AgentRegisterRequest,
    AgentRegisterResponse,
    AgentToolItem,
    AgentToolListResponse,
)
from capass_server.schemas.approve import ApproveRequest
from capass_server.schemas.tool_server import (
    ToolServerApproveResponse,
    ToolServerRegisterRequest,
    ToolServerRegisterResponse,
)
from capass_server.services.agent import approve_agent, register_agent
from capass_server.services.agent_tool import add_tool_to_agent, exec_agent_tool, list_executable_tools
from capass_server.services.tool_server import approve_tool_server, register_tool_server

router = APIRouter()


# ---------- ツールサーバ(公開鍵)の初回登録と承認 ----------
@router.post("/toolservers/register", status_code=201, response_model=ToolServerRegisterResponse, dependencies=[Depends(rate_limit_register)])
def toolservers_register(req: ToolServerRegisterRequest, db: Session = Depends(get_db)) -> ToolServerRegisterResponse:
    """ツールサーバ(公開鍵)の初回登録。承認待ち(pending)で登録され、CaPassサーバ管理者の承認後に利用できる。クライアントIPごとにレート制限がかかる。"""
    tool_server = register_tool_server(db, req)
    return ToolServerRegisterResponse(
        toolserver_id=tool_server.id,
        tool_server_name=tool_server.tool_server_name,
        tool_server_exec_url=tool_server.exec_url,
        applicant_email=tool_server.applicant_email,
        tool_server_public_key=tool_server.tool_server_public_key,
        status=tool_server.status,
        created_at=tool_server.created_at,
    )


@router.post("/toolservers/{toolserver_id}/approve", response_model=ToolServerApproveResponse)
def toolservers_approve(toolserver_id: int, req: ApproveRequest, db: Session = Depends(get_db)) -> ToolServerApproveResponse:
    """ツールサーバの登録承認(CaPassサーバ管理者のみ)。管理者の秘密鍵で署名したリクエストが必要。"""
    tool_server = approve_tool_server(db, toolserver_id, req)
    return ToolServerApproveResponse(
        toolserver_id=tool_server.id,
        tool_server_name=tool_server.tool_server_name,
        tool_server_exec_url=tool_server.exec_url,
        applicant_email=tool_server.applicant_email,
        approver_email=tool_server.approver_email,
        tool_server_public_key=tool_server.tool_server_public_key,
        status=tool_server.status,
        approved_at=tool_server.approved_at,
    )


# ---------- AIエージェント(公開鍵)の初回登録と承認 ----------
@router.post("/agents/register", status_code=201, response_model=AgentRegisterResponse, dependencies=[Depends(rate_limit_register)])
def agents_register(req: AgentRegisterRequest, db: Session = Depends(get_db)) -> AgentRegisterResponse:
    """AIエージェント(公開鍵)の初回登録。承認待ち(pending)で登録され、CaPassサーバ管理者の承認後に利用できる。クライアントIPごとにレート制限がかかる。"""
    agent = register_agent(db, req)
    return AgentRegisterResponse(
        agent_id=agent.agent_id,
        agent_public_key=agent.agent_public_key,
        applicant_email=agent.applicant_email,
        status=agent.status,
        created_at=agent.created_at,
    )


@router.post("/agents/{agent_id}/approve", response_model=AgentApproveResponse)
def agents_approve(agent_id: str, req: ApproveRequest, db: Session = Depends(get_db)) -> AgentApproveResponse:
    """AIエージェントの登録承認(CaPassサーバ管理者のみ)。管理者の秘密鍵で署名したリクエストが必要。"""
    agent = approve_agent(db, agent_id, req)
    return AgentApproveResponse(
        agent_id=agent.agent_id,
        agent_public_key=agent.agent_public_key,
        applicant_email=agent.applicant_email,
        approver_email=agent.approver_email,
        status=agent.status,
        approved_at=agent.approved_at,
    )


# ---------- AIエージェントへのツール追加 ----------
@router.post("/agents/{agent_id}/addtool", status_code=201, response_model=AgentAddToolResponse)
def agents_addtool(agent_id: str, req: AgentAddToolRequest, db: Session = Depends(get_db)) -> AgentAddToolResponse:
    """AIエージェントにツール(ツール代理トークン)を追加する(旧 register。CaPassクライアントの「regist」から呼ばれる)。承認済みツールサーバの署名を検証する。"""
    agent_tool = add_tool_to_agent(db, agent_id, req)
    return AgentAddToolResponse(
        tool_endpoint=agent_tool.tool_endpoint,
        agent_id=agent_tool.agent_id,
        created_at=agent_tool.created_at,
    )


# ---------- AIエージェントによるツール実行 ----------
@router.get("/agents/{agent_id}/tools", response_model=AgentToolListResponse)
def agents_tools(
    agent_id: str,
    signed_at: Annotated[int, Header(alias=HEADER_SIGNED_AT, description="署名時刻(UNIX秒)")],
    signature: Annotated[str, Header(alias=HEADER_SIGNATURE, description="AIエージェントの署名(Base64)。署名対象は agent_id と signed_at")],
    db: Session = Depends(get_db),
) -> AgentToolListResponse:
    """AIエージェントが使用できる(ロックされていない)ツールの一覧を取得する(CaPassクライアントの「list executable」から呼ばれる)。
    各ツールの、エンドポイント・コンテキスト(説明)・paramsのスキーマ(JSON Schema)を返す。AIエージェントの署名が必要。
    使用できるツールが無い場合は、空のリストを返す。"""
    tools = list_executable_tools(db, agent_id, signed_at, signature)
    return AgentToolListResponse(
        agent_id=agent_id,
        tools=[AgentToolItem(tool_endpoint=t.tool_endpoint, context=t.context, params_schema=t.params_schema) for t in tools],
    )


@router.post("/agents/{agent_id}/exec/{tool_endpoint}")
def agents_exec(agent_id: str, tool_endpoint: str, req: AgentExecRequest, db: Session = Depends(get_db)) -> Response:
    """AIエージェントのツール実行を、ツールサーバへ中継する(CaPassクライアントの「exec」から呼ばれる)。AIエージェントの署名が必要。
    paramsは、ツールに登録されたスキーマで検証し、合わない場合は422(errorsに、問題の場所と内容)を返す。
    ツールサーバの2xx/4xxの応答は、そのまま中継する(401のみ403にする)。ツールサーバが5xxなどの場合は502、応答が無い場合は504。"""
    result = exec_agent_tool(db, agent_id, tool_endpoint, req)
    return Response(content=result.body, status_code=result.status_code, media_type=result.content_type)

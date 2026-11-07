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
from capass_server.common.config import TOKEN_MAX_AGE_SEC
from capass_server.common.db import get_db
from capass_server.common.globals import HEADER_SIGNATURE, HEADER_SIGNED_AT
from capass_server.controllers.dependencies import rate_limit_register
from capass_server.schemas.agent import (
    AgentApproveResponse,
    AgentExecRequest,
    AgentGrantApproveResponse,
    AgentGrantRequest,
    AgentGrantResponse,
    AgentRegisterRequest,
    AgentRegisterResponse,
    AgentRevokeRequest,
    AgentRevokeResponse,
    AgentToolItem,
    AgentToolListResponse,
)
from capass_server.schemas.approve import ApproveRequest
from capass_server.schemas.tool import ToolAddRequest, ToolAddResponse, ToolChangeTokenRequest, ToolChangeTokenResponse
from capass_server.schemas.tool_server import (
    ToolServerApproveResponse,
    ToolServerRegisterRequest,
    ToolServerRegisterResponse,
    ToolServerReplaceActivateRequest,
    ToolServerReplaceReserveRequest,
    ToolServerReplaceReserveResponse,
    ToolServerReplaceResponse,
    ToolServerReplaceRollbackRequest,
)
from capass_server.services.agent import approve_agent, register_agent
from capass_server.services.agent_tool import (
    approve_agent_tool_grant,
    exec_agent_tool,
    list_executable_tools,
    request_agent_tool_grant,
    revoke_agent_tool_grant,
)
from capass_server.services.tool import add_tool, change_tool_token
from capass_server.services.tool_server import (
    ReplacementResult,
    activate_tool_server_replacement,
    approve_tool_server,
    register_tool_server,
    reserve_tool_server_replacement,
    rollback_tool_server_replacement,
)

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


def _replace_response(result: ReplacementResult) -> ToolServerReplaceResponse:
    return ToolServerReplaceResponse(
        active_toolserver_id=result.active.id,
        active_tool_server_exec_url=result.active.exec_url,
        standby_toolserver_id=result.standby.id,
        standby_until=result.standby_until,
        moved_tools=result.moved_tools,
    )


# ---------- ツールサーバのリプレース(事前承認 → 切り替え → 切り戻し) ----------
@router.post("/toolservers/{toolserver_id}/replace/reserve", status_code=201, response_model=ToolServerReplaceReserveResponse)
def toolservers_replace_reserve(toolserver_id: int, req: ToolServerReplaceReserveRequest, db: Session = Depends(get_db)) -> ToolServerReplaceReserveResponse:
    """ツールサーバのリプレース(1/3: 予約)。CaPassサーバ管理者が、新ツールサーバ(実行URLと公開鍵)を、旧ツールサーバ({toolserver_id})の後継として、事前に承認する。
    管理者の署名が必要。予約には期限があり、期限内に、切り替え(activate)する。"""
    successor = reserve_tool_server_replacement(db, toolserver_id, req)
    return ToolServerReplaceReserveResponse(
        toolserver_id=successor.id,
        replaces_toolserver_id=toolserver_id,
        tool_server_name=successor.tool_server_name,
        tool_server_exec_url=successor.exec_url,
        tool_server_public_key=successor.tool_server_public_key,
        applicant_email=successor.applicant_email,
        approver_email=successor.approver_email,
        status=successor.status,
        reserved_until=successor.status_expires_at,
    )


@router.post("/toolservers/{toolserver_id}/replace/activate", response_model=ToolServerReplaceResponse)
def toolservers_replace_activate(toolserver_id: int, req: ToolServerReplaceActivateRequest, db: Session = Depends(get_db)) -> ToolServerReplaceResponse:
    """ツールサーバのリプレース(2/3: 切り替え)。予約済みの新ツールサーバへ、ツールを切り替える。旧ツールサーバ({toolserver_id})と新ツールサーバの、両方の署名が必要。
    旧ツールサーバは待機中(standby)になり、期限内なら、切り戻し(rollback)できる。管理者の操作は不要(事前に承認済みの送り先にだけ、切り替えられる)。"""
    return _replace_response(activate_tool_server_replacement(db, toolserver_id, req))


@router.post("/toolservers/{toolserver_id}/replace/rollback", response_model=ToolServerReplaceResponse)
def toolservers_replace_rollback(toolserver_id: int, req: ToolServerReplaceRollbackRequest, db: Session = Depends(get_db)) -> ToolServerReplaceResponse:
    """ツールサーバのリプレース(3/3: 切り戻し)。待機中(standby)の旧ツールサーバ({toolserver_id})へ、ツールを戻す。旧ツールサーバの署名だけでよい。
    新ツールサーバは待機中になり、期限内なら、再度、切り替え(activate)できる。"""
    return _replace_response(rollback_tool_server_replacement(db, toolserver_id, req))


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
# ---------- ツール(ロール単位のツールエンドポイント)の登録とトークンの更新 ----------
@router.post("/tools/addtool", status_code=201, response_model=ToolAddResponse)
def tools_addtool(req: ToolAddRequest, db: Session = Depends(get_db)) -> ToolAddResponse:
    """ツール(ロール単位のツールエンドポイント)の登録(CaPassクライアントの「regist」から呼ばれる)。承認済みツールサーバの署名が必要。
    登録しただけでは、どのAIエージェントも使えない。AIエージェントへの割り当ては、grant(申請)と、その承認で行う。"""
    tool = add_tool(db, req)
    return ToolAddResponse(tool_endpoint=tool.tool_endpoint, created_at=tool.created_at, token_max_age_sec=TOKEN_MAX_AGE_SEC)


@router.post("/tools/{tool_endpoint}/chtkn", response_model=ToolChangeTokenResponse)
def tools_chtkn(tool_endpoint: str, req: ToolChangeTokenRequest, db: Session = Depends(get_db)) -> ToolChangeTokenResponse:
    """ツール代理トークンの更新(CaPassクライアントの「chtkn」から呼ばれる。ツールサーバの定期更新ジョブ)。ツールを登録したツールサーバの署名が必要。
    トークンはロール単位なので、1回の更新が、そのツールを割り当てられた全てのAIエージェントに反映される。
    ツールサーバは、`token_max_age_sec` より短い間隔で、トークンを更新する。ロック中のツールは、更新しても、ロックされたまま。"""
    tool = change_tool_token(db, tool_endpoint, req)
    return ToolChangeTokenResponse(
        tool_endpoint=tool.tool_endpoint,
        tool_proxy_token_updated_at=tool.tool_proxy_token_updated_at,
        locked=tool.locked,
        token_max_age_sec=TOKEN_MAX_AGE_SEC,
    )


# ---------- AIエージェントへのツールの割り当て(申請 → 承認 / 取り消し) ----------
@router.post("/agents/{agent_id}/grant/{tool_endpoint}", status_code=201, response_model=AgentGrantResponse)
def agents_grant(agent_id: str, tool_endpoint: str, req: AgentGrantRequest, db: Session = Depends(get_db)) -> AgentGrantResponse:
    """AIエージェントへのツールの割り当ての申請(承認待ち:pendingになる)。AIエージェントの署名が必要。承認(approve)されると、使えるようになる。
    取り消された(revoked)割り当ては、再申請できる。"""
    grant = request_agent_tool_grant(db, agent_id, tool_endpoint, req)
    return AgentGrantResponse(
        agent_id=grant.agent_id,
        tool_endpoint=tool_endpoint,
        status=grant.status,
        applicant_email=grant.applicant_email,
        created_at=grant.created_at,
    )


@router.post("/agents/{agent_id}/grant/{tool_endpoint}/approve", response_model=AgentGrantApproveResponse)
def agents_grant_approve(agent_id: str, tool_endpoint: str, req: ApproveRequest, db: Session = Depends(get_db)) -> AgentGrantApproveResponse:
    """AIエージェントへのツールの割り当ての承認(いまは、CaPassサーバ管理者のみ。将来は、申請者の上司など)。管理者の署名が必要。"""
    grant = approve_agent_tool_grant(db, agent_id, tool_endpoint, req)
    return AgentGrantApproveResponse(
        agent_id=grant.agent_id,
        tool_endpoint=tool_endpoint,
        status=grant.status,
        applicant_email=grant.applicant_email,
        approver_email=grant.approver_email,
        approved_at=grant.approved_at,
    )


@router.post("/agents/{agent_id}/revoke/{tool_endpoint}", response_model=AgentRevokeResponse)
def agents_revoke(agent_id: str, tool_endpoint: str, req: AgentRevokeRequest, db: Session = Depends(get_db)) -> AgentRevokeResponse:
    """AIエージェントへのツールの割り当ての取り消し。CaPassサーバ管理者、または、そのツールを登録したツールサーバの署名が必要。"""
    grant = revoke_agent_tool_grant(db, agent_id, tool_endpoint, req)
    return AgentRevokeResponse(agent_id=grant.agent_id, tool_endpoint=tool_endpoint, status=grant.status)


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

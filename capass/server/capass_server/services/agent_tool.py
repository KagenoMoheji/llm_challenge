import os
import inspect
import sys
import time
import traceback
PYPATH = os.path.dirname(os.path.abspath(inspect.getfile(inspect.currentframe())))
MODNAME = os.path.splitext(os.path.basename(inspect.getfile(inspect.currentframe())))[0]

# その他のモジュールやROOTPATHのディレクトリ起点の相対パスでのimport
from datetime import datetime, timezone
from cryptography.fernet import InvalidToken
from jsonschema.exceptions import SchemaError
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session
from capass_server import __version__
from capass_server.common.config import TOOL_SERVER_MAX_RESPONSE_BYTES, TOOL_SERVER_TIMEOUT_SEC
from capass_server.common.crypto import decrypt_token
from capass_server.common.errors import (
    DuplicateAgentToolError,
    GrantNotFoundError,
    InvalidApprovalStateError,
    InvalidToolParamsError,
    NotAuthorizedError,
    PermissionDeniedError,
    ToolNotFoundError,
    ToolParamsSchemaError,
    ToolServerBadResponseError,
    ToolTokenDecryptionError,
)
from capass_server.common.params_schema import validate_params
from capass_server.common.signature import (
    SIGN_CONTEXT_AGENT_EXEC,
    SIGN_CONTEXT_AGENT_GRANT,
    SIGN_CONTEXT_AGENT_GRANT_APPROVE,
    SIGN_CONTEXT_AGENT_LISTTOOLS,
    SIGN_CONTEXT_AGENT_REVOKE,
)
from capass_server.common.tool_client import ToolServerResponse, call_tool_server
from capass_server.models import mappers
from capass_server.models.entities import ApprovalStatus, TblAgentTool, TblTool
from capass_server.schemas.agent import AgentExecRequest, AgentGrantRequest, AgentRevokeRequest
from capass_server.schemas.approve import ApproveRequest
from capass_server.services.signed_request import (
    consume_request_nonce,
    verify_admin_request,
    verify_agent_request,
    verify_signed_request,
)


# ---------- AIエージェントへのツールの割り当て(申請 → 承認 / 取り消し) ----------
def request_agent_tool_grant(db: Session, agent_id: str, tool_endpoint: str, req: AgentGrantRequest) -> TblAgentTool:
    """AIエージェントへの、ツールの割り当てを申請する(承認待ち:pendingになる)。AIエージェントの署名を検証する。
    取り消された(revoked)割り当ては、再申請できる。申請中・承認済みの場合は、DuplicateAgentToolError。"""
    verify_agent_request(db, agent_id, SIGN_CONTEXT_AGENT_GRANT, req.signed_payload(agent_id=agent_id, tool_endpoint=tool_endpoint), req.signature)

    tool = mappers.find_tbl_tool_by_endpoint(db, tool_endpoint)
    tool_server = None if tool is None else mappers.find_tbl_tool_server_by_id(db, tool.tool_server_id)
    if tool is None or tool_server is None or tool_server.status != ApprovalStatus.APPROVED:
        raise ToolNotFoundError()  # ツールサーバが承認されていない(取り消された)ツールは、存在しないものとして扱う

    now = datetime.now(timezone.utc)
    grant = mappers.find_tbl_agent_tool(db, agent_id, tool.id)
    if grant is not None:
        if grant.status != ApprovalStatus.REVOKED:
            raise DuplicateAgentToolError(grant.status)
        grant.status = ApprovalStatus.PENDING.value  # 取り消された割り当ての、再申請
        grant.applicant_email = req.applicant_email
        grant.approver_email = None
        grant.approved_at = None
        db.commit()
        return grant

    grant = TblAgentTool(
        agent_id=agent_id,
        tool_id=tool.id,
        status=ApprovalStatus.PENDING.value,
        applicant_email=req.applicant_email,
        approver_email=None,
        locked=False,
        tool_used_at=None,
        created_at=now,
        approved_at=None,
    )
    try:
        mappers.insert_tbl_agent_tool(db, grant)
        db.commit()
    except IntegrityError:
        db.rollback()
        raise DuplicateAgentToolError(ApprovalStatus.PENDING.value)
    return grant


def approve_agent_tool_grant(db: Session, agent_id: str, tool_endpoint: str, req: ApproveRequest) -> TblAgentTool:
    """AIエージェントへの、ツールの割り当ての申請を承認する(いまは、CaPassサーバ管理者のみ。将来は、申請者の上司など)。
    pending→approved。承認済みなら何もせず成功(冪等)。取り消された(revoked)割り当ては、承認できない(再申請が必要)。"""
    admin = verify_admin_request(
        db,
        req.admin_public_key,
        SIGN_CONTEXT_AGENT_GRANT_APPROVE,
        req.signed_payload(agent_id=agent_id, tool_endpoint=tool_endpoint),
        req.signature,
    )
    tool = mappers.find_tbl_tool_by_endpoint(db, tool_endpoint)
    if tool is None:
        raise ToolNotFoundError()
    grant = mappers.find_tbl_agent_tool(db, agent_id, tool.id)
    if grant is None:
        raise GrantNotFoundError()
    if grant.status == ApprovalStatus.APPROVED:
        return grant
    if grant.status != ApprovalStatus.PENDING:
        raise InvalidApprovalStateError(grant.status)

    grant.status = ApprovalStatus.APPROVED.value
    grant.approved_at = datetime.now(timezone.utc)
    grant.approver_email = admin.admin_email  # 承認した管理者のメアドを記録する
    db.commit()
    return grant


def revoke_agent_tool_grant(db: Session, agent_id: str, tool_endpoint: str, req: AgentRevokeRequest) -> TblAgentTool:
    """AIエージェントへの、ツールの割り当てを取り消す。CaPassサーバ管理者、または、そのツールを登録した(承認済みの)ツールサーバだけが、取り消せる。
    取り消し済みなら何もせず成功(冪等)。権限が無い相手には、対象の有無を知らせない(NotAuthorizedError)。"""
    verify_signed_request(req.signer_public_key, SIGN_CONTEXT_AGENT_REVOKE, req.signed_payload(agent_id=agent_id, tool_endpoint=tool_endpoint), req.signature)

    tool = mappers.find_tbl_tool_by_endpoint(db, tool_endpoint)
    admin = mappers.find_tbl_admin_by_public_key(db, req.signer_public_key)
    if admin is None or not admin.is_active:
        tool_server = mappers.find_tbl_tool_server_by_public_key(db, req.signer_public_key)
        is_owner = tool is not None and tool_server is not None and tool_server.status == ApprovalStatus.APPROVED and tool.tool_server_id == tool_server.id
        if not is_owner:
            raise NotAuthorizedError()
    if tool is None:
        raise ToolNotFoundError()
    grant = mappers.find_tbl_agent_tool(db, agent_id, tool.id)
    if grant is None:
        raise GrantNotFoundError()
    if grant.status != ApprovalStatus.REVOKED:
        grant.status = ApprovalStatus.REVOKED.value
        db.commit()
    return grant


# ---------- AIエージェントによるツールの一覧と実行 ----------
def list_executable_tools(db: Session, agent_id: str, signed_at: int, signature: str) -> list[TblTool]:
    """AIエージェントが使用できるツール(割り当てが承認済みで、ロックされておらず、ツールサーバが承認済み)の一覧を、ツールエンドポイント順に返す。
    AIエージェントの署名を検証する。使用できるツールが1件も無い場合は、空のリストを返す(エラーにしない)。"""
    verify_agent_request(db, agent_id, SIGN_CONTEXT_AGENT_LISTTOOLS, {"agent_id": agent_id, "signed_at": signed_at}, signature)
    return mappers.list_tbl_tool_executable(db, agent_id)


def exec_agent_tool(db: Session, agent_id: str, tool_endpoint: str, req: AgentExecRequest) -> ToolServerResponse:
    """AIエージェントのツール実行を、ツールサーバへ中継して、その結果を返す。

    1. AIエージェントの署名を検証する(URLパスのagent_id/tool_endpointも署名対象)。承認済みのAIエージェントのみ。
    2. nonceを使用済みとして記録する(リプレイ防止。ツール実行は副作用があるため)。
    3. 実行できるツール(割り当てが承認済み、ロックされておらず、ツールサーバが承認済み)を探す。無ければPermissionDeniedError。
    4. paramsを、ツールに登録されたスキーマ(params_schema)で検証する。合わなければInvalidToolParamsError(ツールサーバへは中継しない)。
    5. ツール代理トークンを復号して、ツールサーバの実行URLへ中継する。
    6. ツールサーバの応答: 2xxと4xxはそのまま中継する(ただし401は、AIエージェント自身の認証失敗と紛らわしいので403にする)。3xx/5xxは、中継せずに502にする。
    7. 2xxの場合は、このAIエージェントのツール利用日時を更新する。
    """
    payload = req.signed_payload(agent_id=agent_id, tool_endpoint=tool_endpoint)
    verify_agent_request(db, agent_id, SIGN_CONTEXT_AGENT_EXEC, payload, req.signature)
    consume_request_nonce(db, f"agent:{agent_id}", req.nonce, req.signed_at)

    found = mappers.find_tbl_tool_executable(db, agent_id, tool_endpoint)
    if found is None:
        raise PermissionDeniedError()
    grant, tool, tool_server = found

    try:
        param_errors = validate_params(tool.params_schema, req.params)
    except SchemaError:
        raise ToolParamsSchemaError()
    if param_errors:
        raise InvalidToolParamsError(param_errors)

    try:
        token = decrypt_token(tool.tool_proxy_token_encrypted)
    except InvalidToken:
        raise ToolTokenDecryptionError()
    exec_url = tool_server.exec_url

    # ツールサーバの応答を待つ間、DBのトランザクション(接続)を保持しない
    db.commit()

    result = call_tool_server(
        exec_url,
        token,
        {"agent_id": agent_id, "tool_endpoint": tool_endpoint, "params": req.params},
        TOOL_SERVER_TIMEOUT_SEC,
        TOOL_SERVER_MAX_RESPONSE_BYTES,
        user_agent=f"CaPass/{__version__}",
    )

    status = result.status_code
    if 200 <= status < 300:
        grant.tool_used_at = datetime.now(timezone.utc)
        db.commit()
        return result
    if status == 401:
        return ToolServerResponse(403, result.body, result.content_type)
    if 400 <= status < 500:
        return result
    raise ToolServerBadResponseError(f"status {status}")

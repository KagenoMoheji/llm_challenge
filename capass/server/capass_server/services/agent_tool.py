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
from capass_server.common.crypto import decrypt_token, encrypt_token
from capass_server.common.errors import (
    AgentNotApprovedError,
    AgentNotFoundError,
    DuplicateAgentToolError,
    InvalidToolParamsError,
    PermissionDeniedError,
    ToolParamsSchemaError,
    ToolServerBadResponseError,
    ToolServerNotApprovedError,
    ToolTokenDecryptionError,
)
from capass_server.common.params_schema import validate_params
from capass_server.common.signature import SIGN_CONTEXT_AGENT_ADDTOOL, SIGN_CONTEXT_AGENT_EXEC, SIGN_CONTEXT_AGENT_LISTTOOLS
from capass_server.common.tool_client import ToolServerResponse, call_tool_server
from capass_server.models import mappers
from capass_server.models.entities import ApprovalStatus, TblAgentTool
from capass_server.schemas.agent import AgentAddToolRequest, AgentExecRequest
from capass_server.services.signed_request import consume_request_nonce, verify_agent_request, verify_signed_request


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
        params_schema=req.params_schema,
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


def list_executable_tools(db: Session, agent_id: str, signed_at: int, signature: str) -> list[TblAgentTool]:
    """AIエージェントが使用できるツール(ロックされておらず、ツールサーバが承認済み)の一覧を、ツールエンドポイント順に返す。
    AIエージェントの署名を検証する。使用できるツールが1件も無い場合は、空のリストを返す(エラーにしない)。"""
    verify_agent_request(db, agent_id, SIGN_CONTEXT_AGENT_LISTTOOLS, {"agent_id": agent_id, "signed_at": signed_at}, signature)
    return mappers.list_tbl_agent_tool_executable(db, agent_id)


def exec_agent_tool(db: Session, agent_id: str, tool_endpoint: str, req: AgentExecRequest) -> ToolServerResponse:
    """AIエージェントのツール実行を、ツールサーバへ中継して、その結果を返す。

    1. AIエージェントの署名を検証する(URLパスのagent_id/tool_endpointも署名対象)。承認済みのAIエージェントのみ。
    2. nonceを使用済みとして記録する(リプレイ防止。ツール実行は副作用があるため)。
    3. 実行できるツール(ロックされておらず、ツールサーバが承認済み)を探す。無ければPermissionDeniedError。
    4. paramsを、ツールに登録されたスキーマ(params_schema)で検証する。合わなければInvalidToolParamsError(ツールサーバへは中継しない)。
    5. ツール代理トークンを復号して、ツールサーバの実行URLへ中継する。
    6. ツールサーバの応答: 2xxと4xxはそのまま中継する(ただし401は、AIエージェント自身の認証失敗と紛らわしいので403にする)。3xx/5xxは、中継せずに502にする。
    7. 2xxの場合は、ツール利用日時を更新する。
    """
    payload = req.signed_payload(agent_id=agent_id, tool_endpoint=tool_endpoint)
    verify_agent_request(db, agent_id, SIGN_CONTEXT_AGENT_EXEC, payload, req.signature)
    consume_request_nonce(db, agent_id, req.nonce, req.signed_at)

    found = mappers.find_tbl_agent_tool_executable(db, agent_id, tool_endpoint)
    if found is None:
        raise PermissionDeniedError()
    agent_tool, tool_server = found

    try:
        param_errors = validate_params(agent_tool.params_schema, req.params)
    except SchemaError:
        raise ToolParamsSchemaError()
    if param_errors:
        raise InvalidToolParamsError(param_errors)

    try:
        token = decrypt_token(agent_tool.tool_proxy_token_encrypted)
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
        agent_tool.tool_used_at = datetime.now(timezone.utc)
        db.commit()
        return result
    if status == 401:
        return ToolServerResponse(403, result.body, result.content_type)
    if 400 <= status < 500:
        return result
    raise ToolServerBadResponseError(f"status {status}")

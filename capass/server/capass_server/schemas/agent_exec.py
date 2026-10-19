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
from sqlalchemy.orm import Session
from capass_server import __version__
from capass_server.common.config import SIGNATURE_MAX_SKEW_SEC, TOOL_SERVER_MAX_RESPONSE_BYTES, TOOL_SERVER_TIMEOUT_SEC
from capass_server.common.crypto import decrypt_token
from capass_server.common.errors import PermissionDeniedError, ToolServerBadResponseError, ToolTokenDecryptionError
from capass_server.common.signature import SIGN_CONTEXT_AGENT_EXEC, SIGN_CONTEXT_AGENT_LISTTOOLS
from capass_server.common.tool_client import ToolServerResponse, call_tool_server
from capass_server.models import mappers
from capass_server.models.entities import TblAgentTool
from capass_server.schemas.agent import AgentExecRequest
from capass_server.services.signed_request import consume_request_nonce, verify_agent_request


def list_executable_tools(db: Session, agent_id: str, signed_at: int, signature: str) -> list[TblAgentTool]:
    """AIエージェントが使用できるツール(ロックされておらず、ツールサーバが承認済み)の一覧を返す。AIエージェントの署名を検証する。
    使用できるツールが1件も無ければ、PermissionDeniedError(シーケンス図の「権限ありませんエラー」)。"""
    verify_agent_request(db, agent_id, SIGN_CONTEXT_AGENT_LISTTOOLS, {"agent_id": agent_id, "signed_at": signed_at}, signature)
    tools = mappers.list_tbl_agent_tool_executable(db, agent_id)
    if not tools:
        raise PermissionDeniedError()
    return tools


def exec_agent_tool(db: Session, agent_id: str, tool_endpoint: str, req: AgentExecRequest) -> ToolServerResponse:
    """AIエージェントのツール実行を、ツールサーバへ中継して、その結果を返す。

    1. AIエージェントの署名を検証する(URLパスのagent_id/tool_endpointも署名対象)。承認済みのAIエージェントのみ。
    2. nonceを使用済みとして記録する(リプレイ防止。ツール実行は副作用があるため)。
    3. 実行できるツール(ロックされておらず、ツールサーバが承認済み)を探す。無ければPermissionDeniedError。
    4. ツール代理トークンを復号して、ツールサーバの実行URLへ中継する。
    5. ツールサーバの応答: 2xxと4xxはそのまま中継する(ただし401は、AIエージェント自身の認証失敗と紛らわしいので403にする)。3xx/5xxは、中継せずに502にする。
    6. 2xxの場合は、ツール利用日時を更新する。
    """
    payload = req.signed_payload(agent_id=agent_id, tool_endpoint=tool_endpoint)
    verify_agent_request(db, agent_id, SIGN_CONTEXT_AGENT_EXEC, payload, req.signature)
    consume_request_nonce(db, agent_id, req.nonce, req.signed_at)

    found = mappers.find_tbl_agent_tool_executable(db, agent_id, tool_endpoint)
    if found is None:
        raise PermissionDeniedError()
    agent_tool, tool_server = found
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

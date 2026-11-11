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
from capass_server.common.errors import DuplicateToolError, ToolNotFoundError, ToolServerNotApprovedError
from capass_server.common.signature import SIGN_CONTEXT_TOOL_ADDTOOL, SIGN_CONTEXT_TOOL_CHTKN
from capass_server.models import mappers
from capass_server.models.entities import ApprovalStatus, TblTool
from capass_server.schemas.tool import ToolAddRequest, ToolChangeTokenRequest
from capass_server.services.signed_request import consume_request_nonce, verify_signed_request


def add_tool(db: Session, req: ToolAddRequest) -> TblTool:
    """ツール(ロール単位のツールエンドポイント)を登録する。承認済みツールサーバの署名を検証する。
    AIエージェントへの割り当ては、別の操作(agent_tool.request_agent_tool_grant)。"""
    # 1. 署名の検証(DB参照より先に行い、未認証のリクエストに登録有無を知らせない)
    verify_signed_request(req.tool_server_public_key, SIGN_CONTEXT_TOOL_ADDTOOL, req.signed_payload(), req.signature)

    # 2. ツールサーバ公開鍵の承認確認(署名検証済みなので、鍵の持ち主であることは確認できている。次に、管理者が承認した鍵かを確認する)
    tool_server = mappers.find_tbl_tool_server_by_public_key(db, req.tool_server_public_key)
    if tool_server is None or tool_server.status != ApprovalStatus.APPROVED:
        raise ToolServerNotApprovedError(None if tool_server is None else tool_server.status)

    # 3. 重複チェック(ツールエンドポイントは、全体で一意。更新は、トークンの更新(chtkn)で行う)
    if mappers.find_tbl_tool_by_endpoint(db, req.tool_endpoint) is not None:
        raise DuplicateToolError()

    # 4. 登録(同時リクエストによる重複は、一意制約違反として検出する)
    now = datetime.now(timezone.utc)
    tool = TblTool(
        tool_endpoint=req.tool_endpoint,
        context=req.context,
        params_schema=req.params_schema,
        tool_server_id=tool_server.id,
        tool_proxy_token_encrypted=encrypt_token(req.tool_proxy_token),
        tool_proxy_token_updated_at=now,
        locked=False,
        created_at=now,
    )
    try:
        mappers.insert_tbl_tool(db, tool)
        db.commit()
    except IntegrityError:
        db.rollback()
        raise DuplicateToolError()
    return tool


def change_tool_token(db: Session, tool_endpoint: str, req: ToolChangeTokenRequest) -> TblTool:
    """ツール代理トークンを、新しいトークンに更新する(ツールサーバの定期更新ジョブ「chtkn」から呼ばれる)。
    トークンは、ロール単位(ツール単位)なので、そのツールを割り当てられた全てのAIエージェントに反映される。

    1. ツールサーバの署名を検証する(URLパスのtool_endpointも署名対象)。
    2. ツールサーバの公開鍵が承認済みかを確認する。承認されていない(取り消された)ツールサーバは、更新できない。
       この確認を、ツールの検索より先にして、承認されていない鍵の持ち主に、ツールの有無を知らせない。
    3. nonceを使用済みとして記録する(リプレイ防止。古いトークンへの巻き戻しを防ぐ)。
    4. ツールを探す。無い、または別のツールサーバのツールなら、ToolNotFoundError(どちらも「無い」と同じ扱い)。
    5. トークン(暗号化して保存)とトークン更新日時を更新する。ロック状況は変えない(ロックの解除は、別の操作)。
    """
    payload = req.signed_payload(tool_endpoint=tool_endpoint)
    verify_signed_request(req.tool_server_public_key, SIGN_CONTEXT_TOOL_CHTKN, payload, req.signature)

    tool_server = mappers.find_tbl_tool_server_by_public_key(db, req.tool_server_public_key)
    if tool_server is None or tool_server.status != ApprovalStatus.APPROVED:
        raise ToolServerNotApprovedError(None if tool_server is None else tool_server.status)

    consume_request_nonce(db, f"tool:{tool_endpoint}", req.nonce, req.signed_at)

    tool = mappers.find_tbl_tool_by_endpoint(db, tool_endpoint)
    if tool is None or tool.tool_server_id != tool_server.id:
        raise ToolNotFoundError()

    tool.tool_proxy_token_encrypted = encrypt_token(req.tool_proxy_token)
    tool.tool_proxy_token_updated_at = datetime.now(timezone.utc)
    db.commit()
    return tool

import os
import inspect
import sys
import time
import traceback
PYPATH = os.path.dirname(os.path.abspath(inspect.getfile(inspect.currentframe())))
MODNAME = os.path.splitext(os.path.basename(inspect.getfile(inspect.currentframe())))[0]

# その他のモジュールやROOTPATHのディレクトリ起点の相対パスでのimport
from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session
from capass_server.common.db import get_db
from capass_server.schemas.register import RegisterRequest, RegisterResponse
from capass_server.common.errors import DuplicateRegistrationError, SignatureError, ToolServerNotApprovedError
from capass_server.services.tool_registration import register_tool

router = APIRouter()


@router.post("/register", status_code=201, response_model=RegisterResponse)
def register(req: RegisterRequest, db: Session = Depends(get_db)) -> RegisterResponse:
    """ツール/AIエージェント/ツールサーバ公開鍵の登録(CaPassクライアントの「regist」から呼ばれる)。初回を含め、登録の都度ツールサーバの署名を検証する。"""
    try:
        agent_tool = register_tool(db, req)
    except SignatureError as e:
        raise HTTPException(status_code=401, detail=str(e), headers={"WWW-Authenticate": "CaPass-Signature"})
    except ToolServerNotApprovedError as e:
        raise HTTPException(status_code=403, detail=str(e))
    except DuplicateRegistrationError as e:
        raise HTTPException(status_code=409, detail=str(e))
    return RegisterResponse(
        tool_endpoint=agent_tool.tool_endpoint,
        agent_id=agent_tool.agent_id,
        created_at=agent_tool.created_at,
    )


@router.get("/agents/{agent_id}/tools")
def list_agent_tools(agent_id: str) -> None:
    """AIエージェントが使用可能な(ロックされていない)ツール一覧の取得(CaPassクライアントの「list executable」から呼ばれる)。"""
    # TODO: レスポンス: 「ツールエンドポイント/コンテキスト」一覧(0件の場合は権限ありませんエラー)
    raise HTTPException(status_code=501, detail="Not Implemented")


@router.post("/agents/{agent_id}/exec")
def exec_agent_tool(agent_id: str) -> None:
    """AIエージェントによるツール実行(CaPassクライアントの「exec」から呼ばれる)。"""
    # TODO: リクエスト: ツールエンドポイント/ツールパラメータ
    # TODO: レスポンス: ツールの正常終了結果 または 権限ありませんエラー(ツールサーバからの結果を中継)
    raise HTTPException(status_code=501, detail="Not Implemented")

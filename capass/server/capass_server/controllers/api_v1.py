import os
import inspect
import sys
import time
import traceback
PYPATH = os.path.dirname(os.path.abspath(inspect.getfile(inspect.currentframe())))
MODNAME = os.path.splitext(os.path.basename(inspect.getfile(inspect.currentframe())))[0]

# その他のモジュールやROOTPATHのディレクトリ起点の相対パスでのimport
from fastapi import APIRouter, Depends, HTTPException

router = APIRouter()


@router.get("/hello")
def hello() -> dict[str, str]:
    return {"message": "hello, world! (api v1)"}


@router.post("/register")
def register() -> None:
    """ツール/AIエージェント/ツールサーバ公開鍵の登録(CaPassクライアントの「regist」から呼ばれる)。"""
    # TODO: リクエスト: ツール情報(ツールエンドポイント/コンテキスト)/ツール代理トークン/AIエージェント情報/ツールサーバ公開鍵
    # TODO: レスポンス: 登録完了
    raise HTTPException(status_code=501, detail="Not Implemented")


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

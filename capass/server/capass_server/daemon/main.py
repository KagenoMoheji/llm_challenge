import os
import inspect
import sys
import time
import traceback
PYPATH = os.path.dirname(os.path.abspath(inspect.getfile(inspect.currentframe())))
ROOTPATH = os.path.abspath(f"{PYPATH}/..")
MODNAME = os.path.splitext(os.path.basename(inspect.getfile(inspect.currentframe())))[0]
# 以下のROOTPATHでimportの起点を指定
sys.path.append(ROOTPATH)

# その他のモジュールやROOTPATHのディレクトリ起点の相対パスでのimport
import logging
from fastapi import FastAPI
from contextlib import asynccontextmanager
import uvicorn
from capass_server import __version__
from capass_server.common.config import ENV_TYPE, DB_RETRY_COUNT, DB_RETRY_DELAY_SEC, TOOL_SERVER_ALLOW_HTTP
from capass_server.common.db import Base, engine, get_db, wait_for_db
from capass_server.models import entities  # noqa: F401  (create_all の対象にするため、テーブル定義をBase.metadataへ登録する)
from capass_server.controllers.error_handlers import register_error_handlers
from capass_server.routes import register_routes



logger = logging.getLogger(__name__)


@asynccontextmanager
async def lifespan(_: FastAPI):
    # 以下、FastAPI起動時に一回のみ実行する処理
    if TOOL_SERVER_ALLOW_HTTP:
        # http のツールサーバへは、ツール代理トークンやparamsが、暗号化されずに流れる。下の層(IPsec、サービスメッシュ、VPNなど)が、CaPassとツールサーバの間を暗号化していることを、確認して使うこと
        logger.warning("CAPASS_SERVER_TOOL_SERVER_ALLOW_HTTP=true: http の実行URLを許可しています。CaPassサーバとツールサーバの間の通信が、暗号化されていることを確認してください")
    wait_for_db(engine, DB_RETRY_COUNT, DB_RETRY_DELAY_SEC)  # DBへ接続できるまでリトライ
    if ENV_TYPE in ("LOCAL_DEV", "DEV"):
        Base.metadata.create_all(engine)
    yield
    # 以下、FastAPI終了時に一回のみ実行する処理

# FastAPI初期化
app = FastAPI(title="CaPass Server", version=__version__, lifespan=lifespan)
register_routes(app)
register_error_handlers(app)


def run() -> None:
    uvicorn.run("capass_server.main:app", host="127.0.0.1", port=8000)


if __name__ == "__main__":
    run()
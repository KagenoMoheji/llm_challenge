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
from fastapi import FastAPI
from contextlib import asynccontextmanager
import uvicorn
from capass_server import __version__
from capass_server.common.config import ENV_TYPE, DB_RETRY_COUNT, DB_RETRY_DELAY_SEC
from capass_server.common.db import Base, engine, get_db, wait_for_db
from capass_server.routes import register_routes



@asynccontextmanager
async def lifespan(_: FastAPI):
    # 以下、FastAPI起動時に一回のみ実行する処理
    wait_for_db(engine, DB_RETRY_COUNT, DB_RETRY_DELAY_SEC)  # DBへ接続できるまでリトライ
    if ENV_TYPE in ("LOCAL_DEV", "DEV"):
        Base.metadata.create_all(engine)
    yield
    # 以下、FastAPI終了時に一回のみ実行する処理

# FastAPI初期化
app = FastAPI(title="CaPass Server", version=__version__, lifespan=lifespan)
register_routes(app)


def run() -> None:
    uvicorn.run("capass_server.main:app", host="127.0.0.1", port=8000)


if __name__ == "__main__":
    run()
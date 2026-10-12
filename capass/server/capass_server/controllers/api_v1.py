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
    # TODO: tools / agents / tokens 等のエンドポイントは将来ここに追加
    return {"message": "hello, world! (api v1)"}
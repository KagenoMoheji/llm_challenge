import os
import inspect
import sys
import time
import traceback
PYPATH = os.path.dirname(os.path.abspath(inspect.getfile(inspect.currentframe())))
MODNAME = os.path.splitext(os.path.basename(inspect.getfile(inspect.currentframe())))[0]

# その他のモジュールやROOTPATHのディレクトリ起点の相対パスでのimport
from fastapi import FastAPI
from capass_server.controllers import api_v1, root


def register_routes(app: FastAPI) -> None:
    app.include_router(root.router)
    app.include_router(api_v1.router, prefix="/api/v1")
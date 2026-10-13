import os
import inspect
import sys
import time
import traceback
PYPATH = os.path.dirname(os.path.abspath(inspect.getfile(inspect.currentframe())))
# 以下のROOTPATHでimportの起点を指定
ROOTPATH = os.path.abspath(f"{PYPATH}/..")
MODNAME = os.path.splitext(os.path.basename(inspect.getfile(inspect.currentframe())))[0]
sys.path.append(ROOTPATH)

# その他のモジュールやROOTPATHのディレクトリ起点の相対パスでのimport
from fastapi.testclient import TestClient
from capass_server.main import app

client = TestClient(app)


def test_root_hello():
    res = client.get("/hello")
    assert res.status_code == 200
    assert res.json() == {"message": "hello, world!"}

import os
import inspect
import sys
import time
import traceback
PYPATH = os.path.dirname(os.path.abspath(inspect.getfile(inspect.currentframe())))
MODNAME = os.path.splitext(os.path.basename(inspect.getfile(inspect.currentframe())))[0]

# その他のモジュールやROOTPATHのディレクトリ起点の相対パスでのimport
"""CaPassサーバの、CLI(capass init ...)。まだ実装していない(docs/TODO.md の 2.1)。
register(subparsers, context) を定義すると、capass コマンドに、登録される(capass_core.cli.main)。"""

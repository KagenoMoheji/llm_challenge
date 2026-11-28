import os
import inspect
import sys
import time
import traceback
PYPATH = os.path.dirname(os.path.abspath(inspect.getfile(inspect.currentframe())))
MODNAME = os.path.splitext(os.path.basename(inspect.getfile(inspect.currentframe())))[0]

# その他のモジュールやROOTPATHのディレクトリ起点の相対パスでのimport
from capass_toolserver.cli.commands import init


def register(subparsers, context) -> None:
    """`capass` コマンドに、ツールサーバのコマンドを登録する(capass_core.cli.main が、モードを検出して、呼ぶ)。いまは init のみ。"""
    init.register(subparsers)

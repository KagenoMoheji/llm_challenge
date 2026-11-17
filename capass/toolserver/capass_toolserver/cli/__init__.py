import os
import inspect
import sys
import time
import traceback
PYPATH = os.path.dirname(os.path.abspath(inspect.getfile(inspect.currentframe())))
MODNAME = os.path.splitext(os.path.basename(inspect.getfile(inspect.currentframe())))[0]

# その他のモジュールやROOTPATHのディレクトリ起点の相対パスでのimport
from capass_core.cli.init import register_init
from capass_core.init_steps import InitSpec
from capass_core.modes import MODE_TOOLSERVER

# ツールサーバの、初期導入の設定。サービスは、受け口(capass serve。未実装)を、常駐させる
INIT_SPEC = InitSpec(
    mode=MODE_TOOLSERVER,
    unit_description="CaPass tool server receiver",
    exec_args="serve",
    daemon_label="受け口",
)


def register(subparsers, context) -> None:
    """`capass` コマンドに、ツールサーバのコマンドを登録する(capass_core.cli.main が、モードを検出して、呼ぶ)。いまは init のみ。"""
    register_init(subparsers, INIT_SPEC)

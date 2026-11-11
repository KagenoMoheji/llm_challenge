import os
import inspect
import sys
import time
import traceback
PYPATH = os.path.dirname(os.path.abspath(inspect.getfile(inspect.currentframe())))
MODNAME = os.path.splitext(os.path.basename(inspect.getfile(inspect.currentframe())))[0]

# その他のモジュールやROOTPATHのディレクトリ起点の相対パスでのimport


class CapassCliError(Exception):
    """CLIの業務エラーの基底クラス。メッセージを表示して、exit_codeで終了する(main.py)。"""

    exit_code = 1


class RoleConflictError(CapassCliError):
    """このサーバに、すでに別の役割(AIエージェント / ツールサーバ / CaPassサーバ)が設定されている。"""

    exit_code = 3


class KeyAlreadyExistsError(CapassCliError):
    """鍵ファイルが、すでに存在する(--force なしでは、上書きしない)。"""

    exit_code = 4


class HomeDirectoryError(CapassCliError):
    """CaPassクライアントのホームディレクトリ(CAPASS_HOME)を、作成・使用できない。"""

    exit_code = 5

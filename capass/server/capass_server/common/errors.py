import os
import inspect
import sys
import time
import traceback
PYPATH = os.path.dirname(os.path.abspath(inspect.getfile(inspect.currentframe())))
MODNAME = os.path.splitext(os.path.basename(inspect.getfile(inspect.currentframe())))[0]

# その他のモジュールやROOTPATHのディレクトリ起点の相対パスでのimport


class ServiceError(Exception):
    """service層の業務エラーの基底クラス。controllerでHTTPステータスに変換する。"""


class SignatureError(ServiceError):
    """署名検証に関するエラー(401相当)。"""


class SignatureExpiredError(SignatureError):
    def __init__(self) -> None:
        super().__init__("signed_at is out of the allowed time range")


class InvalidSignatureError(SignatureError):
    def __init__(self) -> None:
        super().__init__("invalid signature")


class DuplicateRegistrationError(ServiceError):
    """同一の[ツールエンドポイント/AIエージェント]が登録済み(409相当)。"""

    def __init__(self) -> None:
        super().__init__("tool is already registered for the agent")

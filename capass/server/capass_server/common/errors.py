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


class ToolServerNotApprovedError(ServiceError):
    """ツールサーバの公開鍵が、CaPassサーバ管理者に承認されていない(403相当)。署名検証済みの相手にのみ返すので、状態を伝える。"""

    def __init__(self, status: str | None) -> None:
        if status is None:
            super().__init__("tool server public key is not registered")
        else:
            super().__init__(f"tool server is not approved (status: {status})")

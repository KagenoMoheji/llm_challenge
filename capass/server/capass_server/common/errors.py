import os
import inspect
import sys
import time
import traceback
PYPATH = os.path.dirname(os.path.abspath(inspect.getfile(inspect.currentframe())))
MODNAME = os.path.splitext(os.path.basename(inspect.getfile(inspect.currentframe())))[0]

# その他のモジュールやROOTPATHのディレクトリ起点の相対パスでのimport


class ServiceError(Exception):
    """service層の業務エラーの基底クラス。HTTPステータスへの変換は、controllers/error_handlers.pyで一括して行う。"""


class SignatureError(ServiceError):
    """署名検証に関するエラー(401相当)。"""


class SignatureExpiredError(SignatureError):
    def __init__(self) -> None:
        super().__init__("signed_at is out of the allowed time range")


class InvalidSignatureError(SignatureError):
    def __init__(self) -> None:
        super().__init__("invalid signature")


class NotAdminError(ServiceError):
    """署名は正当だが、署名した公開鍵がCaPassサーバ管理者のものではない(403相当)。"""

    def __init__(self) -> None:
        super().__init__("admin_public_key is not an authorized administrator")


class ToolServerNotApprovedError(ServiceError):
    """ツールサーバの公開鍵が、CaPassサーバ管理者に承認されていない(403相当)。署名検証済みの相手にのみ返すので、状態を伝える。"""

    def __init__(self, status: str | None) -> None:
        if status is None:
            super().__init__("tool server public key is not registered")
        else:
            super().__init__(f"tool server is not approved (status: {status})")


class AgentNotApprovedError(ServiceError):
    """AIエージェントが、CaPassサーバ管理者に承認されていない(403相当)。"""

    def __init__(self, status: str) -> None:
        super().__init__(f"agent is not approved (status: {status})")


class ToolServerNotFoundError(ServiceError):
    """指定のツールサーバが存在しない(404相当)。"""

    def __init__(self) -> None:
        super().__init__("tool server not found")


class AgentNotFoundError(ServiceError):
    """指定のAIエージェントが存在しない(404相当)。"""

    def __init__(self) -> None:
        super().__init__("agent not found")


class DuplicateToolServerError(ServiceError):
    """同一の公開鍵のツールサーバが登録済み(409相当)。"""

    def __init__(self, status: str | None = None) -> None:
        if status is None:
            super().__init__("tool server public key is already registered")
        else:
            super().__init__(f"tool server public key is already registered (status: {status})")


class DuplicateAgentError(ServiceError):
    """同一のagent_idまたは公開鍵のAIエージェントが登録済み(409相当)。"""

    def __init__(self) -> None:
        super().__init__("agent_id or agent public key is already registered")


class DuplicateAgentToolError(ServiceError):
    """同一の[ツールエンドポイント/AIエージェント]が登録済み(409相当)。"""

    def __init__(self) -> None:
        super().__init__("tool is already registered for the agent")


class InvalidApprovalStateError(ServiceError):
    """現在の承認ステータスからは承認できない(409相当)。"""

    def __init__(self, status: str) -> None:
        super().__init__(f"cannot approve in the current status (status: {status})")


class RateLimitExceededError(ServiceError):
    """リクエストが多すぎる(429相当)。retry_after_secは、再試行までの待ち時間(秒)。"""

    def __init__(self, retry_after_sec: int) -> None:
        super().__init__("too many requests")
        self.retry_after_sec = retry_after_sec

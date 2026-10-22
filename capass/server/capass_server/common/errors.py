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


class PermissionDeniedError(ServiceError):
    """実行できるツールが無い(エンドポイントが未登録/ロック中/ツールサーバが未承認を区別せず、まとめて返す)(403相当)。ツール実行(exec)で使う。"""

    def __init__(self) -> None:
        super().__init__("permission denied")


class ReplayedRequestError(SignatureError):
    """同じnonceのリクエストを、すでに受け付けている(リプレイ)(401相当)。"""

    def __init__(self) -> None:
        super().__init__("nonce has already been used")


class InvalidToolServerUrlError(ServiceError):
    """ツールサーバの実行URLが、許可されていない形式(422相当)。"""

    def __init__(self) -> None:
        super().__init__("tool_server_exec_url must be an https URL")


class ToolServerUnavailableError(ServiceError):
    """ツールサーバに接続できない(502相当)。"""

    def __init__(self) -> None:
        super().__init__("tool server is unavailable")


class ToolServerTimeoutError(ServiceError):
    """ツールサーバの応答がタイムアウトした(504相当)。"""

    def __init__(self) -> None:
        super().__init__("tool server timed out")


class ToolServerBadResponseError(ServiceError):
    """ツールサーバの応答を中継できない(5xx/3xxの応答、サイズ超過など)(502相当)。"""

    def __init__(self, reason: str) -> None:
        super().__init__(f"tool server returned an unusable response ({reason})")


class ToolTokenDecryptionError(ServiceError):
    """保存されたツール代理トークンを復号できない(暗号化鍵の設定ミスなど。500相当)。"""

    def __init__(self) -> None:
        super().__init__("tool proxy token cannot be decrypted")


class InvalidToolParamsError(ServiceError):
    """ツールパラメータ(params)が、ツールに登録されたスキーマに合っていない(422相当)。
    errorsには、AIエージェントが修正できるよう、問題の場所と内容を入れる。"""

    def __init__(self, errors: list[str]) -> None:
        super().__init__("params does not match the params_schema of the tool")
        self.errors = errors


class ToolParamsSchemaError(ServiceError):
    """保存されたparamsのスキーマが不正で、検証できない(500相当。登録時に検証しているので、通常は起きない)。"""

    def __init__(self) -> None:
        super().__init__("stored params_schema is invalid")


class InvalidNewKeySignatureError(SignatureError):
    """新しい公開鍵の署名が不正(401相当)。旧公開鍵の署名の検証後(鍵の持ち主と確認できた相手)にだけ返すので、どちらの署名が不正かを伝える。"""

    def __init__(self) -> None:
        super().__init__("invalid signature of the new public key")


class ToolNotFoundError(ServiceError):
    """指定の[ツールエンドポイント/AIエージェント]のツールが、そのツールサーバ(公開鍵)で登録されていない(404相当)。
    他のツールサーバのツールの有無を知らせないよう、「存在しない」と「別のツールサーバのツール」は区別しない。"""

    def __init__(self) -> None:
        super().__init__("tool not found")

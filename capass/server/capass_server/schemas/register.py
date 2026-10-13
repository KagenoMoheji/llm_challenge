import os
import inspect
import sys
import time
import traceback
PYPATH = os.path.dirname(os.path.abspath(inspect.getfile(inspect.currentframe())))
MODNAME = os.path.splitext(os.path.basename(inspect.getfile(inspect.currentframe())))[0]

# その他のモジュールやROOTPATHのディレクトリ起点の相対パスでのimport
from datetime import datetime
from pydantic import BaseModel, ConfigDict, Field, StrictInt, field_validator
from capass_server.common.signature import decode_ed25519_public_key, decode_ed25519_signature

_SIGNATURE_DESC = (
    "署名(Base64)。Ed25519で、メッセージ = b'capass-register-v1\\n' + 正規化JSON に対して署名する。"
    "正規化JSONは、signature以外の全フィールドを sort_keys=True / separators=(',', ':') / ensure_ascii=False でJSON化し、UTF-8でエンコードしたもの。"
)


class RegisterRequest(BaseModel):
    """ツール/AIエージェント/ツールサーバ公開鍵の登録リクエスト。全フィールド必須(署名対象を一意にするため)。"""

    model_config = ConfigDict(extra="forbid")

    tool_endpoint: str = Field(min_length=1, max_length=512, description="ツールエンドポイント")
    context: str = Field(min_length=1, description="ツールのコンテキスト(説明)")
    tool_proxy_token: str = Field(min_length=1, max_length=1024, description="ツール代理トークン")
    agent_id: str = Field(min_length=1, max_length=128, description="AIエージェント情報(ID)")
    tool_server_public_key: str = Field(description="ツールサーバ公開鍵(Base64。Ed25519の生32バイト)")
    signed_at: StrictInt = Field(description="署名時刻(UNIX秒)。サーバ時刻との差が許容範囲を超えると拒否される")
    signature: str = Field(description=_SIGNATURE_DESC)

    @field_validator("tool_server_public_key")
    @classmethod
    def _validate_public_key(cls, v: str) -> str:
        try:
            decode_ed25519_public_key(v)
        except ValueError:
            raise ValueError("must be Base64 of a 32-byte Ed25519 public key")
        return v

    @field_validator("signature")
    @classmethod
    def _validate_signature_format(cls, v: str) -> str:
        try:
            decode_ed25519_signature(v)
        except ValueError:
            raise ValueError("must be Base64 of a 64-byte Ed25519 signature")
        return v

    def signed_payload(self) -> dict:
        """署名対象のペイロード(signature以外の全フィールド)。"""
        return self.model_dump(exclude={"signature"})


class RegisterResponse(BaseModel):
    tool_endpoint: str
    agent_id: str
    created_at: datetime

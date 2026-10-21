import os
import inspect
import sys
import time
import traceback
PYPATH = os.path.dirname(os.path.abspath(inspect.getfile(inspect.currentframe())))
MODNAME = os.path.splitext(os.path.basename(inspect.getfile(inspect.currentframe())))[0]

# その他のモジュールやROOTPATHのディレクトリ起点の相対パスでのimport
from datetime import datetime
from typing import ClassVar
from pydantic import BaseModel, Field, field_validator
from capass_server.common.globals import EMAIL_MAX_LEN, EMAIL_PATTERN, EXEC_URL_MAX_LEN, EXEC_URL_PATTERN, TOOL_SERVER_NAME_MAX_LEN
from capass_server.common.signature import decode_ed25519_signature
from capass_server.schemas.base import SignedRequest, validate_public_key_format


class ToolServerRegisterRequest(SignedRequest):
    """ツールサーバ(公開鍵)の初回登録リクエスト。ツールサーバ自身の秘密鍵で署名する(鍵の所持証明)。

    署名プレフィックス: SIGN_CONTEXT_TOOLSERVER_REGISTER
    署名対象: tool_server_public_key, tool_server_name, tool_server_exec_url, applicant_email, signed_at
    """

    tool_server_public_key: str = Field(description="ツールサーバ公開鍵(Base64。Ed25519の生32バイト)")
    tool_server_name: str = Field(min_length=1, max_length=TOOL_SERVER_NAME_MAX_LEN, description="ツールサーバの名称(管理者が承認時に識別するため)")
    tool_server_exec_url: str = Field(
        max_length=EXEC_URL_MAX_LEN,
        pattern=EXEC_URL_PATTERN,
        description="ツール実行の依頼先URL。CaPassサーバが、AIエージェントのツール実行を、ここへ中継する(既定ではhttpsのみ)。管理者が承認時に確認する",
    )
    applicant_email: str = Field(max_length=EMAIL_MAX_LEN, pattern=EMAIL_PATTERN, description="申請者のメールアドレス(管理者が承認前に、申請内容の確認の連絡をするため)")

    @field_validator("tool_server_public_key")
    @classmethod
    def _validate_tool_server_public_key(cls, v: str) -> str:
        return validate_public_key_format(v)


class ToolServerRegisterResponse(BaseModel):
    toolserver_id: int
    tool_server_name: str
    tool_server_exec_url: str
    applicant_email: str
    tool_server_public_key: str
    status: str
    created_at: datetime


class ToolServerApproveResponse(BaseModel):
    toolserver_id: int
    tool_server_name: str
    tool_server_exec_url: str
    applicant_email: str
    approver_email: str | None
    tool_server_public_key: str
    status: str
    approved_at: datetime | None


class ToolServerChangeKeyRequest(SignedRequest):
    """ツールサーバのリプレース(公開鍵の更新)のリクエスト(toolservers/{toolserver_id}/chkey)。
    旧ツールサーバ(現在登録されている鍵)と、新ツールサーバ(新しい鍵)の、両方が署名する。

    署名対象(旧・新で同じ内容): new_tool_server_public_key, signed_at
        + URLパスの toolserver_id
        + old_tool_server_public_key(サーバに登録されている、現在の公開鍵。リクエストには含めない)
    signature: 旧ツールサーバの署名。プレフィックスは SIGN_CONTEXT_TOOLSERVER_CHKEY_OLD
    new_key_signature: 新ツールサーバの署名(新しい鍵の所持証明)。プレフィックスは SIGN_CONTEXT_TOOLSERVER_CHKEY_NEW
    """

    SIGNATURE_FIELDS: ClassVar[tuple[str, ...]] = ("signature", "new_key_signature")

    signature: str = Field(description="旧ツールサーバ(現在登録されている鍵)の署名(Base64。Ed25519の64バイト)")
    new_tool_server_public_key: str = Field(description="新ツールサーバ公開鍵(Base64。Ed25519の生32バイト)")
    new_key_signature: str = Field(description="新ツールサーバの署名(Base64。Ed25519の64バイト)")

    @field_validator("new_tool_server_public_key")
    @classmethod
    def _validate_new_tool_server_public_key(cls, v: str) -> str:
        return validate_public_key_format(v)

    @field_validator("new_key_signature")
    @classmethod
    def _validate_new_key_signature_format(cls, v: str) -> str:
        try:
            decode_ed25519_signature(v)
        except ValueError:
            raise ValueError("must be Base64 of a 64-byte Ed25519 signature")
        return v


class ToolServerChangeKeyResponse(BaseModel):
    toolserver_id: int
    tool_server_name: str
    tool_server_public_key: str  # 更新後(新しい)の公開鍵
    status: str

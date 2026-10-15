import os
import inspect
import sys
import time
import traceback
PYPATH = os.path.dirname(os.path.abspath(inspect.getfile(inspect.currentframe())))
MODNAME = os.path.splitext(os.path.basename(inspect.getfile(inspect.currentframe())))[0]

# その他のモジュールやROOTPATHのディレクトリ起点の相対パスでのimport
from datetime import datetime
from pydantic import BaseModel, Field, field_validator
from capass_server.schemas.base import SignedRequest, validate_public_key_format


class ToolServerRegisterRequest(SignedRequest):
    """ツールサーバ(公開鍵)の初回登録リクエスト。ツールサーバ自身の秘密鍵で署名する(鍵の所持証明)。

    署名プレフィックス: SIGN_CONTEXT_TOOLSERVER_REGISTER
    署名対象: tool_server_public_key, tool_server_name, signed_at
    """

    tool_server_public_key: str = Field(description="ツールサーバ公開鍵(Base64。Ed25519の生32バイト)")
    tool_server_name: str = Field(min_length=1, max_length=255, description="ツールサーバの名称(管理者が承認時に識別するため)")

    @field_validator("tool_server_public_key")
    @classmethod
    def _validate_tool_server_public_key(cls, v: str) -> str:
        return validate_public_key_format(v)


class ToolServerRegisterResponse(BaseModel):
    toolserver_id: int
    tool_server_name: str
    tool_server_public_key: str
    status: str
    created_at: datetime


class ToolServerApproveResponse(BaseModel):
    toolserver_id: int
    tool_server_name: str
    tool_server_public_key: str
    status: str
    approved_at: datetime | None

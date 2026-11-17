import os
import inspect
import sys
import time
import traceback
PYPATH = os.path.dirname(os.path.abspath(inspect.getfile(inspect.currentframe())))
MODNAME = os.path.splitext(os.path.basename(inspect.getfile(inspect.currentframe())))[0]

# その他のモジュールやROOTPATHのディレクトリ起点の相対パスでのimport
from datetime import datetime
from typing import Any
from pydantic import BaseModel, Field, field_validator
from capass_server.common.globals import (
    NONCE_MAX_LEN,
    NONCE_MIN_LEN,
    NONCE_PATTERN,
    TOOL_ENDPOINT_MAX_LEN,
    TOOL_ENDPOINT_PATTERN,
    TOOL_PROXY_TOKEN_MAX_LEN,
)
from capass_server.common.params_schema import validate_params_schema_definition
from capass_server.schemas.base import SignedRequest, validate_public_key_format


class ToolAddRequest(SignedRequest):
    """ツール(ロール単位のツールエンドポイント)の登録リクエスト(tools/addtool)。承認済みツールサーバの秘密鍵で署名する。
    AIエージェントへの割り当ては、別のAPI(agents/{agent_id}/grant/{tool_endpoint})で行う。

    署名プレフィックス: SIGN_CONTEXT_TOOL_ADDTOOL
    署名対象: tool_endpoint, context, params_schema, tool_proxy_token, tool_server_public_key, signed_at
    """

    tool_endpoint: str = Field(
        min_length=1,
        max_length=TOOL_ENDPOINT_MAX_LEN,
        pattern=TOOL_ENDPOINT_PATTERN,
        description="ツールエンドポイント(全体で一意。URLパス exec/{tool_endpoint} に使うため、スラッシュ・空白・制御文字は不可)",
    )
    context: str = Field(min_length=1, description="ツールのコンテキスト(説明)")
    params_schema: dict[str, Any] = Field(
        description=(
            "ツールパラメータ(params)のスキーマ(JSON Schema)。AIエージェントへの一覧に含まれ、実行時にCaPassサーバがparamsを検証する。"
            '{"type": "object", "properties": {...}} の形で、各パラメータに "description" が必要(パラメータが無い場合は "properties": {} )。'
            "正規表現(pattern / patternProperties)は使えない"
        )
    )
    tool_proxy_token: str = Field(min_length=1, max_length=TOOL_PROXY_TOKEN_MAX_LEN, description="ツール代理トークン(リソース側のロールの認証情報を隠す、ロール単位のトークン)")
    tool_server_public_key: str = Field(description="ツールサーバ公開鍵(Base64。Ed25519の生32バイト)。承認済みである必要がある")

    @field_validator("tool_server_public_key")
    @classmethod
    def _validate_tool_server_public_key(cls, v: str) -> str:
        return validate_public_key_format(v)

    @field_validator("params_schema")
    @classmethod
    def _validate_params_schema(cls, v: dict[str, Any]) -> dict[str, Any]:
        validate_params_schema_definition(v)
        return v


class ToolAddResponse(BaseModel):
    tool_endpoint: str
    created_at: datetime
    token_max_age_sec: int  # ツールサーバは、これより短い間隔で、ツール代理トークンを更新する(chtkn)


class ToolChangeTokenRequest(SignedRequest):
    """ツール代理トークンの更新リクエスト(tools/{tool_endpoint}/chtkn)。ツールを登録したツールサーバの秘密鍵で署名する。
    トークンは、ロール単位なので、1回の更新が、そのツールを割り当てられた全てのAIエージェントに反映される。

    署名プレフィックス: SIGN_CONTEXT_TOOL_CHTKN
    署名対象: tool_proxy_token, tool_server_public_key, nonce, signed_at + URLパスの tool_endpoint
    """

    tool_proxy_token: str = Field(min_length=1, max_length=TOOL_PROXY_TOKEN_MAX_LEN, description="新しいツール代理トークン")
    tool_server_public_key: str = Field(description="ツールを登録したツールサーバの公開鍵(Base64。Ed25519の生32バイト)。承認済みである必要がある")
    nonce: str = Field(pattern=NONCE_PATTERN, description=f"リクエストごとに一意な文字列({NONCE_MIN_LEN}〜{NONCE_MAX_LEN}文字の英数字と - _)。同じnonceのリクエストは、リプレイとして拒否される")

    @field_validator("tool_server_public_key")
    @classmethod
    def _validate_tool_server_public_key(cls, v: str) -> str:
        return validate_public_key_format(v)


class ToolChangeTokenResponse(BaseModel):
    tool_endpoint: str
    tool_proxy_token_updated_at: datetime
    locked: bool  # ロック中のツールは、更新しても、ロックされたまま(ロックの解除は、別の操作)
    token_max_age_sec: int

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
    AGENT_ID_MAX_LEN,
    AGENT_ID_PATTERN,
    EMAIL_MAX_LEN,
    EMAIL_PATTERN,
    NONCE_MAX_LEN,
    NONCE_MIN_LEN,
    NONCE_PATTERN,
    TOOL_ENDPOINT_MAX_LEN,
    TOOL_ENDPOINT_PATTERN,
    TOOL_PROXY_TOKEN_MAX_LEN,
)
from capass_server.common.params_schema import validate_params_schema_definition
from capass_server.schemas.base import SignedRequest, validate_public_key_format


class AgentRegisterRequest(SignedRequest):
    """AIエージェント(公開鍵)の初回登録リクエスト。AIエージェント自身の秘密鍵で署名する(鍵の所持証明)。

    署名プレフィックス: SIGN_CONTEXT_AGENT_REGISTER
    署名対象: agent_id, agent_public_key, applicant_email, signed_at
    """

    agent_id: str = Field(pattern=AGENT_ID_PATTERN, description=f"AIエージェントの識別子(英数字と . _ - のみ、{AGENT_ID_MAX_LEN}文字まで)")
    agent_public_key: str = Field(description="AIエージェント公開鍵(Base64。Ed25519の生32バイト)")
    applicant_email: str = Field(max_length=EMAIL_MAX_LEN, pattern=EMAIL_PATTERN, description="申請者のメールアドレス(管理者が承認前に、申請内容の確認の連絡をするため)")

    @field_validator("agent_public_key")
    @classmethod
    def _validate_agent_public_key(cls, v: str) -> str:
        return validate_public_key_format(v)


class AgentRegisterResponse(BaseModel):
    agent_id: str
    agent_public_key: str
    applicant_email: str
    status: str
    created_at: datetime


class AgentApproveResponse(BaseModel):
    agent_id: str
    agent_public_key: str
    applicant_email: str
    approver_email: str | None
    status: str
    approved_at: datetime | None


class AgentAddToolRequest(SignedRequest):
    """AIエージェントへのツール追加リクエスト(agents/{agent_id}/addtool)。承認済みツールサーバの秘密鍵で署名する。

    署名プレフィックス: SIGN_CONTEXT_AGENT_ADDTOOL
    署名対象: tool_endpoint, context, params_schema, tool_proxy_token, tool_server_public_key, signed_at + URLパスのagent_id
    """

    tool_endpoint: str = Field(
        min_length=1,
        max_length=TOOL_ENDPOINT_MAX_LEN,
        pattern=TOOL_ENDPOINT_PATTERN,
        description="ツールエンドポイント(URLパス exec/{tool_endpoint} に使うため、スラッシュ・空白・制御文字は不可)",
    )
    context: str = Field(min_length=1, description="ツールのコンテキスト(説明)")
    params_schema: dict[str, Any] = Field(
        description=(
            "ツールパラメータ(params)のスキーマ(JSON Schema)。AIエージェントへの一覧に含まれ、実行時にCaPassサーバがparamsを検証する。"
            '{"type": "object", "properties": {...}} の形で、各パラメータに "description" が必要(パラメータが無い場合は "properties": {} )'
        )
    )
    tool_proxy_token: str = Field(min_length=1, max_length=TOOL_PROXY_TOKEN_MAX_LEN, description="ツール代理トークン")
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


class AgentAddToolResponse(BaseModel):
    tool_endpoint: str
    agent_id: str
    created_at: datetime
    token_max_age_sec: int  # ツールサーバは、これより短い間隔で、ツール代理トークンを更新する(chtkn)


class AgentToolItem(BaseModel):
    tool_endpoint: str
    context: str
    params_schema: dict[str, Any]


class AgentToolListResponse(BaseModel):
    agent_id: str
    tools: list[AgentToolItem]


class AgentExecRequest(SignedRequest):
    """ツール実行リクエスト(agents/{agent_id}/exec/{tool_endpoint})。AIエージェント自身の秘密鍵で署名する。

    署名プレフィックス: SIGN_CONTEXT_AGENT_EXEC
    署名対象: params, nonce, signed_at + URLパスの agent_id, tool_endpoint
    """

    params: dict[str, Any] = Field(description="ツールパラメータ(JSONオブジェクト。ツールサーバへそのまま渡される。パラメータが無い場合は {} )")
    nonce: str = Field(pattern=NONCE_PATTERN, description=f"リクエストごとに一意な文字列({NONCE_MIN_LEN}〜{NONCE_MAX_LEN}文字の英数字と - _)。同じnonceのリクエストは、リプレイとして拒否される")


class AgentChangeToolTokenRequest(SignedRequest):
    """ツール代理トークンの更新リクエスト(agents/{agent_id}/chtkn/{tool_endpoint})。ツールを登録したツールサーバの秘密鍵で署名する。

    署名プレフィックス: SIGN_CONTEXT_AGENT_CHTKN
    署名対象: tool_proxy_token, tool_server_public_key, nonce, signed_at + URLパスの agent_id, tool_endpoint
    """

    tool_proxy_token: str = Field(min_length=1, max_length=TOOL_PROXY_TOKEN_MAX_LEN, description="新しいツール代理トークン")
    tool_server_public_key: str = Field(description="ツールを登録したツールサーバの公開鍵(Base64。Ed25519の生32バイト)。承認済みである必要がある")
    nonce: str = Field(pattern=NONCE_PATTERN, description=f"リクエストごとに一意な文字列({NONCE_MIN_LEN}〜{NONCE_MAX_LEN}文字の英数字と - _)。同じnonceのリクエストは、リプレイとして拒否される")

    @field_validator("tool_server_public_key")
    @classmethod
    def _validate_tool_server_public_key(cls, v: str) -> str:
        return validate_public_key_format(v)


class AgentChangeToolTokenResponse(BaseModel):
    tool_endpoint: str
    agent_id: str
    tool_proxy_token_updated_at: datetime
    locked: bool  # ロック中のツールは、更新しても、ロックされたまま(ロックの解除は、別の操作)
    token_max_age_sec: int

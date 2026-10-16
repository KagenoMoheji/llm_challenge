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
from capass_server.schemas.base import EMAIL_PATTERN, SignedRequest, validate_public_key_format


class AgentRegisterRequest(SignedRequest):
    """AIエージェント(公開鍵)の初回登録リクエスト。AIエージェント自身の秘密鍵で署名する(鍵の所持証明)。

    署名プレフィックス: SIGN_CONTEXT_AGENT_REGISTER
    署名対象: agent_id, agent_public_key, applicant_email, signed_at
    """

    agent_id: str = Field(pattern=r"^[A-Za-z0-9._-]{1,128}$", description="AIエージェントの識別子(英数字と . _ - のみ、128文字まで)")
    agent_public_key: str = Field(description="AIエージェント公開鍵(Base64。Ed25519の生32バイト)")
    applicant_email: str = Field(max_length=255, pattern=EMAIL_PATTERN, description="申請者のメールアドレス(管理者が承認前に、申請内容の確認の連絡をするため)")

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
    署名対象: tool_endpoint, context, tool_proxy_token, tool_server_public_key, signed_at + URLパスのagent_id
    """

    tool_endpoint: str = Field(min_length=1, max_length=512, description="ツールエンドポイント")
    context: str = Field(min_length=1, description="ツールのコンテキスト(説明)")
    tool_proxy_token: str = Field(min_length=1, max_length=1024, description="ツール代理トークン")
    tool_server_public_key: str = Field(description="ツールサーバ公開鍵(Base64。Ed25519の生32バイト)。承認済みである必要がある")

    @field_validator("tool_server_public_key")
    @classmethod
    def _validate_tool_server_public_key(cls, v: str) -> str:
        return validate_public_key_format(v)


class AgentAddToolResponse(BaseModel):
    tool_endpoint: str
    agent_id: str
    created_at: datetime

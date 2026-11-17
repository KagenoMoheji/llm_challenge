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
)
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


class AgentGrantRequest(SignedRequest):
    """AIエージェントへのツールの割り当ての申請(agents/{agent_id}/grant/{tool_endpoint})。AIエージェント自身の秘密鍵で署名する。
    申請は承認待ち(pending)になり、承認(agents/{agent_id}/grant/{tool_endpoint}/approve)されると、AIエージェントがツールを使えるようになる。

    署名プレフィックス: SIGN_CONTEXT_AGENT_GRANT
    署名対象: applicant_email, signed_at + URLパスの agent_id, tool_endpoint
    """

    applicant_email: str = Field(max_length=EMAIL_MAX_LEN, pattern=EMAIL_PATTERN, description="申請者(AIエージェントの利用者)のメールアドレス")


class AgentGrantResponse(BaseModel):
    agent_id: str
    tool_endpoint: str
    status: str
    applicant_email: str
    created_at: datetime


class AgentGrantApproveResponse(BaseModel):
    agent_id: str
    tool_endpoint: str
    status: str
    applicant_email: str
    approver_email: str | None
    approved_at: datetime | None


class AgentRevokeRequest(SignedRequest):
    """AIエージェントへのツールの割り当ての取り消し(agents/{agent_id}/revoke/{tool_endpoint})。
    CaPassサーバ管理者、または、そのツールを登録したツールサーバが、署名する。

    署名プレフィックス: SIGN_CONTEXT_AGENT_REVOKE
    署名対象: signer_public_key, signed_at + URLパスの agent_id, tool_endpoint
    """

    signer_public_key: str = Field(description="署名した人の公開鍵(Base64。Ed25519の生32バイト)。管理者(tbl_admin)、または、そのツールを登録した承認済みツールサーバの公開鍵")

    @field_validator("signer_public_key")
    @classmethod
    def _validate_signer_public_key(cls, v: str) -> str:
        return validate_public_key_format(v)


class AgentRevokeResponse(BaseModel):
    agent_id: str
    tool_endpoint: str
    status: str


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

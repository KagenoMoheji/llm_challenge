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


class ToolServerReplaceReserveRequest(SignedRequest):
    """ツールサーバのリプレース(1/3: 予約)。CaPassサーバ管理者が、後継(新)ツールサーバを、事前に承認する(toolservers/{toolserver_id}/replace/reserve)。
    {toolserver_id}は、置き換えられる(旧)ツールサーバ。管理者は、ツールサーバ管理者から、事前に申告された、新ツールサーバの実行URLと公開鍵を、登録する。

    署名プレフィックス: SIGN_CONTEXT_TOOLSERVER_REPLACE_RESERVE
    署名対象: admin_public_key, new_tool_server_public_key, new_tool_server_name, new_tool_server_exec_url, applicant_email, signed_at + URLパスの toolserver_id
    """

    admin_public_key: str = Field(description="署名した管理者の公開鍵(Base64。Ed25519の生32バイト)。tbl_adminに登録された有効な管理者の公開鍵である必要がある")
    new_tool_server_public_key: str = Field(description="新ツールサーバの公開鍵(Base64。Ed25519の生32バイト)")
    new_tool_server_name: str = Field(min_length=1, max_length=TOOL_SERVER_NAME_MAX_LEN, description="新ツールサーバの名称")
    new_tool_server_exec_url: str = Field(
        max_length=EXEC_URL_MAX_LEN,
        pattern=EXEC_URL_PATTERN,
        description="新ツールサーバの実行URL(既定ではhttpsのみ。プライベートIPのURLも使える)。切り替え後は、ここへ中継される",
    )
    applicant_email: str = Field(max_length=EMAIL_MAX_LEN, pattern=EMAIL_PATTERN, description="リプレースを申告したツールサーバ管理者のメールアドレス")

    @field_validator("admin_public_key")
    @classmethod
    def _validate_admin_public_key(cls, v: str) -> str:
        return validate_public_key_format(v)

    @field_validator("new_tool_server_public_key")
    @classmethod
    def _validate_new_tool_server_public_key(cls, v: str) -> str:
        return validate_public_key_format(v)


class ToolServerReplaceReserveResponse(BaseModel):
    toolserver_id: int  # 予約された、新ツールサーバのid
    replaces_toolserver_id: int  # 置き換えられる、旧ツールサーバのid
    tool_server_name: str
    tool_server_exec_url: str
    tool_server_public_key: str
    applicant_email: str
    approver_email: str | None
    status: str  # reserved
    reserved_until: datetime | None  # 予約の期限(これを過ぎると、切り替えられない)


class ToolServerReplaceActivateRequest(SignedRequest):
    """ツールサーバのリプレース(2/3: 切り替え)。予約済みの新ツールサーバへ、ツールを切り替える(toolservers/{toolserver_id}/replace/activate)。
    {toolserver_id}は、置き換えられる(旧)ツールサーバ。旧ツールサーバと新ツールサーバの、両方の署名が必要。

    署名対象(旧・新で同じ内容): new_tool_server_public_key, signed_at
        + URLパスの toolserver_id
        + old_tool_server_public_key(サーバに登録されている、旧ツールサーバの公開鍵。リクエストには含めない)
    signature: 旧ツールサーバの署名。プレフィックスは SIGN_CONTEXT_TOOLSERVER_REPLACE_ACTIVATE_OLD
    new_key_signature: 新ツールサーバの署名(新しい鍵の所持証明)。プレフィックスは SIGN_CONTEXT_TOOLSERVER_REPLACE_ACTIVATE_NEW
    """

    SIGNATURE_FIELDS: ClassVar[tuple[str, ...]] = ("signature", "new_key_signature")

    signature: str = Field(description="旧ツールサーバ(現在アクティブな鍵)の署名(Base64。Ed25519の64バイト)")
    new_tool_server_public_key: str = Field(description="新ツールサーバ公開鍵(Base64。Ed25519の生32バイト)。予約(reserve)された公開鍵である必要がある")
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


class ToolServerReplaceRollbackRequest(SignedRequest):
    """ツールサーバのリプレース(3/3: 切り戻し)。旧ツールサーバへ、ツールを切り戻す(toolservers/{toolserver_id}/replace/rollback)。
    {toolserver_id}は、切り戻し先の、旧(待機中:standby)ツールサーバ。新ツールサーバに不具合があっても使えるよう、旧ツールサーバの署名だけでよい。

    署名プレフィックス: SIGN_CONTEXT_TOOLSERVER_REPLACE_ROLLBACK
    署名対象: signed_at + URLパスの toolserver_id + tool_server_public_key(サーバに登録されている、旧ツールサーバの公開鍵。リクエストには含めない)
    """


class ToolServerReplaceResponse(BaseModel):
    """切り替え(activate)と切り戻し(rollback)のレスポンス。"""

    active_toolserver_id: int  # 切り替え(切り戻し)後に、アクティブになったツールサーバのid
    active_tool_server_exec_url: str
    standby_toolserver_id: int  # 待機中になったツールサーバのid
    standby_until: datetime | None  # 待機中のツールサーバへ、切り替え(切り戻し)できる期限
    moved_tools: int  # 付け替えたツールの数

import os
import inspect
import sys
import time
import traceback
PYPATH = os.path.dirname(os.path.abspath(inspect.getfile(inspect.currentframe())))
MODNAME = os.path.splitext(os.path.basename(inspect.getfile(inspect.currentframe())))[0]

# その他のモジュールやROOTPATHのディレクトリ起点の相対パスでのimport
from pydantic import Field, field_validator
from capass_server.schemas.base import SignedRequest, validate_public_key_format


class ApproveRequest(SignedRequest):
    """承認系API(toolservers/{toolserver_id}/approve, agents/{agent_id}/approve)のリクエスト。CaPassサーバ管理者が署名する。

    署名対象: admin_public_key, signed_at + URLパスのパラメータ(toolserver_id または agent_id)
    """

    admin_public_key: str = Field(description="署名した管理者の公開鍵(Base64。Ed25519の生32バイト)。tbl_adminに登録された有効な管理者の公開鍵である必要がある")

    @field_validator("admin_public_key")
    @classmethod
    def _validate_admin_public_key(cls, v: str) -> str:
        return validate_public_key_format(v)

import os
import inspect
import sys
import time
import traceback
PYPATH = os.path.dirname(os.path.abspath(inspect.getfile(inspect.currentframe())))
MODNAME = os.path.splitext(os.path.basename(inspect.getfile(inspect.currentframe())))[0]

# その他のモジュールやROOTPATHのディレクトリ起点の相対パスでのimport
from sqlalchemy.orm import Session
from capass_server.common.config import SIGNATURE_MAX_SKEW_SEC
from capass_server.common.errors import InvalidSignatureError, NotAdminError, SignatureExpiredError
from capass_server.common.signature import build_signing_message, is_within_skew, verify_ed25519
from capass_server.models import mappers
from capass_server.models.entities import TblAdmin


def verify_signed_request(public_key_b64: str, sign_context: bytes, payload: dict, signature_b64: str) -> None:
    """署名付きリクエストを検証する。署名時刻が許容範囲外ならSignatureExpiredError、署名が不正ならInvalidSignatureError。
    DB参照より先に呼び出し、未認証のリクエストに登録有無などを知らせないようにする。"""
    if not is_within_skew(payload["signed_at"], SIGNATURE_MAX_SKEW_SEC):
        raise SignatureExpiredError()
    message = build_signing_message(sign_context, payload)
    if not verify_ed25519(public_key_b64, message, signature_b64):
        raise InvalidSignatureError()


def verify_admin_request(db: Session, admin_public_key_b64: str, sign_context: bytes, payload: dict, signature_b64: str) -> TblAdmin:
    """管理者による署名付きリクエストを検証し、管理者のレコードを返す。
    署名の検証後に、署名した公開鍵がtbl_adminに登録された有効な管理者のものかを確認する(違えばNotAdminError)。"""
    verify_signed_request(admin_public_key_b64, sign_context, payload, signature_b64)
    admin = mappers.find_tbl_admin_by_public_key(db, admin_public_key_b64)
    if admin is None or not admin.is_active:
        raise NotAdminError()
    return admin

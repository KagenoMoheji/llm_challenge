import os
import inspect
import sys
import time
import traceback
PYPATH = os.path.dirname(os.path.abspath(inspect.getfile(inspect.currentframe())))
MODNAME = os.path.splitext(os.path.basename(inspect.getfile(inspect.currentframe())))[0]

# その他のモジュールやROOTPATHのディレクトリ起点の相対パスでのimport
from pydantic import BaseModel, ConfigDict, Field, StrictInt, field_validator
from capass_server.common.signature import decode_ed25519_public_key, decode_ed25519_signature


# メールアドレスの簡易チェック。EmailStrは値を正規化(ドメインの小文字化等)するため、署名したJSONと一致しなくなる恐れがあり、使わない
EMAIL_PATTERN = r"^[^@\s]+@[^@\s]+\.[^@\s]+$"


def validate_public_key_format(v: str) -> str:
    """Base64(標準)の生32バイトEd25519公開鍵であることを検証する(各スキーマのfield_validatorから使う)。"""
    try:
        decode_ed25519_public_key(v)
    except ValueError:
        raise ValueError("must be Base64 of a 32-byte Ed25519 public key")
    return v


class SignedRequest(BaseModel):
    """署名付きリクエストの基底クラス。全フィールド必須(署名対象を一意にするため)。未知のフィールドは拒否する。

    署名の仕様(Ed25519。公開鍵・署名はBase64):
      メッセージ = エンドポイントごとの固定プレフィックス(common/signature.pyのSIGN_CONTEXT_*) + 正規化JSON
      正規化JSON = 「signature以外の全フィールド + URLパスのパラメータ」を、sort_keys=True / separators=(',', ':') / ensure_ascii=False でJSON化し、UTF-8でエンコードしたもの
    URLパスのパラメータ(例: agent_id, toolserver_id)も署名対象に含めることで、別のリソースへのリクエストの使い回しを防ぐ。
    """

    model_config = ConfigDict(extra="forbid")

    signed_at: StrictInt = Field(description="署名時刻(UNIX秒)。サーバ時刻との差が許容範囲を超えると拒否される")
    signature: str = Field(description="署名(Base64。Ed25519の64バイト)")

    @field_validator("signature")
    @classmethod
    def _validate_signature_format(cls, v: str) -> str:
        try:
            decode_ed25519_signature(v)
        except ValueError:
            raise ValueError("must be Base64 of a 64-byte Ed25519 signature")
        return v

    def signed_payload(self, **path_params) -> dict:
        """署名対象のペイロード(signature以外の全フィールド + URLパスのパラメータ)。"""
        payload = self.model_dump(exclude={"signature"})
        overlap = payload.keys() & path_params.keys()
        if overlap:
            raise ValueError(f"path params overlap with body fields: {sorted(overlap)}")
        return {**payload, **path_params}

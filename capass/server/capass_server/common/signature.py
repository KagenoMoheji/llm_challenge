import os
import inspect
import sys
import time
import traceback
PYPATH = os.path.dirname(os.path.abspath(inspect.getfile(inspect.currentframe())))
MODNAME = os.path.splitext(os.path.basename(inspect.getfile(inspect.currentframe())))[0]

# その他のモジュールやROOTPATHのディレクトリ起点の相対パスでのimport
import base64
import json
from cryptography.exceptions import InvalidSignature
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PublicKey

ED25519_PUBLIC_KEY_LEN = 32
ED25519_SIGNATURE_LEN = 64


def canonical_json_bytes(payload: dict) -> bytes:
    """署名対象のJSONを決定的なバイト列にする(キーのソート/空白なし/UTF-8)。クライアント(CLI)も同じ規則で署名すること。"""
    return json.dumps(payload, sort_keys=True, separators=(",", ":"), ensure_ascii=False).encode("utf-8")


def build_signing_message(sign_context: bytes, payload: dict) -> bytes:
    """署名対象メッセージ = 用途ごとの固定プレフィックス + 正規化JSON。プレフィックスで、別用途の署名の使い回しを防ぐ。"""
    return sign_context + canonical_json_bytes(payload)


def decode_ed25519_public_key(public_key_b64: str) -> Ed25519PublicKey:
    """Base64(標準)の生32バイトEd25519公開鍵をデコードする。不正な場合はValueError。"""
    raw = base64.b64decode(public_key_b64, validate=True)
    if len(raw) != ED25519_PUBLIC_KEY_LEN:
        raise ValueError("invalid Ed25519 public key length")
    return Ed25519PublicKey.from_public_bytes(raw)


def decode_ed25519_signature(signature_b64: str) -> bytes:
    """Base64(標準)の64バイトEd25519署名をデコードする。不正な場合はValueError。"""
    raw = base64.b64decode(signature_b64, validate=True)
    if len(raw) != ED25519_SIGNATURE_LEN:
        raise ValueError("invalid Ed25519 signature length")
    return raw


def verify_ed25519(public_key_b64: str, message: bytes, signature_b64: str) -> bool:
    """署名が正当ならTrue。鍵/署名の形式不正・検証失敗はいずれもFalse(例外は投げない)。"""
    try:
        public_key = decode_ed25519_public_key(public_key_b64)
        signature = decode_ed25519_signature(signature_b64)
        public_key.verify(signature, message)
        return True
    except (ValueError, InvalidSignature):
        return False


def is_within_skew(signed_at: int, max_skew_sec: int, now: float | None = None) -> bool:
    """署名時刻(UNIX秒)が、現在時刻から前後max_skew_sec秒以内ならTrue。"""
    current = time.time() if now is None else now
    return abs(current - signed_at) <= max_skew_sec

import os
import inspect
import sys
import time
import traceback
PYPATH = os.path.dirname(os.path.abspath(inspect.getfile(inspect.currentframe())))
# 以下のROOTPATHでimportの起点を指定
ROOTPATH = os.path.abspath(f"{PYPATH}/..")
MODNAME = os.path.splitext(os.path.basename(inspect.getfile(inspect.currentframe())))[0]
sys.path.append(ROOTPATH)

# その他のモジュールやROOTPATHのディレクトリ起点の相対パスでのimport
import base64
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey
from cryptography.hazmat.primitives.serialization import Encoding, PublicFormat
from capass_server.common.signature import (
    build_signing_message,
    canonical_json_bytes,
    is_within_skew,
    verify_ed25519,
)

CTX = b"test-context\n"


def _keypair():
    priv = Ed25519PrivateKey.generate()
    pub_b64 = base64.b64encode(priv.public_key().public_bytes(Encoding.Raw, PublicFormat.Raw)).decode()
    return priv, pub_b64


def _sign(priv, message: bytes) -> str:
    return base64.b64encode(priv.sign(message)).decode()


def test_canonical_json_is_order_independent():
    assert canonical_json_bytes({"b": 1, "a": "あ"}) == canonical_json_bytes({"a": "あ", "b": 1})
    assert canonical_json_bytes({"a": "あ", "b": 1}) == '{"a":"あ","b":1}'.encode("utf-8")


def test_verify_ok():
    priv, pub = _keypair()
    msg = build_signing_message(CTX, {"x": 1})
    assert verify_ed25519(pub, msg, _sign(priv, msg)) is True


def test_verify_fails_when_payload_tampered():
    priv, pub = _keypair()
    sig = _sign(priv, build_signing_message(CTX, {"x": 1}))
    assert verify_ed25519(pub, build_signing_message(CTX, {"x": 2}), sig) is False


def test_verify_fails_when_context_differs():
    priv, pub = _keypair()
    sig = _sign(priv, build_signing_message(CTX, {"x": 1}))
    assert verify_ed25519(pub, build_signing_message(b"other\n", {"x": 1}), sig) is False


def test_verify_fails_with_other_key():
    priv, _ = _keypair()
    _, other_pub = _keypair()
    msg = build_signing_message(CTX, {"x": 1})
    assert verify_ed25519(other_pub, msg, _sign(priv, msg)) is False


def test_verify_returns_false_on_malformed_input():
    priv, pub = _keypair()
    msg = build_signing_message(CTX, {"x": 1})
    assert verify_ed25519("not-base64!!", msg, _sign(priv, msg)) is False
    assert verify_ed25519(pub, msg, "not-base64!!") is False
    assert verify_ed25519(pub, msg, base64.b64encode(b"short").decode()) is False


def test_is_within_skew():
    assert is_within_skew(1000, 300, now=1000) is True
    assert is_within_skew(700, 300, now=1000) is True
    assert is_within_skew(1300, 300, now=1000) is True
    assert is_within_skew(699, 300, now=1000) is False
    assert is_within_skew(1301, 300, now=1000) is False

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
import pytest
from cryptography.fernet import Fernet, InvalidToken
from capass_server.common.crypto import create_token_cipher, decrypt_token, encrypt_token


def _key() -> str:
    return Fernet.generate_key().decode()


def test_roundtrip_with_configured_key():
    enc = encrypt_token("proxy-token-1")
    assert enc != "proxy-token-1"
    assert "proxy-token-1" not in enc
    assert decrypt_token(enc) == "proxy-token-1"


def test_ciphertext_differs_each_time():
    assert encrypt_token("same") != encrypt_token("same")


def test_unicode_roundtrip():
    assert decrypt_token(encrypt_token("トークン🔑")) == "トークン🔑"


def test_wrong_key_cannot_decrypt():
    enc = encrypt_token("secret", create_token_cipher([_key()]))
    with pytest.raises(InvalidToken):
        decrypt_token(enc, create_token_cipher([_key()]))


def test_key_rotation():
    old, new = _key(), _key()
    enc_old = encrypt_token("secret", create_token_cipher([old]))
    rotated = create_token_cipher([new, old])  # 先頭=新鍵で暗号化、旧鍵でも復号できる
    assert decrypt_token(enc_old, rotated) == "secret"
    enc_new = encrypt_token("secret", rotated)
    assert decrypt_token(enc_new, create_token_cipher([new])) == "secret"  # 新規分は新鍵だけで復号できる


def test_invalid_keys_are_rejected():
    with pytest.raises(ValueError):
        create_token_cipher([])
    with pytest.raises(ValueError):
        create_token_cipher(["not-a-valid-fernet-key"])

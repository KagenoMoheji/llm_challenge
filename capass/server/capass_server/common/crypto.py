import os
import inspect
import sys
import time
import traceback
PYPATH = os.path.dirname(os.path.abspath(inspect.getfile(inspect.currentframe())))
MODNAME = os.path.splitext(os.path.basename(inspect.getfile(inspect.currentframe())))[0]

# その他のモジュールやROOTPATHのディレクトリ起点の相対パスでのimport
from cryptography.fernet import Fernet, MultiFernet
from capass_server.common.config import TOKEN_ENCRYPTION_KEYS


def create_token_cipher(keys: list[str]) -> MultiFernet:
    """Fernet(AES-128-CBC + HMAC-SHA256)の暗号器を作る。先頭の鍵で暗号化し、全ての鍵で復号を試す(鍵ローテーション対応)。
    鍵が空/不正な場合はValueError(起動時に気づけるようimport時に生成する)。"""
    if not keys:
        raise ValueError("at least one token encryption key is required")
    return MultiFernet([Fernet(k) for k in keys])


token_cipher = create_token_cipher(TOKEN_ENCRYPTION_KEYS)


def encrypt_token(plaintext: str, cipher: MultiFernet | None = None) -> str:
    """ツール代理トークンを暗号化する(DB保存用)。暗号化のたびにIVが変わるため、同じ平文でも結果は毎回異なる。"""
    c = cipher if cipher is not None else token_cipher
    return c.encrypt(plaintext.encode("utf-8")).decode("ascii")


def decrypt_token(ciphertext: str, cipher: MultiFernet | None = None) -> str:
    """暗号化済みトークンを平文に戻す(ツールサーバへの中継用)。復号できない場合はcryptography.fernet.InvalidToken。"""
    c = cipher if cipher is not None else token_cipher
    return c.decrypt(ciphertext.encode("ascii")).decode("utf-8")

import os
import inspect
import sys
import time
import traceback
PYPATH = os.path.dirname(os.path.abspath(inspect.getfile(inspect.currentframe())))
MODNAME = os.path.splitext(os.path.basename(inspect.getfile(inspect.currentframe())))[0]

# その他のモジュールやROOTPATHのディレクトリ起点の相対パスでのimport
import base64
import hashlib
from dataclasses import dataclass
from pathlib import Path
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey
from cryptography.hazmat.primitives.serialization import Encoding, NoEncryption, PrivateFormat, PublicFormat
from capass_core.errors import AppDirectoryError
from capass_core.fileio import write_atomic
from capass_core.paths import AppPaths
from capass_core.system import SystemOps

PRIVATE_KEY_MODE = 0o600  # 秘密鍵は、所有者(実行ユーザ)だけが読み書きできる
PUBLIC_KEY_MODE = 0o644


@dataclass(frozen=True)
class KeyPairInfo:
    mode: str
    private_key_path: Path
    public_key_path: Path
    public_key_b64: str  # CaPassサーバへ登録する、公開鍵(Base64。Ed25519の生32バイト)
    fingerprint: str  # 公開鍵のSHA-256(管理者が、別の経路で、公開鍵を照合するための目印)
    reused: bool  # 既存の鍵を使った(新しく作っていない)


def generate_keypair() -> tuple[bytes, bytes]:
    """Ed25519の鍵ペアを作り、(秘密鍵の生32バイト, 公開鍵の生32バイト)を返す。CaPassサーバの署名の検証と、同じ形式。"""
    private = Ed25519PrivateKey.generate()
    private_raw = private.private_bytes(Encoding.Raw, PrivateFormat.Raw, NoEncryption())
    public_raw = private.public_key().public_bytes(Encoding.Raw, PublicFormat.Raw)
    return private_raw, public_raw


def encode_b64(raw: bytes) -> str:
    return base64.b64encode(raw).decode("ascii")


def fingerprint(public_raw: bytes) -> str:
    return "SHA256:" + hashlib.sha256(public_raw).hexdigest()


def load_key_info(paths: AppPaths, mode: str) -> KeyPairInfo | None:
    """鍵ファイルが存在すれば、その情報を返す(存在しなければNone)。初期化が途中で止まった後の、再実行で、既存の鍵を使うため。"""
    private_path, public_path = paths.private_key_path(mode), paths.public_key_path(mode)
    if not private_path.exists() and not public_path.exists():
        return None
    try:
        public_raw = base64.b64decode(public_path.read_text(encoding="utf-8").strip(), validate=True)
        base64.b64decode(private_path.read_text(encoding="utf-8").strip(), validate=True)
    except (OSError, ValueError):
        raise AppDirectoryError(f"鍵ファイルを読めません(片方だけ存在する、または壊れています): {private_path}、{public_path}\n  確認して、不要なファイルを削除してから、やり直してください。")
    if len(public_raw) != 32:
        raise AppDirectoryError(f"公開鍵のファイルが、不正です: {public_path}")
    return KeyPairInfo(mode, private_path, public_path, encode_b64(public_raw), fingerprint(public_raw), reused=True)


def create_key_files(paths: AppPaths, mode: str, ops: SystemOps, user: str, group: str) -> KeyPairInfo:
    """modeの鍵ペアを作り、<keys>/<mode>.key(秘密鍵)と <mode>.pub(公開鍵)に保存して、実行ユーザの持ち物にする。
    既存の鍵は、上書きしない(既存なら、そのまま使う)。鍵を作り直すと、CaPassサーバに登録した本人確認が、変わってしまうため。"""
    existing = load_key_info(paths, mode)
    if existing is not None:
        return existing
    private_raw, public_raw = generate_keypair()
    private_path, public_path = paths.private_key_path(mode), paths.public_key_path(mode)
    try:
        write_atomic(private_path, encode_b64(private_raw) + "\n", PRIVATE_KEY_MODE)
        ops.chown(private_path, user, group)
        write_atomic(public_path, encode_b64(public_raw) + "\n", PUBLIC_KEY_MODE)
        ops.chown(public_path, user, group)
    except OSError as e:
        raise AppDirectoryError(f"鍵ファイルを書き込めません: {e}")
    return KeyPairInfo(mode, private_path, public_path, encode_b64(public_raw), fingerprint(public_raw), reused=False)

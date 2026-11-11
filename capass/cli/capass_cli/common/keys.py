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
from capass_cli.common.errors import HomeDirectoryError, KeyAlreadyExistsError
from capass_cli.common.fileio import write_atomic
from capass_cli.common.paths import keys_dir, private_key_path, public_key_path, role_dir
from capass_cli.common.roles import ensure_role_available, write_role_marker

PRIVATE_KEY_MODE = 0o600  # 秘密鍵は、所有者だけが読み書きできる
PUBLIC_KEY_MODE = 0o644
DIRECTORY_MODE = 0o700


@dataclass(frozen=True)
class KeyPairInfo:
    role: str
    private_key_path: Path
    public_key_path: Path
    public_key_b64: str  # CaPassサーバへ登録する、公開鍵(Base64。Ed25519の生32バイト)
    fingerprint: str  # 公開鍵のSHA-256(管理者が、別の経路で、公開鍵を照合するための目印)


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


def _ensure_private_dir(path: Path) -> None:
    try:
        path.mkdir(parents=True, exist_ok=True)  # 途中のディレクトリも作る(--home に、まだ無い場所を指定した場合)
        os.chmod(path, DIRECTORY_MODE)
    except OSError as e:
        raise HomeDirectoryError(f"ディレクトリを作成できません: {path} ({e})")


def create_key_files(home: Path, role: str, force: bool = False) -> KeyPairInfo:
    """roleの鍵ペアを作り、<home>/<role>/keys/<role>.key(秘密鍵)と <role>.pub(公開鍵)に保存する。
    --force なしでは、鍵が存在する場合は、KeyAlreadyExistsError(鍵を作り直すと、CaPassサーバに登録した本人確認が、変わってしまうため)。"""
    if home.exists() and not home.is_dir():
        raise HomeDirectoryError(f"ホームディレクトリが、ディレクトリではありません: {home}")
    private_path, public_path = private_key_path(home, role), public_key_path(home, role)
    existing = [p for p in (private_path, public_path) if p.exists()]
    if existing and not force:
        raise KeyAlreadyExistsError(
            "鍵ファイルが、すでに存在します: " + "、".join(str(p) for p in existing) + "\n"
            "  鍵を作り直すと、CaPassサーバに登録した公開鍵が、使えなくなります。作り直す場合は、--force を指定してください。"
        )
    for directory in (home, role_dir(home, role), keys_dir(home, role)):
        _ensure_private_dir(directory)

    private_raw, public_raw = generate_keypair()
    try:
        write_atomic(private_path, encode_b64(private_raw) + "\n", PRIVATE_KEY_MODE)
        write_atomic(public_path, encode_b64(public_raw) + "\n", PUBLIC_KEY_MODE)
    except OSError as e:
        raise HomeDirectoryError(f"鍵ファイルを書き込めません: {e}")
    return KeyPairInfo(role, private_path, public_path, encode_b64(public_raw), fingerprint(public_raw))


def setup_role_keys(home: Path, role: str, force: bool = False) -> KeyPairInfo:
    """役割の確認(同居の防止)→ 鍵の作成 → 役割ファイルの記録、を行う。確認に失敗したら、何も作らない。"""
    ensure_role_available(home, role)
    info = create_key_files(home, role, force)
    write_role_marker(home, role)
    return info

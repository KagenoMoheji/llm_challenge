import os
import inspect
import sys
import time
import traceback
PYPATH = os.path.dirname(os.path.abspath(inspect.getfile(inspect.currentframe())))
ROOTPATH = os.path.abspath(f"{PYPATH}/..")
MODNAME = os.path.splitext(os.path.basename(inspect.getfile(inspect.currentframe())))[0]
# 以下のROOTPATHでimportの起点を指定
sys.path.append(ROOTPATH)

# その他のモジュールやROOTPATHのディレクトリ起点の相対パスでのimport
import base64
import stat
import pytest
from pathlib import Path
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey, Ed25519PublicKey
from capass_cli.common.errors import HomeDirectoryError, KeyAlreadyExistsError
from capass_cli.common.keys import create_key_files, encode_b64, fingerprint, generate_keypair, setup_role_keys
from capass_cli.common.paths import keys_dir, private_key_path, public_key_path
from capass_cli.common.roles import ROLE_TOOLSERVER


def _mode(path: Path) -> int:
    return stat.S_IMODE(path.stat().st_mode)


def test_generate_keypair_is_ed25519_raw_32_bytes_and_usable():
    private_raw, public_raw = generate_keypair()
    assert len(private_raw) == 32 and len(public_raw) == 32  # CaPassサーバが期待する、生の32バイト
    signature = Ed25519PrivateKey.from_private_bytes(private_raw).sign(b"message")
    Ed25519PublicKey.from_public_bytes(public_raw).verify(signature, b"message")  # 秘密鍵と公開鍵が、対になっている(不正なら例外)


def test_generate_keypair_is_random():
    assert generate_keypair()[0] != generate_keypair()[0]


def test_fingerprint_is_sha256_hex_and_deterministic():
    _, public_raw = generate_keypair()
    value = fingerprint(public_raw)
    assert value.startswith("SHA256:") and len(value) == len("SHA256:") + 64
    assert value == fingerprint(public_raw)
    assert value != fingerprint(generate_keypair()[1])


def test_create_key_files_writes_base64_keys_named_by_role(tmp_path):
    home = tmp_path / "capass"
    info = create_key_files(home, ROLE_TOOLSERVER)
    assert info.private_key_path == home / "toolserver" / "keys" / "toolserver.key"  # ディレクトリとファイル名に、役割が入る
    assert info.public_key_path == home / "toolserver" / "keys" / "toolserver.pub"
    private_raw = base64.b64decode(info.private_key_path.read_text(encoding="utf-8").strip(), validate=True)
    public_raw = base64.b64decode(info.public_key_path.read_text(encoding="utf-8").strip(), validate=True)
    assert len(private_raw) == 32 and len(public_raw) == 32
    assert info.public_key_b64 == encode_b64(public_raw)
    assert info.fingerprint == fingerprint(public_raw)
    # 保存した秘密鍵から、保存した公開鍵が、導出できる
    derived = Ed25519PrivateKey.from_private_bytes(private_raw).public_key()
    Ed25519PublicKey.from_public_bytes(public_raw).verify(Ed25519PrivateKey.from_private_bytes(private_raw).sign(b"x"), b"x")
    assert derived is not None


def test_create_key_files_permissions_are_restrictive(tmp_path):
    import os

    if os.name == "nt":  # Windowsでは、POSIXのパーミッションを使わない
        return
    home = tmp_path / "capass"
    info = create_key_files(home, ROLE_TOOLSERVER)
    assert _mode(info.private_key_path) == 0o600  # 秘密鍵は、所有者だけが読み書きできる
    assert _mode(info.public_key_path) == 0o644
    for directory in (home, home / "toolserver", keys_dir(home, ROLE_TOOLSERVER)):
        assert _mode(directory) == 0o700
    assert [p.name for p in keys_dir(home, ROLE_TOOLSERVER).iterdir() if p.name.startswith(".")] == []  # 一時ファイルが残らない


def test_create_key_files_refuses_to_overwrite_without_force(tmp_path):
    home = tmp_path / "capass"
    first = create_key_files(home, ROLE_TOOLSERVER)
    before = first.private_key_path.read_text(encoding="utf-8")
    with pytest.raises(KeyAlreadyExistsError):
        create_key_files(home, ROLE_TOOLSERVER)
    assert first.private_key_path.read_text(encoding="utf-8") == before  # 上書きされていない


def test_create_key_files_refuses_even_if_only_one_key_file_exists(tmp_path):
    home = tmp_path / "capass"
    keys_dir(home, ROLE_TOOLSERVER).mkdir(parents=True)
    public_key_path(home, ROLE_TOOLSERVER).write_text("existing\n", encoding="utf-8")
    with pytest.raises(KeyAlreadyExistsError):
        create_key_files(home, ROLE_TOOLSERVER)
    assert not private_key_path(home, ROLE_TOOLSERVER).exists()


def test_create_key_files_with_force_replaces_both_keys(tmp_path):
    home = tmp_path / "capass"
    first = create_key_files(home, ROLE_TOOLSERVER)
    second = create_key_files(home, ROLE_TOOLSERVER, force=True)
    assert second.public_key_b64 != first.public_key_b64
    assert second.public_key_path.read_text(encoding="utf-8").strip() == second.public_key_b64


def test_home_that_is_a_file_is_an_error(tmp_path):
    home = tmp_path / "not-a-directory"
    home.write_text("x", encoding="utf-8")
    with pytest.raises(HomeDirectoryError):
        create_key_files(home, ROLE_TOOLSERVER)


def test_setup_role_keys_records_the_role(tmp_path):
    home = tmp_path / "capass"
    setup_role_keys(home, ROLE_TOOLSERVER)
    assert (home / "role").read_text(encoding="utf-8").strip() == "toolserver"

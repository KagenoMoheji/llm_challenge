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
import os
import stat
import pytest
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey, Ed25519PublicKey
from capass_core.cli.common.errors import AppDirectoryError
from capass_core.cli.common.keys import create_key_files, encode_b64, fingerprint, generate_keypair, load_key_info
from capass_core.cli.common.paths import AppPaths
from capass_core.cli.common.modes import MODE_TOOLSERVER
from capass_core.cli.common.testing import FakeSystemOps


def _paths(tmp_path):
    paths = AppPaths(root=tmp_path / "capass")
    paths.keys_dir.mkdir(parents=True)
    return paths


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
    assert value == fingerprint(public_raw) and value != fingerprint(generate_keypair()[1])


def test_create_key_files_writes_base64_keys_named_by_mode_and_gives_them_to_the_service_user(tmp_path):
    paths, ops = _paths(tmp_path), FakeSystemOps()
    info = create_key_files(paths, MODE_TOOLSERVER, ops, "capass", "capass")
    assert info.private_key_path == paths.keys_dir / "toolserver.key" and info.public_key_path == paths.keys_dir / "toolserver.pub"  # ファイル名に、モードが入る
    private_raw = base64.b64decode(info.private_key_path.read_text(encoding="utf-8").strip(), validate=True)
    public_raw = base64.b64decode(info.public_key_path.read_text(encoding="utf-8").strip(), validate=True)
    assert len(private_raw) == 32 and len(public_raw) == 32 and info.reused is False
    assert info.public_key_b64 == encode_b64(public_raw) and info.fingerprint == fingerprint(public_raw)
    derived = Ed25519PrivateKey.from_private_bytes(private_raw).public_key().public_bytes_raw()
    assert derived == public_raw  # 保存した秘密鍵から、保存した公開鍵が、導出できる
    assert ops.chowns[str(info.private_key_path)] == ("capass", "capass") and ops.chowns[str(info.public_key_path)] == ("capass", "capass")


def test_key_file_permissions_are_restrictive(tmp_path):
    if os.name == "nt":  # Windowsでは、POSIXのパーミッションを使わない
        return
    info = create_key_files(_paths(tmp_path), MODE_TOOLSERVER, FakeSystemOps(), "capass", "capass")
    assert stat.S_IMODE(info.private_key_path.stat().st_mode) == 0o600  # 秘密鍵は、所有者だけが読み書きできる
    assert stat.S_IMODE(info.public_key_path.stat().st_mode) == 0o644
    assert [p.name for p in info.private_key_path.parent.iterdir() if p.name.startswith(".")] == []  # 一時ファイルが残らない


def test_existing_keys_are_reused_and_never_overwritten(tmp_path):
    paths, ops = _paths(tmp_path), FakeSystemOps()
    first = create_key_files(paths, MODE_TOOLSERVER, ops, "capass", "capass")
    before = first.private_key_path.read_text(encoding="utf-8")
    second = create_key_files(paths, MODE_TOOLSERVER, ops, "capass", "capass")
    assert second.reused is True and second.public_key_b64 == first.public_key_b64
    assert first.private_key_path.read_text(encoding="utf-8") == before  # 上書きされていない


def test_load_key_info_returns_none_without_keys(tmp_path):
    assert load_key_info(_paths(tmp_path), MODE_TOOLSERVER) is None


def test_only_one_key_file_or_broken_files_are_an_error(tmp_path):
    paths = _paths(tmp_path)
    paths.public_key_path(MODE_TOOLSERVER).write_text("AAAA\n", encoding="utf-8")  # 片方だけ
    with pytest.raises(AppDirectoryError):
        create_key_files(paths, MODE_TOOLSERVER, FakeSystemOps(), "capass", "capass")
    assert not paths.private_key_path(MODE_TOOLSERVER).exists()  # 新しい鍵を作って、混ぜない
    paths.private_key_path(MODE_TOOLSERVER).write_text("not base64!!\n", encoding="utf-8")
    with pytest.raises(AppDirectoryError):
        load_key_info(paths, MODE_TOOLSERVER)

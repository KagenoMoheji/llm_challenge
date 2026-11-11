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
import pytest
from pathlib import Path
from capass_cli import __version__
from capass_cli.main import main


def _keygen(tmp_path: Path, *extra: str, home: Path | None = None) -> int:
    return main(["--home", str(home or tmp_path / "capass"), "toolserver", "keygen", *extra])


def test_keygen_creates_keys_and_prints_public_info_only(tmp_path, capsys):
    assert _keygen(tmp_path) == 0
    home = tmp_path / "capass"
    private_text = (home / "toolserver" / "keys" / "toolserver.key").read_text(encoding="utf-8").strip()
    public_text = (home / "toolserver" / "keys" / "toolserver.pub").read_text(encoding="utf-8").strip()
    assert len(base64.b64decode(private_text, validate=True)) == 32
    assert len(base64.b64decode(public_text, validate=True)) == 32
    out = capsys.readouterr().out
    assert public_text in out and "SHA256:" in out  # 公開鍵とフィンガープリントを表示する
    assert private_text not in out  # 秘密鍵は、表示しない
    assert str(home / "toolserver" / "keys" / "toolserver.key") in out  # 保存先は、表示する
    assert (home / "role").read_text(encoding="utf-8").strip() == "toolserver"


def test_keygen_twice_is_an_error_and_keeps_the_keys(tmp_path, capsys):
    assert _keygen(tmp_path) == 0
    key_file = tmp_path / "capass" / "toolserver" / "keys" / "toolserver.key"
    before = key_file.read_text(encoding="utf-8")
    capsys.readouterr()
    assert _keygen(tmp_path) == 4
    err = capsys.readouterr().err
    assert "エラー" in err and "--force" in err
    assert key_file.read_text(encoding="utf-8") == before


def test_keygen_force_replaces_the_keys(tmp_path):
    assert _keygen(tmp_path) == 0
    public_file = tmp_path / "capass" / "toolserver" / "keys" / "toolserver.pub"
    before = public_file.read_text(encoding="utf-8")
    assert _keygen(tmp_path, "--force") == 0
    assert public_file.read_text(encoding="utf-8") != before


def test_keygen_is_refused_on_a_server_set_up_as_an_agent(tmp_path, capsys):
    home = tmp_path / "capass"
    (home / "agent" / "keys").mkdir(parents=True)  # AIエージェントとして、設定済み
    assert _keygen(tmp_path) == 3  # 役割の同居
    err = capsys.readouterr().err
    assert "AIエージェント" in err and "同居" in err
    assert not (home / "toolserver").exists()  # 何も作らない
    assert not (home / "role").exists()


def test_keygen_is_refused_when_the_role_file_says_another_role(tmp_path):
    home = tmp_path / "capass"
    home.mkdir()
    (home / "role").write_text("agent\n", encoding="utf-8")
    assert _keygen(tmp_path) == 3
    assert not (home / "toolserver").exists()


def test_keygen_after_keygen_is_not_a_role_conflict(tmp_path):
    assert _keygen(tmp_path) == 0
    assert _keygen(tmp_path, "--force") == 0  # 同じ役割の再作成は、役割の同居ではない


def test_home_priority_option_then_env_then_default(tmp_path, monkeypatch):
    from_env, from_option, default_home = tmp_path / "env", tmp_path / "option", tmp_path / "default-home"
    monkeypatch.setenv("CAPASS_HOME", str(from_env))
    monkeypatch.setenv("HOME", str(default_home))
    monkeypatch.setenv("USERPROFILE", str(default_home))
    assert main(["toolserver", "keygen"]) == 0  # 環境変数
    assert (from_env / "toolserver" / "keys" / "toolserver.key").exists()
    assert main(["--home", str(from_option), "toolserver", "keygen"]) == 0  # オプションが、環境変数より優先
    assert (from_option / "toolserver" / "keys" / "toolserver.key").exists()
    monkeypatch.delenv("CAPASS_HOME")
    assert main(["toolserver", "keygen"]) == 0  # 既定: ~/.capass
    assert (default_home / ".capass" / "toolserver" / "keys" / "toolserver.key").exists()


def test_version_option(capsys):
    with pytest.raises(SystemExit) as e:
        main(["--version"])
    assert e.value.code == 0
    assert __version__ in capsys.readouterr().out


def test_usage_errors_exit_with_2():
    for argv in ([], ["toolserver"], ["no-such-command"], ["toolserver", "no-such-subcommand"]):
        with pytest.raises(SystemExit) as e:
            main(argv)
        assert e.value.code == 2, argv

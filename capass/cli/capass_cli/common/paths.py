import os
import inspect
import sys
import time
import traceback
PYPATH = os.path.dirname(os.path.abspath(inspect.getfile(inspect.currentframe())))
MODNAME = os.path.splitext(os.path.basename(inspect.getfile(inspect.currentframe())))[0]

# その他のモジュールやROOTPATHのディレクトリ起点の相対パスでのimport
from pathlib import Path

HOME_ENV_VAR = "CAPASS_HOME"
DEFAULT_HOME_DIRNAME = ".capass"
KEYS_DIRNAME = "keys"


def resolve_home(home_option: str | None) -> Path:
    """CaPassクライアントのホームディレクトリを決める。優先順位: --home オプション > 環境変数 CAPASS_HOME > ~/.capass"""
    if home_option:
        path = Path(home_option)
    elif os.environ.get(HOME_ENV_VAR):
        path = Path(os.environ[HOME_ENV_VAR])
    else:
        path = Path.home() / DEFAULT_HOME_DIRNAME
    return path.expanduser().resolve()


def role_dir(home: Path, role: str) -> Path:
    """役割ごとのディレクトリ。鍵などの、その役割のファイルは、全てこの下に置く(ディレクトリ名で、役割を区別する)。"""
    return home / role


def keys_dir(home: Path, role: str) -> Path:
    return role_dir(home, role) / KEYS_DIRNAME


def private_key_path(home: Path, role: str) -> Path:
    """秘密鍵のファイル。ファイル名にも役割を入れる(別の場所へコピーされても、どの役割の鍵か分かるように)。例: ~/.capass/toolserver/keys/toolserver.key"""
    return keys_dir(home, role) / f"{role}.key"


def public_key_path(home: Path, role: str) -> Path:
    """公開鍵のファイル。例: ~/.capass/toolserver/keys/toolserver.pub"""
    return keys_dir(home, role) / f"{role}.pub"

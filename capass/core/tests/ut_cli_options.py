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
from pathlib import Path
from capass_core.cli.common.errors import InvalidOptionError
from capass_core.cli.common.paths import AppPaths
from capass_core.cli.common.init_steps import InitOptions, validate_options

PATHS = AppPaths(root=Path("/opt/capass"))


def test_defaults_are_filled_from_the_app_directory():
    options = validate_options(InitOptions(user="capass", port=31000), PATHS)
    assert options.log_dir == Path("/opt/capass/logs") and options.data_dir == Path("/opt/capass/data")


def test_custom_directories_are_accepted_and_normalized():
    options = validate_options(InitOptions(user="svc", port=40000, log_dir=Path("/var/log/capass/"), data_dir=Path("/var/lib/capass/../capass-data")), PATHS)
    assert (options.log_dir, options.data_dir) == (Path("/var/log/capass"), Path("/var/lib/capass-data"))


def test_invalid_user_names_are_rejected():
    for user in ("root", "", "Capass", "1capass", "has space", "a" * 33, "capass;rm", "ユーザ"):
        with pytest.raises(InvalidOptionError):
            validate_options(InitOptions(user=user, port=31000), PATHS)


def test_valid_user_names_are_accepted():
    for user in ("capass", "_capass", "capass-ts", "a", "svc_1"):
        validate_options(InitOptions(user=user, port=31000), PATHS)


def test_port_must_be_unprivileged():
    for port in (0, 80, 1023, 65536, -1):
        with pytest.raises(InvalidOptionError):
            validate_options(InitOptions(user="capass", port=port), PATHS)
    for port in (1024, 31000, 65535):
        validate_options(InitOptions(user="capass", port=port), PATHS)


def test_directories_must_be_safe_absolute_paths():
    for bad in (Path("relative/logs"), Path("/"), Path("/opt/capass"), Path("/opt/capass/bin"), Path("/opt/capass/confs/x"), Path("/opt/capass/keys")):
        with pytest.raises(InvalidOptionError):
            validate_options(InitOptions(user="capass", port=31000, log_dir=bad), PATHS)
        with pytest.raises(InvalidOptionError):
            validate_options(InitOptions(user="capass", port=31000, data_dir=bad), PATHS)


def test_log_and_data_directories_must_differ():
    with pytest.raises(InvalidOptionError):
        validate_options(InitOptions(user="capass", port=31000, log_dir=Path("/var/x"), data_dir=Path("/var/x")), PATHS)


def test_error_exit_code_is_2():
    with pytest.raises(InvalidOptionError) as e:
        validate_options(InitOptions(user="root", port=31000), PATHS)
    assert e.value.exit_code == 2

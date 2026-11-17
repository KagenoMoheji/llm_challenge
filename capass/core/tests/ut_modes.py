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
from capass_core.errors import ModeNotInstalledError, MultipleModesInstalledError
from capass_core.modes import (
    MODE_AGENT,
    MODE_SERVER,
    MODE_TOOLSERVER,
    detect_installed_modes,
    ensure_single_mode,
    install_hint,
    package_name,
)


def _finder(*installed_packages):
    """指定のパッケージだけが、インストールされている、find_specの代わり。"""
    return lambda name: object() if name in installed_packages else None


def test_package_names_follow_the_convention():
    assert [package_name(m) for m in (MODE_SERVER, MODE_TOOLSERVER, MODE_AGENT)] == ["capass_server", "capass_toolserver", "capass_agent"]
    assert install_hint(MODE_TOOLSERVER) == 'pip install "capass[toolserver]"'


def test_detect_installed_modes_by_package_presence():
    assert detect_installed_modes(_finder()) == set()
    assert detect_installed_modes(_finder("capass_toolserver")) == {MODE_TOOLSERVER}
    assert detect_installed_modes(_finder("capass_agent", "capass_server", "capass_other")) == {MODE_AGENT, MODE_SERVER}  # 関係のないパッケージは、無視する


def test_detect_installed_modes_does_not_import_the_packages(monkeypatch):
    import importlib.util
    import sys

    sys.modules.pop("capass_toolserver_never_imported", None)
    detect_installed_modes(importlib.util.find_spec)  # 本物のfind_specで、エラーにならない(インストールされていないので、空)
    assert "capass_toolserver_never_imported" not in sys.modules


def test_exactly_one_mode_is_accepted():
    for mode in (MODE_SERVER, MODE_TOOLSERVER, MODE_AGENT):
        assert ensure_single_mode({mode}) == mode


def test_no_mode_installed_tells_how_to_install():
    with pytest.raises(ModeNotInstalledError) as e:
        ensure_single_mode(set())
    message = str(e.value)
    for mode in ("toolserver", "agent", "server"):
        assert f'pip install "capass[{mode}]"' in message
    assert e.value.exit_code == 10


def test_two_or_more_modes_are_refused_and_listed():
    for installed in ({MODE_AGENT, MODE_TOOLSERVER}, {MODE_SERVER, MODE_TOOLSERVER}, {MODE_AGENT, MODE_SERVER, MODE_TOOLSERVER}):
        with pytest.raises(MultipleModesInstalledError) as e:
            ensure_single_mode(installed)
        message = str(e.value)
        assert "同時に使うことはできません" in message and "pip uninstall" in message
        for mode in installed:
            assert mode in message  # 現在のインストール状態
        assert e.value.exit_code == 11

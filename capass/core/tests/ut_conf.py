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
from capass_core.conf import read_conf, read_installed_mode, render_conf
from capass_core.errors import AppDirectoryError
from capass_core.paths import AppPaths


def test_render_and_read_roundtrip(tmp_path):
    paths = AppPaths(root=tmp_path / "capass")
    paths.confs_dir.mkdir(parents=True)
    text = render_conf("toolserver", "0.1.6", "capass", "capass", 31000, Path("/var/log/capass"), Path("/var/lib/capass"), paths)
    paths.conf_file.write_text(text, encoding="utf-8")
    conf = read_conf(paths.conf_file)
    assert (conf.mode, conf.version, conf.user, conf.group, conf.port) == ("toolserver", "0.1.6", "capass", "capass", 31000)
    assert (conf.log_dir, conf.data_dir) == ("/var/log/capass", "/var/lib/capass")
    assert conf.initialized_at.endswith("Z")
    assert text.startswith("#")  # 先頭に、説明のコメントがある


def test_values_with_percent_are_kept(tmp_path):
    paths = AppPaths(root=tmp_path / "capass")
    paths.confs_dir.mkdir(parents=True)
    paths.conf_file.write_text(render_conf("toolserver", "0.1.6", "capass", "capass", 31000, Path("/var/log/50%/capass"), Path("/d"), paths), encoding="utf-8")
    assert read_conf(paths.conf_file).log_dir == "/var/log/50%/capass"  # 値の中の % を、変換しない


def test_read_installed_mode_is_none_without_conf(tmp_path):
    assert read_installed_mode(AppPaths(root=tmp_path / "none")) is None


def test_broken_conf_is_an_error(tmp_path):
    paths = AppPaths(root=tmp_path / "capass")
    paths.confs_dir.mkdir(parents=True)
    for content in ("broken", "[capass]\nmode = toolserver\n", "[capass]\nmode = toolserver\nversion = 1\ninitialized_at = x\n[service]\nuser = u\ngroup = g\nport = abc\n[paths]\nlog_dir = /l\ndata_dir = /d\n"):
        paths.conf_file.write_text(content, encoding="utf-8")
        with pytest.raises(AppDirectoryError):
            read_installed_mode(paths)

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
from pathlib import Path
from capass_core.paths import AppPaths
from capass_core.systemd import UNIT_MARKER, render_unit


def test_unit_runs_the_wrapper_as_the_service_user():
    paths = AppPaths(root=Path("/opt/capass"))
    unit = render_unit(paths, "capass", "capass", Path("/opt/capass/logs"), Path("/opt/capass/data"), "CaPass tool server receiver", "serve")
    assert unit.startswith(UNIT_MARKER)  # capass init が作ったことを、後で確認できる
    assert "Description=CaPass tool server receiver" in unit
    assert "User=capass" in unit and "Group=capass" in unit
    assert "ExecStart=/opt/capass/bin/capass serve" in unit
    assert "WorkingDirectory=/opt/capass" in unit
    assert "ReadWritePaths=/opt/capass/logs /opt/capass/data" in unit  # 書き込めるのは、ログとデータだけ
    assert "NoNewPrivileges=true" in unit and "ProtectSystem=strict" in unit
    assert "WantedBy=multi-user.target" in unit
    assert "{" not in unit and "}" not in unit  # 置き換え漏れが無い


def test_unit_uses_custom_directories_user_and_command():
    unit = render_unit(AppPaths(root=Path("/opt/capass")), "svc", "svcgrp", Path("/var/log/capass"), Path("/var/lib/capass"), "CaPass server", "serve --workers 2")
    assert "User=svc" in unit and "Group=svcgrp" in unit
    assert "ReadWritePaths=/var/log/capass /var/lib/capass" in unit
    assert "ExecStart=/opt/capass/bin/capass serve --workers 2" in unit

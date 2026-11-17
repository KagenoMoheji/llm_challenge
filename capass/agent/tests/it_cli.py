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
from capass_core.cli.main import main
from capass_core.testing import make_context


def _only_agent(name):
    return object() if name == "capass_agent" else None


def test_agent_mode_commands_are_not_implemented_yet(tmp_path, capsys):
    ctx = make_context(tmp_path)
    assert main(["init"], context=ctx, find_spec=_only_agent) == 9  # capass_agent.cli は、まだ registerを持たない
    assert "実装されていません" in capsys.readouterr().err
    assert not ctx.paths.root.exists()  # 何も作らない

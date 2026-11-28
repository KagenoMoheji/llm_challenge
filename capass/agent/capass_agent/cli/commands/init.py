import os
import inspect
import sys
import time
import traceback
PYPATH = os.path.dirname(os.path.abspath(inspect.getfile(inspect.currentframe())))
MODNAME = os.path.splitext(os.path.basename(inspect.getfile(inspect.currentframe())))[0]

# その他のモジュールやROOTPATHのディレクトリ起点の相対パスでのimport
"""`capass init`(AIエージェント)。まだ実装していない。
共通の部品(capass_core.cli.common.init_steps など)を、組み合わせて、このモードの手順(run_init)を書く。
(サービスファイルを作るか、など、手順は、モードごとに違う。)"""

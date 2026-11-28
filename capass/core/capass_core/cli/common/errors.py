import os
import inspect
import sys
import time
import traceback
PYPATH = os.path.dirname(os.path.abspath(inspect.getfile(inspect.currentframe())))
MODNAME = os.path.splitext(os.path.basename(inspect.getfile(inspect.currentframe())))[0]

# その他のモジュールやROOTPATHのディレクトリ起点の相対パスでのimport


class CapassCliError(Exception):
    """CLIの業務エラーの基底クラス。メッセージを表示して、exit_codeで終了する(cli/main.py)。"""

    exit_code = 1


class InvalidOptionError(CapassCliError):
    """オプションの値が不正(argparseの、使い方の誤りと同じ、終了コード2)。"""

    exit_code = 2


class RoleConflictError(CapassCliError):
    """このサーバに、すでに別のモード(AIエージェント / ツールサーバ / CaPassサーバ)が設定されている。"""

    exit_code = 3


class AlreadyInitializedError(CapassCliError):
    """このサーバは、すでに初期化されている。"""

    exit_code = 4


class AppDirectoryError(CapassCliError):
    """アプリディレクトリ(/opt/capass)や、その中のファイルを、作成・使用できない。"""

    exit_code = 5


class NotRootError(CapassCliError):
    """root権限で、実行されていない。"""

    exit_code = 6


class UnsupportedEnvironmentError(CapassCliError):
    """サポートしていない環境(Linux + systemd以外など)。"""

    exit_code = 7


class SystemCommandError(CapassCliError):
    """OSのコマンド(useradd など)が、失敗した。"""

    exit_code = 8


class ModeNotImplementedError(CapassCliError):
    """インストール済みのモードの、コマンドが、まだ実装されていない。"""

    exit_code = 9


class ModeNotInstalledError(CapassCliError):
    """モード(server / toolserver / agent)が、インストールされていない。"""

    exit_code = 10


class MultipleModesInstalledError(CapassCliError):
    """2つ以上のモードが、同じPython環境に、インストールされている(同時に使えない)。"""

    exit_code = 11

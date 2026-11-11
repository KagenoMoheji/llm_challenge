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
import argparse
from capass_cli import __version__
from capass_cli.commands import toolserver
from capass_cli.common.errors import CapassCliError


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="capass", description="CaPassクライアント(CLI)")
    parser.add_argument("--version", action="version", version=f"capass {__version__}")
    parser.add_argument("--home", help="CaPassクライアントのホームディレクトリ(鍵などを置く場所)。省略時は、環境変数 CAPASS_HOME、なければ ~/.capass")
    subparsers = parser.add_subparsers(dest="group", required=True, metavar="<コマンド>")
    toolserver.register(subparsers)
    return parser


def main(argv: list[str] | None = None) -> int:
    """CLIのエントリポイント。終了コード: 0=成功、1=エラー、2=使い方の誤り、3=役割の同居、4=鍵が存在する、5=ホームディレクトリを使えない。"""
    args = build_parser().parse_args(argv)
    try:
        return args.func(args)
    except CapassCliError as e:
        print(f"エラー: {e}", file=sys.stderr)
        return e.exit_code


def run() -> None:
    sys.exit(main())


if __name__ == "__main__":
    run()

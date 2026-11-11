import os
import inspect
import sys
import time
import traceback
PYPATH = os.path.dirname(os.path.abspath(inspect.getfile(inspect.currentframe())))
MODNAME = os.path.splitext(os.path.basename(inspect.getfile(inspect.currentframe())))[0]

# その他のモジュールやROOTPATHのディレクトリ起点の相対パスでのimport
import argparse
from capass_cli.common.keys import setup_role_keys
from capass_cli.common.paths import resolve_home
from capass_cli.common.roles import ROLE_TOOLSERVER


def register(subparsers: argparse._SubParsersAction) -> None:
    """`capass toolserver ...` のサブコマンドを登録する。"""
    parser = subparsers.add_parser("toolserver", help="ツールサーバ側の操作")
    sub = parser.add_subparsers(dest="toolserver_command", required=True, metavar="<サブコマンド>")

    keygen = sub.add_parser(
        "keygen",
        help="ツールサーバの公開鍵と秘密鍵を作る",
        description=(
            "ツールサーバの、Ed25519の鍵ペアを作ります。秘密鍵は、このサーバだけで保管してください(他へコピーしない)。"
            "公開鍵を、CaPassサーバへの登録(toolservers/register)に使います。"
            "このサーバが、AIエージェントとして設定されている場合は、エラーになります(AIエージェントとツールサーバの同居の防止)。"
        ),
    )
    keygen.add_argument("--force", action="store_true", help="鍵が存在する場合に、上書きして作り直す(CaPassサーバに登録した公開鍵は、使えなくなります)")
    keygen.set_defaults(func=cmd_keygen)


def cmd_keygen(args: argparse.Namespace) -> int:
    home = resolve_home(args.home)
    info = setup_role_keys(home, ROLE_TOOLSERVER, force=args.force)
    print("ツールサーバの鍵ペアを作成しました。")
    print(f"  秘密鍵: {info.private_key_path}  (このサーバだけで保管してください。他へコピーしないでください)")
    print(f"  公開鍵: {info.public_key_path}")
    print(f"  公開鍵(Base64): {info.public_key_b64}")
    print(f"  フィンガープリント: {info.fingerprint}")
    print("")
    print("公開鍵を、CaPassサーバへの登録(toolservers/register)に使います。CaPassサーバ管理者には、承認前の確認のために、")
    print("公開鍵とフィンガープリントを、別の経路(メール、チャットなど)でも伝えてください。")
    return 0

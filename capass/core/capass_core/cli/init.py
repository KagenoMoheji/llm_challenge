import os
import inspect
import sys
import time
import traceback
PYPATH = os.path.dirname(os.path.abspath(inspect.getfile(inspect.currentframe())))
MODNAME = os.path.splitext(os.path.basename(inspect.getfile(inspect.currentframe())))[0]

# その他のモジュールやROOTPATHのディレクトリ起点の相対パスでのimport
import argparse
from pathlib import Path
from capass_core.init_steps import InitOptions, InitResult, InitSpec, run_init
from capass_core.modes import MODE_LABELS
from capass_core.paths import DEFAULT_PORT, DEFAULT_USER


def register_init(subparsers: argparse._SubParsersAction, spec: InitSpec) -> None:
    """`capass init` を登録する。常駐プロセスを持つモード(toolserver、server)の、モードのパッケージが、自分のInitSpecを渡して呼ぶ。"""
    label = MODE_LABELS.get(spec.mode, spec.mode)
    parser = subparsers.add_parser(
        "init",
        help=f"サーバの初期導入(root権限が必要) [モード: {spec.mode}]",
        description=(
            f"このサーバを、「{label}」として、初期導入します(root権限が必要)。アプリディレクトリ(/opt/capass)は固定です。\n"
            "  1. 実行ユーザ/グループの作成\n"
            "  2. アプリディレクトリ(bin / confs / keys / logs / data)の作成\n"
            "  3. 実行ファイルを bin に配置\n"
            "  4. 鍵(公開鍵・秘密鍵)を keys に作成(権限は厳しく)\n"
            "  5. systemdのサービスファイル(/etc/systemd/system/capass.service)の作成\n"
            "  6. CLIのバージョンと設定を confs に記録\n"
            "別のモードが設定済みのサーバでは、エラーになります(AIエージェントとツールサーバの同居の防止)。"
        ),
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    parser.add_argument("--user", default=DEFAULT_USER, help=f"実行ユーザ名(グループは、同じ名前)。存在しなければ作成する(既定: {DEFAULT_USER})")
    parser.add_argument("--log-dir", type=Path, help="ログディレクトリ(既定: {アプリディレクトリ}/logs)")
    parser.add_argument("--data-dir", type=Path, help="一時データディレクトリ(既定: {アプリディレクトリ}/data)")
    parser.add_argument("--port", type=int, default=DEFAULT_PORT, help=f"CaPassサーバからの、依頼を待ち受ける、常駐のポート番号(既定: {DEFAULT_PORT})")
    parser.set_defaults(func=lambda args: cmd_init(args, spec))


def cmd_init(args: argparse.Namespace, spec: InitSpec) -> int:
    options = InitOptions(user=args.user, port=args.port, log_dir=args.log_dir, data_dir=args.data_dir)
    result = run_init(spec, options, args.context)
    _print_result(result, spec)
    return 0


def _print_result(r: InitResult, spec: InitSpec) -> None:
    label = MODE_LABELS.get(r.mode, r.mode)
    print(f"{label}の初期導入が完了しました。")
    print(f"  実行ユーザ: {r.user}:{r.group}" + ("(新しく作成しました)" if r.user_created else "(既存のユーザを使います)"))
    print(f"  待ち受けポート: {r.port}")
    print(f"  ログディレクトリ: {r.log_dir}")
    print(f"  データディレクトリ: {r.data_dir}")
    print(f"  実行ファイル: {r.wrapper_path}")
    print(f"  設定ファイル: {r.conf_path}")
    print(f"  サービスファイル: {r.unit_path}")
    print(f"  秘密鍵: {r.keys.private_key_path}  (実行ユーザだけが読めます。他へコピーしないでください)" + ("  ※既存の鍵を使いました" if r.keys.reused else ""))
    print(f"  公開鍵: {r.keys.public_key_path}")
    print(f"  公開鍵(Base64): {r.keys.public_key_b64}")
    print(f"  フィンガープリント: {r.keys.fingerprint}")
    print("")
    print("次の手順:")
    print("  1. 公開鍵を、CaPassサーバへの登録(toolservers/register)に使います。CaPassサーバ管理者には、承認前の確認のために、")
    print("     公開鍵とフィンガープリントを、別の経路(メール、チャットなど)でも伝えてください。")
    print("  2. systemdに、サービスファイルを読み込ませます: systemctl daemon-reload")
    print(f"  3. {spec.daemon_label}(capass {spec.exec_args})は、まだ実装されていません。実装後に、systemctl enable --now capass で、常駐させます。")
    print(f"  4. ファイアウォールで、ポート {r.port} への接続元を、CaPassサーバのIPアドレスに限ってください(ポートは、init では開けません)。")

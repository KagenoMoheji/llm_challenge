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
from capass_core import __version__
from capass_core.cli.common.conf import render_conf
from capass_core.cli.common.init_steps import (
    InitOptions,
    InitResult,
    check_not_initialized,
    check_root,
    check_systemd_dir,
    check_unit_file_is_ours,
    create_app_dirs,
    ensure_service_user,
    validate_options,
    write_file,
    write_wrapper,
)
from capass_core.cli.common.keys import create_key_files
from capass_core.cli.common.modes import MODE_LABELS, MODE_TOOLSERVER, ensure_host_mode
from capass_core.cli.common.paths import DEFAULT_PORT, DEFAULT_USER, SERVICE_NAME
from capass_core.cli.common.system import SystemContext
from capass_core.cli.common.systemd import render_unit

MODE = MODE_TOOLSERVER
UNIT_DESCRIPTION = "CaPass tool server receiver"
UNIT_EXEC_ARGS = "serve"  # サービスが実行するコマンド(受け口。未実装)


def register(subparsers: argparse._SubParsersAction) -> None:
    """`capass init`(ツールサーバ)を登録する。"""
    parser = subparsers.add_parser(
        "init",
        help=f"サーバの初期導入(root権限が必要) [モード: {MODE}]",
        description=(
            f"このサーバを、「{MODE_LABELS[MODE]}」として、初期導入します(root権限が必要)。アプリディレクトリ(/opt/capass)は固定です。\n"
            "  1. 実行ユーザ/グループの作成\n"
            "  2. アプリディレクトリ(bin / confs / keys / logs / data)の作成\n"
            "  3. 実行ファイルを bin に配置\n"
            "  4. 鍵(公開鍵・秘密鍵)を keys に作成(権限は厳しく)\n"
            "  5. systemdのサービスファイル(/etc/systemd/system/capass.service)の作成\n"
            "  6. CLIのバージョンと設定を confs に記録\n"
            "別のモードが設定済み、または別のモードの常駐プロセスが稼働中のサーバでは、エラーになります(AIエージェントとツールサーバの同居の防止)。"
        ),
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    parser.add_argument("--user", default=DEFAULT_USER, help=f"実行ユーザ名(グループは、同じ名前)。存在しなければ作成する(既定: {DEFAULT_USER})")
    parser.add_argument("--log-dir", type=Path, help="ログディレクトリ(既定: {アプリディレクトリ}/logs)")
    parser.add_argument("--data-dir", type=Path, help="一時データディレクトリ(既定: {アプリディレクトリ}/data)")
    parser.add_argument("--port", type=int, default=DEFAULT_PORT, help=f"CaPassサーバからの、ツール実行の依頼を待ち受ける、常駐のポート番号(既定: {DEFAULT_PORT})")
    parser.set_defaults(func=cmd_init)


def cmd_init(args: argparse.Namespace) -> int:
    options = InitOptions(user=args.user, port=args.port, log_dir=args.log_dir, data_dir=args.data_dir)
    _print_result(run_init(options, args.context))
    return 0


def run_init(options: InitOptions, context: SystemContext) -> InitResult:
    """ツールサーバの、初期導入の手順。共通の部品(capass_core.cli.common.init_steps など)を、組み合わせて書く。
    ツールサーバは、受け口の常駐プロセス(systemdのサービス)を持つので、サービスファイルも作る。
    確認は、最初に全て行い、失敗したら、何も変更しない。設定ファイル(初期化済みの目印)は、最後に作るので、途中で失敗しても、再実行できる。"""
    paths, ops = context.paths, context.ops

    # ---- 1. 確認(何も変更しない) ----
    check_root(context)
    check_systemd_dir(context)
    options = validate_options(options, paths)
    check_not_initialized(paths, MODE)
    ensure_host_mode(paths, MODE, ops)  # 別のモードの設定、鍵、稼働中のプロセスがあれば、RoleConflictError
    unit_path = context.systemd_dir / SERVICE_NAME
    check_unit_file_is_ours(unit_path)

    # ---- 2. 実行ユーザ/グループ、ディレクトリ、実行ファイル ----
    group, user_created = ensure_service_user(context, options.user)
    create_app_dirs(context, options.user, group, options.log_dir, options.data_dir)
    wrapper_path = write_wrapper(context)

    # ---- 3. 鍵(既存の鍵があれば、そのまま使う) ----
    keys = create_key_files(paths, MODE, ops, options.user, group)

    # ---- 4. systemdのサービスファイル ----
    unit = render_unit(paths, options.user, group, options.log_dir, options.data_dir, UNIT_DESCRIPTION, UNIT_EXEC_ARGS)
    write_file(context, unit_path, unit, 0o644, "root", "root")

    # ---- 5. 設定ファイル(最後に作る。これが、初期化済みの目印) ----
    conf_text = render_conf(MODE, __version__, options.user, group, options.port, options.log_dir, options.data_dir, paths)
    write_file(context, paths.conf_file, conf_text, 0o644, "root", "root")

    return InitResult(MODE, options.user, group, user_created, options.port, options.log_dir, options.data_dir, wrapper_path, paths.conf_file, unit_path, keys)


def _print_result(r: InitResult) -> None:
    print(f"{MODE_LABELS[r.mode]}の初期導入が完了しました。")
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
    print(f"  3. 受け口(capass {UNIT_EXEC_ARGS})は、まだ実装されていません。実装後に、systemctl enable --now capass で、常駐させます。")
    print(f"  4. ファイアウォールで、ポート {r.port} への接続元を、CaPassサーバのIPアドレスに限ってください(ポートは、init では開けません)。")

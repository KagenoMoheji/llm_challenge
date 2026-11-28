import os
import inspect
import sys
import time
import traceback
PYPATH = os.path.dirname(os.path.abspath(inspect.getfile(inspect.currentframe())))
ROOTPATH = os.path.abspath(f"{PYPATH}/../..")
MODNAME = os.path.splitext(os.path.basename(inspect.getfile(inspect.currentframe())))[0]
# 以下のROOTPATHでimportの起点を指定
sys.path.append(ROOTPATH)

# その他のモジュールやROOTPATHのディレクトリ起点の相対パスでのimport
import argparse
import importlib
from capass_core import __version__
from capass_core.cli.common.errors import CapassCliError, ModeNotImplementedError
from capass_core.cli.common.modes import (
    MODE_LABELS,
    MODE_STATUS,
    MODES,
    describe_current_mode,
    detect_installed_modes,
    ensure_host_mode,
    ensure_single_mode,
    install_hint,
    package_name,
)
from capass_core.cli.common.system import SystemContext

HELP_EPILOG = """モード(このサーバの役割。1つのサーバに、1つだけ設定できます。モードごとに、別のパッケージをインストールします):
{modes}

インストール済みのモード: {installed}
このサーバのモード(初期化済み): {current_mode}{state}"""


def load_mode_cli(mode: str):
    """モードのパッケージの、CLI(capass_<モード>.cli)を、必要になったときに、importする(遅延import)。
    CLIがまだ無いモード(server など)は、Noneを返す。パッケージの中のimportエラーは、隠さずに、そのまま投げる。"""
    name = f"{package_name(mode)}.cli"
    try:
        return importlib.import_module(name)
    except ModuleNotFoundError as e:
        if e.name == name:
            return None
        raise


def _describe_installed(installed: set[str]) -> str:
    if not installed:
        return "なし"
    names = ", ".join(sorted(installed))
    return names if len(installed) == 1 else f"{names}(同時に使えません)"


def build_parser(context: SystemContext, installed: set[str], mode_error: CapassCliError | None = None) -> argparse.ArgumentParser:
    modes = "\n".join(f"  {m:<11} {MODE_LABELS[m]}  ... {MODE_STATUS[m]}  ({install_hint(m)})" for m in MODES)
    state = f"\n\nこのサーバでは、コマンドを使えません: {str(mode_error).splitlines()[0]}" if mode_error is not None else ""
    return argparse.ArgumentParser(
        prog="capass",
        description="CaPass CLI",
        epilog=HELP_EPILOG.format(modes=modes, installed=_describe_installed(installed), current_mode=describe_current_mode(context.paths), state=state),
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )


def main(argv: list[str] | None = None, context: SystemContext | None = None, find_spec=None, load_cli=None) -> int:
    """CLIのエントリポイント。インストール済みのモードを探して(find_spec)、そのモードのコマンドだけを登録する(load_cli)。
    確認の順序: (1) 同じPython環境に、モードのパッケージが、ちょうど1つか(ensure_single_mode)、
    (2) このサーバに、別のモードの設定や常駐プロセスが無いか(ensure_host_mode: /opt/capass の設定ファイルと鍵のファイル名、systemd、ps)。
    contextは、システムの場所とOSの操作、find_spec / load_cli は、モードの検出と読み込みを、テストで差し替えるための引数(本番は、全て省略)。
    終了コード: 0=成功、1=エラー、2=使い方の誤り・オプションの不正、3=モードの同居(サーバ)、4=初期化済み、5=ディレクトリ・ファイルを使えない、
    6=root権限が必要、7=サポート外の環境、8=OSのコマンドの失敗、9=コマンドが未実装のモード、10=モードがインストールされていない、
    11=2つ以上のモードがインストールされている。"""
    context = context or SystemContext()
    load_cli = load_cli or load_mode_cli
    installed = detect_installed_modes(find_spec)
    mode, mode_cli, mode_error = None, None, None
    try:
        mode = ensure_single_mode(installed)
        ensure_host_mode(context.paths, mode, context.ops)
        mode_cli = load_cli(mode)
        if mode_cli is not None and not hasattr(mode_cli, "register"):
            mode_cli = None  # CLIのパッケージはあるが、コマンドの登録が、まだ無い
    except CapassCliError as e:
        mode_error = e
    parser = build_parser(context, installed, mode_error)
    parser.add_argument("--version", action="version", version=f"capass {__version__}")
    try:
        if mode_cli is None:
            parser.parse_known_args(argv)  # --help と --version は、ここで表示して終了する
            raise mode_error or ModeNotImplementedError(f"モード「{mode}」のコマンドは、まだ実装されていません(実装状況: {MODE_STATUS[mode]})。")
        subparsers = parser.add_subparsers(dest="command", required=True, metavar="<コマンド>")
        mode_cli.register(subparsers, context)
        args = parser.parse_args(argv)
        args.context = context
        return args.func(args)
    except CapassCliError as e:
        print(f"エラー: {e}", file=sys.stderr)
        return e.exit_code


def run() -> None:
    sys.exit(main())


if __name__ == "__main__":
    run()

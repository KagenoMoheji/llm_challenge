import os
import inspect
import sys
import time
import traceback
PYPATH = os.path.dirname(os.path.abspath(inspect.getfile(inspect.currentframe())))
MODNAME = os.path.splitext(os.path.basename(inspect.getfile(inspect.currentframe())))[0]

# その他のモジュールやROOTPATHのディレクトリ起点の相対パスでのimport
from capass_core.conf import read_installed_mode
from capass_core.errors import AppDirectoryError, RoleConflictError
from capass_core.modes import MODE_LABELS, MODES
from capass_core.paths import AppPaths


def _label(mode: str) -> str:
    return MODE_LABELS.get(mode, mode)


def detect_role_evidence(paths: AppPaths) -> dict[str, list[str]]:
    """このサーバに設定済みのモードと、その根拠を返す。根拠は、(1) 設定ファイルのモード、(2) 鍵ファイルのファイル名(<モード>.key / <モード>.pub)。"""
    evidence: dict[str, list[str]] = {}
    mode = read_installed_mode(paths)
    if mode:
        evidence.setdefault(mode, []).append(f"設定ファイル {paths.conf_file}")
    for candidate in MODES:
        for key_path in (paths.private_key_path(candidate), paths.public_key_path(candidate)):
            if key_path.exists():
                evidence.setdefault(candidate, []).append(f"鍵ファイル {key_path}")
    return evidence


def ensure_role_available(paths: AppPaths, mode: str) -> None:
    """このサーバで、modeを設定してよいかを確認する。すでに別のモードが設定されていれば、RoleConflictError。
    AIエージェントとツールサーバ(とCaPassサーバ)を、同じサーバに同居させないための、ガード。
    AIエージェントは、プロンプトインジェクションなどで、意図しない操作をする恐れがある。同じサーバにツールサーバがあると、
    ツールサーバの秘密鍵や認証情報に、直接アクセスでき、CaPassサーバの承認と署名の確認を、迂回できてしまう。
    アプリディレクトリは、サーバ全体で1つ(/opt/capass)に固定しているので、ユーザや、Python環境(venv)が違っても、同居を検出できる。
    なお、これは、設定ミスを防ぐ仕組みで、悪意のある操作(ファイルの削除など)は、防げない。"""
    others = {m: e for m, e in detect_role_evidence(paths).items() if m != mode}
    if not others:
        return
    existing = "、".join(f"「{_label(m)}」({'、'.join(e)})" for m, e in sorted(others.items()))
    raise RoleConflictError(
        f"このサーバは、すでに{existing}として設定されています。「{_label(mode)}」のモードを、同じサーバに同居させることはできません。\n"
        "  AIエージェントとツールサーバが同居すると、AIエージェントが、ツールサーバの秘密鍵や認証情報に直接アクセスでき、CaPassサーバの承認と署名の確認を、迂回できてしまうためです。\n"
        "  別のサーバで設定してください(初期化を取り消す機能は、まだありません)。"
    )


def describe_current_mode(paths: AppPaths) -> str:
    """`capass --help` に表示する、このサーバの、初期化済みのモード。"""
    try:
        mode = read_installed_mode(paths)
    except AppDirectoryError:
        return "不明(設定ファイルを読めません)"
    if mode is None:
        return "未初期化(capass init で、初期化します)"
    return f"{mode}({_label(mode)}。{paths.root} で初期化済み)"

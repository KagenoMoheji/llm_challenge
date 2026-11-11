import os
import inspect
import sys
import time
import traceback
PYPATH = os.path.dirname(os.path.abspath(inspect.getfile(inspect.currentframe())))
MODNAME = os.path.splitext(os.path.basename(inspect.getfile(inspect.currentframe())))[0]

# その他のモジュールやROOTPATHのディレクトリ起点の相対パスでのimport
from pathlib import Path
from capass_cli.common.errors import RoleConflictError
from capass_cli.common.fileio import write_atomic
from capass_cli.common.paths import role_dir

ROLE_AGENT = "agent"  # AIエージェントの作業環境
ROLE_TOOLSERVER = "toolserver"  # ツールサーバ
ROLE_SERVER = "server"  # CaPassサーバ
ROLES = (ROLE_AGENT, ROLE_TOOLSERVER, ROLE_SERVER)
ROLE_LABELS = {ROLE_AGENT: "AIエージェント", ROLE_TOOLSERVER: "ツールサーバ", ROLE_SERVER: "CaPassサーバ"}
ROLE_MARKER_FILENAME = "role"  # ホーム直下の、このサーバの役割を書いたファイル(最初の鍵の作成のときに書かれる)


def _label(role: str) -> str:
    return ROLE_LABELS.get(role, role)


def detect_role_evidence(home: Path) -> dict[str, list[str]]:
    """このサーバに設定済みの役割と、その根拠(役割のディレクトリ、役割ファイル)を返す。"""
    evidence: dict[str, list[str]] = {}
    for role in ROLES:
        directory = role_dir(home, role)
        if directory.exists():
            evidence.setdefault(role, []).append(f"ディレクトリ {directory}")
    marker = home / ROLE_MARKER_FILENAME
    if marker.is_file():
        text = marker.read_text(encoding="utf-8").strip()
        if text:  # 未知の役割名(手で書き換えられた場合など)も、同居できない役割として扱う
            evidence.setdefault(text, []).append(f"役割ファイル {marker}")
    return evidence


def ensure_role_available(home: Path, role: str) -> None:
    """このサーバで、roleの役割を設定してよいかを確認する。すでに別の役割が設定されていれば、RoleConflictError。
    AIエージェントとツールサーバ(とCaPassサーバ)を、同じサーバに同居させないための、ガード。
    AIエージェントは、プロンプトインジェクションなどで、意図しない操作をする恐れがある。同じサーバにツールサーバがあると、
    ツールサーバの秘密鍵や認証情報に、直接アクセスでき、CaPassサーバの承認と署名の確認を、迂回できてしまう。
    なお、これは、設定ミスを防ぐ仕組みで、悪意のある操作(ファイルの削除など)は、防げない。"""
    others = {r: e for r, e in detect_role_evidence(home).items() if r != role}
    if not others:
        return
    existing = ", ".join(f"「{_label(r)}」({'、'.join(e)})" for r, e in sorted(others.items()))
    raise RoleConflictError(
        f"このサーバは、すでに{existing}として設定されています。「{_label(role)}」の役割を、同じサーバに同居させることはできません。\n"
        "  AIエージェントとツールサーバが同居すると、AIエージェントが、ツールサーバの秘密鍵や認証情報に直接アクセスでき、CaPassサーバの承認と署名の確認を、迂回できてしまうためです。\n"
        "  別のサーバで設定してください。開発・テストで、同じ端末で試す場合は、役割ごとに、別の CAPASS_HOME を指定してください"
        f"(例: CAPASS_HOME=/tmp/capass-{role} capass ...)。"
    )


def write_role_marker(home: Path, role: str) -> None:
    """このサーバの役割を、役割ファイルに書く(以降、別の役割の設定を、ensure_role_availableが拒否する)。"""
    write_atomic(home / ROLE_MARKER_FILENAME, role + "\n", 0o644)

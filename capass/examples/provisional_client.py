"""CaPassクライアント(CLI)が実装されるまでの暫定クライアント(開発・動作確認用)。

CLIの `keygen` / `regist` などの代わりに、CaPassサーバのRestAPIを、署名付きで直接呼び出す。
秘密鍵は環境変数で渡す(keygenで作ったBase64文字列)。サーバのURLは CAPASS_URL(省略時 http://127.0.0.1:8000)。

  python provisional_client.py keygen
  python provisional_client.py toolserver-register --name "社内ツールサーバA" \
      --exec-url https://toolserver.example.com/capass/exec --email you@example.com      # 環境変数 TOOL_SERVER_PRIVATE_KEY
  python provisional_client.py toolserver-approve  --toolserver-id 1                   # 環境変数 ADMIN_PRIVATE_KEY
  python provisional_client.py agent-register      --agent-id agent-1 --email you@example.com          # 環境変数 AGENT_PRIVATE_KEY
  python provisional_client.py agent-approve       --agent-id agent-1                  # 環境変数 ADMIN_PRIVATE_KEY
  # ツールサーバのリプレース(予約 → 切り替え → 切り戻し)
  python provisional_client.py toolserver-replace-reserve --toolserver-id 1 --new-public-key <新の公開鍵> --new-name "新ツールサーバ" --new-exec-url https://new.example.com/capass/exec --email you@example.com   # ADMIN_PRIVATE_KEY
  python provisional_client.py toolserver-replace-sign-old --toolserver-id 1 --new-public-key <新の公開鍵> > handoff.json   # 旧ツールサーバ: TOOL_SERVER_PRIVATE_KEY
  python provisional_client.py toolserver-replace-activate --toolserver-id 1 --handoff @handoff.json                       # 新ツールサーバ: TOOL_SERVER_PRIVATE_KEY
  python provisional_client.py toolserver-replace-rollback --toolserver-id 1                                               # 旧ツールサーバ: TOOL_SERVER_PRIVATE_KEY
  # ツール(ロール単位)の登録と、AIエージェントへの割り当て(申請 → 承認 / 取り消し)
  python provisional_client.py tool-add            --endpoint psql_manager --context "..." --params-schema @schema.json   # TOOL_SERVER_PRIVATE_KEY
  python provisional_client.py agent-grant         --agent-id agent-1 --endpoint psql_manager --email you@example.com     # AGENT_PRIVATE_KEY(申請)
  python provisional_client.py agent-grant-approve --agent-id agent-1 --endpoint psql_manager                             # ADMIN_PRIVATE_KEY(承認)
  python provisional_client.py agent-revoke        --agent-id agent-1 --endpoint psql_manager [--as toolserver]           # ADMIN_PRIVATE_KEY(または TOOL_SERVER_PRIVATE_KEY)
  python provisional_client.py tool-chtkn          --endpoint psql_manager              # TOOL_SERVER_PRIVATE_KEY(トークンの更新。割り当てられた全AIエージェントに反映)
  python provisional_client.py agent-tools         --agent-id agent-1                  # 環境変数 AGENT_PRIVATE_KEY(list executable の代用)
  python provisional_client.py agent-exec          --agent-id agent-1 \
      --endpoint psql_manager --params '{"sql": "SELECT 1"}'                           # 環境変数 AGENT_PRIVATE_KEY(exec の代用)
"""
import os
import inspect
import sys
import time
import traceback
PYPATH = os.path.dirname(os.path.abspath(inspect.getfile(inspect.currentframe())))
MODNAME = os.path.splitext(os.path.basename(inspect.getfile(inspect.currentframe())))[0]

# その他のモジュールやROOTPATHのディレクトリ起点の相対パスでのimport
# (このスクリプトはCaPassサーバのコードをimportしない単体スクリプトなので、ROOTPATHは使わない)
import argparse
import base64
import json
import secrets
import urllib.error
import urllib.parse
import urllib.request

from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey
from cryptography.hazmat.primitives.serialization import Encoding, NoEncryption, PrivateFormat, PublicFormat

CAPASS_URL = os.environ.get("CAPASS_URL", "http://127.0.0.1:8000")

# 署名メッセージのプレフィックス。サーバ(capass_server/common/signature.py)のSIGN_CONTEXT_*と一致させること
SIGN_CONTEXT_TOOLSERVER_REGISTER = b"capass-toolserver-register-v1\n"
SIGN_CONTEXT_TOOLSERVER_APPROVE = b"capass-toolserver-approve-v1\n"
SIGN_CONTEXT_TOOLSERVER_REPLACE_RESERVE = b"capass-toolserver-replace-reserve-v1\n"
SIGN_CONTEXT_TOOLSERVER_REPLACE_ACTIVATE_OLD = b"capass-toolserver-replace-activate-old-v1\n"
SIGN_CONTEXT_TOOLSERVER_REPLACE_ACTIVATE_NEW = b"capass-toolserver-replace-activate-new-v1\n"
SIGN_CONTEXT_TOOLSERVER_REPLACE_ROLLBACK = b"capass-toolserver-replace-rollback-v1\n"
SIGN_CONTEXT_AGENT_REGISTER = b"capass-agent-register-v1\n"
SIGN_CONTEXT_AGENT_APPROVE = b"capass-agent-approve-v1\n"
SIGN_CONTEXT_TOOL_ADDTOOL = b"capass-tool-addtool-v1\n"
SIGN_CONTEXT_TOOL_CHTKN = b"capass-tool-chtkn-v1\n"
SIGN_CONTEXT_AGENT_GRANT = b"capass-agent-grant-v1\n"
SIGN_CONTEXT_AGENT_GRANT_APPROVE = b"capass-agent-grant-approve-v1\n"
SIGN_CONTEXT_AGENT_REVOKE = b"capass-agent-revoke-v1\n"
SIGN_CONTEXT_AGENT_LISTTOOLS = b"capass-agent-listtools-v1\n"
SIGN_CONTEXT_AGENT_EXEC = b"capass-agent-exec-v1\n"


def _load_private_key(env_name: str) -> Ed25519PrivateKey:
    value = os.environ.get(env_name)
    if not value:
        sys.exit(f"環境変数 {env_name} に、keygenで作った秘密鍵(Base64)を設定してください")
    return Ed25519PrivateKey.from_private_bytes(base64.b64decode(value))


def _public_key_b64(private_key: Ed25519PrivateKey) -> str:
    return base64.b64encode(private_key.public_key().public_bytes(Encoding.Raw, PublicFormat.Raw)).decode()


def _signed_body(private_key: Ed25519PrivateKey, sign_context: bytes, fields: dict, path_params: dict | None = None) -> dict:
    """ボディを作って署名する。署名対象 = signature以外の全フィールド + URLパスのパラメータ(正規化JSON)。"""
    body = {**fields, "signed_at": int(time.time())}
    payload = {**body, **(path_params or {})}
    canonical = json.dumps(payload, sort_keys=True, separators=(",", ":"), ensure_ascii=False).encode("utf-8")
    body["signature"] = base64.b64encode(private_key.sign(sign_context + canonical)).decode()
    return body


def _post(path: str, body: dict) -> None:
    req = urllib.request.Request(
        f"{CAPASS_URL}{path}",
        data=json.dumps(body, ensure_ascii=False).encode("utf-8"),
        headers={"Content-Type": "application/json"},
        method="POST",
    )
    try:
        with urllib.request.urlopen(req) as res:
            print(res.status, res.read().decode("utf-8"))
    except urllib.error.HTTPError as e:
        print(e.code, e.read().decode("utf-8"))


def _get(path: str, headers: dict) -> None:
    req = urllib.request.Request(f"{CAPASS_URL}{path}", headers=headers, method="GET")
    try:
        with urllib.request.urlopen(req) as res:
            print(res.status, res.read().decode("utf-8"))
    except urllib.error.HTTPError as e:
        print(e.code, e.read().decode("utf-8"))


def _load_json_object(value: str, option: str) -> dict:
    """JSONオブジェクトの文字列、または @ファイルパス(ファイルの中身がJSON)を読み込む。"""
    text = open(value[1:], encoding="utf-8").read() if value.startswith("@") else value
    obj = json.loads(text)
    if not isinstance(obj, dict):
        sys.exit(f"{option} はJSONオブジェクトで指定してください")
    return obj


def cmd_keygen(_: argparse.Namespace) -> None:
    priv = Ed25519PrivateKey.generate()
    print("PRIVATE:", base64.b64encode(priv.private_bytes(Encoding.Raw, PrivateFormat.Raw, NoEncryption())).decode())
    print("PUBLIC :", _public_key_b64(priv))


def build_toolserver_register(priv: Ed25519PrivateKey, name: str, exec_url: str, email: str) -> tuple[str, dict]:
    fields = {"tool_server_public_key": _public_key_b64(priv), "tool_server_name": name, "tool_server_exec_url": exec_url, "applicant_email": email}
    return "/api/v1/toolservers/register", _signed_body(priv, SIGN_CONTEXT_TOOLSERVER_REGISTER, fields)


def build_toolserver_approve(admin: Ed25519PrivateKey, toolserver_id: int) -> tuple[str, dict]:
    fields = {"admin_public_key": _public_key_b64(admin)}
    body = _signed_body(admin, SIGN_CONTEXT_TOOLSERVER_APPROVE, fields, {"toolserver_id": toolserver_id})
    return f"/api/v1/toolservers/{toolserver_id}/approve", body


def build_agent_register(priv: Ed25519PrivateKey, agent_id: str, email: str) -> tuple[str, dict]:
    fields = {"agent_id": agent_id, "agent_public_key": _public_key_b64(priv), "applicant_email": email}
    return "/api/v1/agents/register", _signed_body(priv, SIGN_CONTEXT_AGENT_REGISTER, fields)


def build_agent_approve(admin: Ed25519PrivateKey, agent_id: str) -> tuple[str, dict]:
    fields = {"admin_public_key": _public_key_b64(admin)}
    body = _signed_body(admin, SIGN_CONTEXT_AGENT_APPROVE, fields, {"agent_id": agent_id})
    return f"/api/v1/agents/{urllib.parse.quote(agent_id, safe='')}/approve", body


def _sign_canonical(priv: Ed25519PrivateKey, sign_context: bytes, payload: dict) -> str:
    canonical = json.dumps(payload, sort_keys=True, separators=(",", ":"), ensure_ascii=False).encode("utf-8")
    return base64.b64encode(priv.sign(sign_context + canonical)).decode()


def build_replace_reserve(admin: Ed25519PrivateKey, toolserver_id: int, new_public_key: str, new_name: str, new_exec_url: str, email: str) -> tuple[str, dict]:
    fields = {
        "admin_public_key": _public_key_b64(admin),
        "new_tool_server_public_key": new_public_key,
        "new_tool_server_name": new_name,
        "new_tool_server_exec_url": new_exec_url,
        "applicant_email": email,
    }
    return f"/api/v1/toolservers/{toolserver_id}/replace/reserve", _signed_body(admin, SIGN_CONTEXT_TOOLSERVER_REPLACE_RESERVE, fields, {"toolserver_id": toolserver_id})


def build_replace_handoff(old_priv: Ed25519PrivateKey, toolserver_id: int, new_public_key: str) -> dict:
    """旧ツールサーバが、切り替え(activate)の署名を作る。新ツールサーバへ渡す(handoff)。署名時刻は、新ツールサーバの署名にも使う。"""
    signed_at = int(time.time())
    payload = {"toolserver_id": toolserver_id, "old_tool_server_public_key": _public_key_b64(old_priv), "new_tool_server_public_key": new_public_key, "signed_at": signed_at}
    return {
        "old_tool_server_public_key": payload["old_tool_server_public_key"],
        "new_tool_server_public_key": new_public_key,
        "signed_at": signed_at,
        "signature": _sign_canonical(old_priv, SIGN_CONTEXT_TOOLSERVER_REPLACE_ACTIVATE_OLD, payload),
    }


def build_replace_activate(new_priv: Ed25519PrivateKey, toolserver_id: int, handoff: dict) -> tuple[str, dict]:
    """新ツールサーバが、handoffと同じ内容に署名して、切り替えのリクエストを作る。"""
    if handoff["new_tool_server_public_key"] != _public_key_b64(new_priv):
        sys.exit("handoff の new_tool_server_public_key が、この秘密鍵(新ツールサーバ)の公開鍵と、一致しません")
    payload = {
        "toolserver_id": toolserver_id,
        "old_tool_server_public_key": handoff["old_tool_server_public_key"],
        "new_tool_server_public_key": handoff["new_tool_server_public_key"],
        "signed_at": handoff["signed_at"],
    }
    body = {
        "new_tool_server_public_key": handoff["new_tool_server_public_key"],
        "signed_at": handoff["signed_at"],
        "signature": handoff["signature"],
        "new_key_signature": _sign_canonical(new_priv, SIGN_CONTEXT_TOOLSERVER_REPLACE_ACTIVATE_NEW, payload),
    }
    return f"/api/v1/toolservers/{toolserver_id}/replace/activate", body


def build_replace_rollback(old_priv: Ed25519PrivateKey, toolserver_id: int) -> tuple[str, dict]:
    """旧ツールサーバ(切り戻し先)が、自分の署名だけで、切り戻しのリクエストを作る。"""
    signed_at = int(time.time())
    payload = {"toolserver_id": toolserver_id, "tool_server_public_key": _public_key_b64(old_priv), "signed_at": signed_at}
    body = {"signed_at": signed_at, "signature": _sign_canonical(old_priv, SIGN_CONTEXT_TOOLSERVER_REPLACE_ROLLBACK, payload)}
    return f"/api/v1/toolservers/{toolserver_id}/replace/rollback", body


def build_tool_add(priv: Ed25519PrivateKey, endpoint: str, context: str, token: str, params_schema: dict) -> tuple[str, dict]:
    fields = {
        "tool_endpoint": endpoint,
        "context": context,
        "params_schema": params_schema,
        "tool_proxy_token": token,
        "tool_server_public_key": _public_key_b64(priv),
    }
    return "/api/v1/tools/addtool", _signed_body(priv, SIGN_CONTEXT_TOOL_ADDTOOL, fields)


def build_tool_chtkn(priv: Ed25519PrivateKey, endpoint: str, token: str) -> tuple[str, dict]:
    fields = {"tool_proxy_token": token, "tool_server_public_key": _public_key_b64(priv), "nonce": secrets.token_urlsafe(16)}  # nonceは、リクエストごとに必ず新しく作る
    body = _signed_body(priv, SIGN_CONTEXT_TOOL_CHTKN, fields, {"tool_endpoint": endpoint})
    return f"/api/v1/tools/{urllib.parse.quote(endpoint, safe='')}/chtkn", body


def build_agent_grant(priv: Ed25519PrivateKey, agent_id: str, endpoint: str, email: str) -> tuple[str, dict]:
    body = _signed_body(priv, SIGN_CONTEXT_AGENT_GRANT, {"applicant_email": email}, {"agent_id": agent_id, "tool_endpoint": endpoint})
    return f"/api/v1/agents/{urllib.parse.quote(agent_id, safe='')}/grant/{urllib.parse.quote(endpoint, safe='')}", body


def build_agent_grant_approve(admin: Ed25519PrivateKey, agent_id: str, endpoint: str) -> tuple[str, dict]:
    body = _signed_body(admin, SIGN_CONTEXT_AGENT_GRANT_APPROVE, {"admin_public_key": _public_key_b64(admin)}, {"agent_id": agent_id, "tool_endpoint": endpoint})
    return f"/api/v1/agents/{urllib.parse.quote(agent_id, safe='')}/grant/{urllib.parse.quote(endpoint, safe='')}/approve", body


def build_agent_revoke(signer: Ed25519PrivateKey, agent_id: str, endpoint: str) -> tuple[str, dict]:
    body = _signed_body(signer, SIGN_CONTEXT_AGENT_REVOKE, {"signer_public_key": _public_key_b64(signer)}, {"agent_id": agent_id, "tool_endpoint": endpoint})
    return f"/api/v1/agents/{urllib.parse.quote(agent_id, safe='')}/revoke/{urllib.parse.quote(endpoint, safe='')}", body


def build_agent_tools(priv: Ed25519PrivateKey, agent_id: str) -> tuple[str, dict]:
    """GETの署名はヘッダーで送る。署名対象は agent_id と signed_at。"""
    signed_at = int(time.time())
    canonical = json.dumps({"agent_id": agent_id, "signed_at": signed_at}, sort_keys=True, separators=(",", ":"), ensure_ascii=False).encode("utf-8")
    signature = base64.b64encode(priv.sign(SIGN_CONTEXT_AGENT_LISTTOOLS + canonical)).decode()
    headers = {"X-CaPass-Signed-At": str(signed_at), "X-CaPass-Signature": signature}
    return f"/api/v1/agents/{urllib.parse.quote(agent_id, safe='')}/tools", headers


def build_agent_exec(priv: Ed25519PrivateKey, agent_id: str, endpoint: str, params: dict) -> tuple[str, dict]:
    fields = {"params": params, "nonce": secrets.token_urlsafe(16)}  # nonceは、リクエストごとに必ず新しく作る(使い回すとリプレイとして拒否される)
    body = _signed_body(priv, SIGN_CONTEXT_AGENT_EXEC, fields, {"agent_id": agent_id, "tool_endpoint": endpoint})
    return f"/api/v1/agents/{urllib.parse.quote(agent_id, safe='')}/exec/{urllib.parse.quote(endpoint, safe='')}", body


def cmd_toolserver_register(a: argparse.Namespace) -> None:
    _post(*build_toolserver_register(_load_private_key("TOOL_SERVER_PRIVATE_KEY"), a.name, a.exec_url, a.email))


def cmd_toolserver_approve(a: argparse.Namespace) -> None:
    _post(*build_toolserver_approve(_load_private_key("ADMIN_PRIVATE_KEY"), a.toolserver_id))


def cmd_agent_register(a: argparse.Namespace) -> None:
    _post(*build_agent_register(_load_private_key("AGENT_PRIVATE_KEY"), a.agent_id, a.email))


def cmd_agent_approve(a: argparse.Namespace) -> None:
    _post(*build_agent_approve(_load_private_key("ADMIN_PRIVATE_KEY"), a.agent_id))


def cmd_toolserver_replace_reserve(a: argparse.Namespace) -> None:
    _post(*build_replace_reserve(_load_private_key("ADMIN_PRIVATE_KEY"), a.toolserver_id, a.new_public_key, a.new_name, a.new_exec_url, a.email))


def cmd_toolserver_replace_sign_old(a: argparse.Namespace) -> None:
    print(json.dumps(build_replace_handoff(_load_private_key("TOOL_SERVER_PRIVATE_KEY"), a.toolserver_id, a.new_public_key), ensure_ascii=False))
    print("# 上のJSONを、新ツールサーバへ渡してください(署名時刻から、数分以内に activate を実行すること)", file=sys.stderr)


def cmd_toolserver_replace_activate(a: argparse.Namespace) -> None:
    _post(*build_replace_activate(_load_private_key("TOOL_SERVER_PRIVATE_KEY"), a.toolserver_id, _load_json_object(a.handoff, "--handoff")))


def cmd_toolserver_replace_rollback(a: argparse.Namespace) -> None:
    _post(*build_replace_rollback(_load_private_key("TOOL_SERVER_PRIVATE_KEY"), a.toolserver_id))


def cmd_tool_add(a: argparse.Namespace) -> None:
    token = a.token or secrets.token_urlsafe(32)  # ツール代理トークン(ロール単位)。省略時は自動発行する
    print("tool_proxy_token(ツールサーバ側のDBに、[認証情報(ロール)/トークン]として保存すること):", token)
    _post(*build_tool_add(_load_private_key("TOOL_SERVER_PRIVATE_KEY"), a.endpoint, a.context, token, _load_json_object(a.params_schema, "--params-schema")))


def cmd_tool_chtkn(a: argparse.Namespace) -> None:
    token = a.token or secrets.token_urlsafe(32)  # 新しいツール代理トークン。省略時は自動発行する
    print("new tool_proxy_token(ツールサーバ側のDBに、先に保存しておくこと。更新が完了するまでは、古いトークンと両方で受け付けると安全):", token)
    _post(*build_tool_chtkn(_load_private_key("TOOL_SERVER_PRIVATE_KEY"), a.endpoint, token))


def cmd_agent_grant(a: argparse.Namespace) -> None:
    _post(*build_agent_grant(_load_private_key("AGENT_PRIVATE_KEY"), a.agent_id, a.endpoint, a.email))


def cmd_agent_grant_approve(a: argparse.Namespace) -> None:
    _post(*build_agent_grant_approve(_load_private_key("ADMIN_PRIVATE_KEY"), a.agent_id, a.endpoint))


def cmd_agent_revoke(a: argparse.Namespace) -> None:
    env_name = "ADMIN_PRIVATE_KEY" if a.as_signer == "admin" else "TOOL_SERVER_PRIVATE_KEY"
    _post(*build_agent_revoke(_load_private_key(env_name), a.agent_id, a.endpoint))


def cmd_agent_tools(a: argparse.Namespace) -> None:
    _get(*build_agent_tools(_load_private_key("AGENT_PRIVATE_KEY"), a.agent_id))


def cmd_agent_exec(a: argparse.Namespace) -> None:
    params = json.loads(a.params)
    if not isinstance(params, dict):
        sys.exit("--params はJSONオブジェクトで指定してください")
    _post(*build_agent_exec(_load_private_key("AGENT_PRIVATE_KEY"), a.agent_id, a.endpoint, params))


def main() -> None:
    parser = argparse.ArgumentParser(description="CaPass暫定クライアント(CLI実装までの代用)")
    sub = parser.add_subparsers(dest="command", required=True)

    sub.add_parser("keygen", help="Ed25519キーペアを作る").set_defaults(func=cmd_keygen)

    p = sub.add_parser("toolserver-register", help="ツールサーバ(公開鍵)の初回登録")
    p.add_argument("--name", required=True, help="ツールサーバの名称(管理者が承認時に識別するため)")
    p.add_argument("--exec-url", required=True, help="ツール実行の依頼先URL。CaPassサーバがここへ中継する(既定ではhttpsのみ)")
    p.add_argument("--email", required=True, help="申請者のメールアドレス(管理者が承認前に、申請内容の確認の連絡をするため)")
    p.set_defaults(func=cmd_toolserver_register)

    p = sub.add_parser("toolserver-approve", help="ツールサーバの登録承認(管理者)")
    p.add_argument("--toolserver-id", type=int, required=True)
    p.set_defaults(func=cmd_toolserver_approve)

    p = sub.add_parser("agent-register", help="AIエージェント(公開鍵)の初回登録")
    p.add_argument("--agent-id", required=True)
    p.add_argument("--email", required=True, help="申請者のメールアドレス(管理者が承認前に、申請内容の確認の連絡をするため)")
    p.set_defaults(func=cmd_agent_register)

    p = sub.add_parser("agent-approve", help="AIエージェントの登録承認(管理者)")
    p.add_argument("--agent-id", required=True)
    p.set_defaults(func=cmd_agent_approve)

    p = sub.add_parser("toolserver-replace-reserve", help="ツールサーバのリプレース(1/3): 新ツールサーバを、後継として予約する(管理者)")
    p.add_argument("--toolserver-id", type=int, required=True, help="置き換えられる(旧)ツールサーバのid")
    p.add_argument("--new-public-key", required=True, help="新ツールサーバの公開鍵")
    p.add_argument("--new-name", required=True, help="新ツールサーバの名称")
    p.add_argument("--new-exec-url", required=True, help="新ツールサーバの実行URL")
    p.add_argument("--email", required=True, help="リプレースを申告したツールサーバ管理者のメールアドレス")
    p.set_defaults(func=cmd_toolserver_replace_reserve)

    p = sub.add_parser("toolserver-replace-sign-old", help="ツールサーバのリプレース(2/3の準備): 旧ツールサーバで、切り替えの署名(handoff)を作る")
    p.add_argument("--toolserver-id", type=int, required=True, help="旧ツールサーバのid")
    p.add_argument("--new-public-key", required=True, help="新ツールサーバの公開鍵(予約済みのもの)")
    p.set_defaults(func=cmd_toolserver_replace_sign_old)

    p = sub.add_parser("toolserver-replace-activate", help="ツールサーバのリプレース(2/3): 新ツールサーバで、handoffに署名して、切り替えを実行する")
    p.add_argument("--toolserver-id", type=int, required=True, help="旧ツールサーバのid")
    p.add_argument("--handoff", required=True, help="旧ツールサーバが作ったhandoff(JSON文字列、または @ファイルパス)")
    p.set_defaults(func=cmd_toolserver_replace_activate)

    p = sub.add_parser("toolserver-replace-rollback", help="ツールサーバのリプレース(3/3): 旧ツールサーバへ、切り戻す")
    p.add_argument("--toolserver-id", type=int, required=True, help="切り戻し先の、旧ツールサーバのid")
    p.set_defaults(func=cmd_toolserver_replace_rollback)

    p = sub.add_parser("tool-add", help="ツール(ロール単位のツールエンドポイント)を登録する(承認済みツールサーバ)")
    p.add_argument("--endpoint", required=True, help="ツールエンドポイント(全体で一意)")
    p.add_argument("--context", required=True, help="ツールのコンテキスト(説明)")
    p.add_argument("--params-schema", required=True, help="ツールのparamsのスキーマ(JSON Schema)。JSON文字列、または @ファイルパス。各パラメータに description が必要。pattern は使えない")
    p.add_argument("--token", help="ツール代理トークン(省略時は自動発行)")
    p.set_defaults(func=cmd_tool_add)

    p = sub.add_parser("tool-chtkn", help="ツール代理トークンを更新する(ツールサーバの定期更新ジョブ。割り当てられた全AIエージェントに反映される)")
    p.add_argument("--endpoint", required=True, help="ツールエンドポイント")
    p.add_argument("--token", help="新しいツール代理トークン(省略時は自動発行)")
    p.set_defaults(func=cmd_tool_chtkn)

    p = sub.add_parser("agent-grant", help="AIエージェントへのツールの割り当てを申請する(AIエージェント)")
    p.add_argument("--agent-id", required=True)
    p.add_argument("--endpoint", required=True, help="ツールエンドポイント")
    p.add_argument("--email", required=True, help="申請者のメールアドレス")
    p.set_defaults(func=cmd_agent_grant)

    p = sub.add_parser("agent-grant-approve", help="ツールの割り当ての申請を承認する(管理者)")
    p.add_argument("--agent-id", required=True)
    p.add_argument("--endpoint", required=True, help="ツールエンドポイント")
    p.set_defaults(func=cmd_agent_grant_approve)

    p = sub.add_parser("agent-revoke", help="ツールの割り当てを取り消す(管理者、またはツールを登録したツールサーバ)")
    p.add_argument("--agent-id", required=True)
    p.add_argument("--endpoint", required=True, help="ツールエンドポイント")
    p.add_argument("--as", dest="as_signer", choices=["admin", "toolserver"], default="admin", help="署名する人。admin=ADMIN_PRIVATE_KEY、toolserver=TOOL_SERVER_PRIVATE_KEY")
    p.set_defaults(func=cmd_agent_revoke)

    p = sub.add_parser("agent-tools", help="使用できるツールの一覧を取得する(AIエージェント)")
    p.add_argument("--agent-id", required=True)
    p.set_defaults(func=cmd_agent_tools)

    p = sub.add_parser("agent-exec", help="ツールを実行する(AIエージェント)")
    p.add_argument("--agent-id", required=True)
    p.add_argument("--endpoint", required=True, help="ツールエンドポイント")
    p.add_argument("--params", default="{}", help='ツールパラメータ(JSONオブジェクト)。例: \'{"sql": "SELECT 1"}\'')
    p.set_defaults(func=cmd_agent_exec)

    args = parser.parse_args()
    args.func(args)


if __name__ == "__main__":
    main()

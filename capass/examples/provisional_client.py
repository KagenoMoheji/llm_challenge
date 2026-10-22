"""CaPassクライアント(CLI)が実装されるまでの暫定クライアント(開発・動作確認用)。

CLIの `keygen` / `regist` などの代わりに、CaPassサーバのRestAPIを、署名付きで直接呼び出す。
秘密鍵は環境変数で渡す(keygenで作ったBase64文字列)。サーバのURLは CAPASS_URL(省略時 http://127.0.0.1:8000)。

  python provisional_client.py keygen
  python provisional_client.py toolserver-register --name "社内ツールサーバA" \
      --exec-url https://toolserver.example.com/capass/exec --email you@example.com      # 環境変数 TOOL_SERVER_PRIVATE_KEY
  python provisional_client.py toolserver-approve  --toolserver-id 1                   # 環境変数 ADMIN_PRIVATE_KEY
  python provisional_client.py agent-register      --agent-id agent-1 --email you@example.com          # 環境変数 AGENT_PRIVATE_KEY
  python provisional_client.py agent-approve       --agent-id agent-1                  # 環境変数 ADMIN_PRIVATE_KEY
  python provisional_client.py agent-addtool       --agent-id agent-1 \
      --endpoint psql_manager --context "..." --params-schema @schema.json             # 環境変数 TOOL_SERVER_PRIVATE_KEY
  # ツールサーバのリプレース: 新ツールサーバで handoff を作り(PRIVATEは新ツールサーバの鍵)、旧ツールサーバで chkey する(PRIVATEは旧ツールサーバの鍵)
  python provisional_client.py toolserver-chkey-prepare --toolserver-id 1 --old-public-key <旧公開鍵>   # 新ツールサーバ: 環境変数 TOOL_SERVER_PRIVATE_KEY
  python provisional_client.py toolserver-chkey --toolserver-id 1 --handoff @handoff.json              # 旧ツールサーバ: 環境変数 TOOL_SERVER_PRIVATE_KEY
  python provisional_client.py agent-chtkn         --agent-id agent-1 --endpoint psql_manager   # 環境変数 TOOL_SERVER_PRIVATE_KEY(chtkn の代用。トークンは自動で新しく作る)
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
SIGN_CONTEXT_TOOLSERVER_CHKEY_OLD = b"capass-toolserver-chkey-old-v1\n"
SIGN_CONTEXT_TOOLSERVER_CHKEY_NEW = b"capass-toolserver-chkey-new-v1\n"
SIGN_CONTEXT_AGENT_REGISTER = b"capass-agent-register-v1\n"
SIGN_CONTEXT_AGENT_APPROVE = b"capass-agent-approve-v1\n"
SIGN_CONTEXT_AGENT_ADDTOOL = b"capass-agent-addtool-v1\n"
SIGN_CONTEXT_AGENT_CHTKN = b"capass-agent-chtkn-v1\n"
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


def build_agent_addtool(priv: Ed25519PrivateKey, agent_id: str, endpoint: str, context: str, token: str, params_schema: dict) -> tuple[str, dict]:
    fields = {
        "tool_endpoint": endpoint,
        "context": context,
        "params_schema": params_schema,
        "tool_proxy_token": token,
        "tool_server_public_key": _public_key_b64(priv),
    }
    body = _signed_body(priv, SIGN_CONTEXT_AGENT_ADDTOOL, fields, {"agent_id": agent_id})
    return f"/api/v1/agents/{urllib.parse.quote(agent_id, safe='')}/addtool", body


def _sign_canonical(priv: Ed25519PrivateKey, sign_context: bytes, payload: dict) -> str:
    canonical = json.dumps(payload, sort_keys=True, separators=(",", ":"), ensure_ascii=False).encode("utf-8")
    return base64.b64encode(priv.sign(sign_context + canonical)).decode()


def build_chkey_handoff(new_priv: Ed25519PrivateKey, toolserver_id: int, old_public_key: str) -> dict:
    """新ツールサーバが、自分の鍵の所持を証明する署名を作る。旧ツールサーバへ渡す(handoff)。署名時刻は、旧ツールサーバの署名にも使う。"""
    signed_at = int(time.time())
    payload = {
        "toolserver_id": toolserver_id,
        "old_tool_server_public_key": old_public_key,
        "new_tool_server_public_key": _public_key_b64(new_priv),
        "signed_at": signed_at,
    }
    return {
        "new_tool_server_public_key": payload["new_tool_server_public_key"],
        "signed_at": signed_at,
        "new_key_signature": _sign_canonical(new_priv, SIGN_CONTEXT_TOOLSERVER_CHKEY_NEW, payload),
    }


def build_chkey(old_priv: Ed25519PrivateKey, toolserver_id: int, handoff: dict) -> tuple[str, dict]:
    """旧ツールサーバが、handoffと同じ内容に署名して、リクエストを作る。"""
    payload = {
        "toolserver_id": toolserver_id,
        "old_tool_server_public_key": _public_key_b64(old_priv),
        "new_tool_server_public_key": handoff["new_tool_server_public_key"],
        "signed_at": handoff["signed_at"],
    }
    body = {**handoff, "signature": _sign_canonical(old_priv, SIGN_CONTEXT_TOOLSERVER_CHKEY_OLD, payload)}
    return f"/api/v1/toolservers/{toolserver_id}/chkey", body


def build_agent_chtkn(priv: Ed25519PrivateKey, agent_id: str, endpoint: str, token: str) -> tuple[str, dict]:
    fields = {"tool_proxy_token": token, "tool_server_public_key": _public_key_b64(priv), "nonce": secrets.token_urlsafe(16)}  # nonceは、リクエストごとに必ず新しく作る
    body = _signed_body(priv, SIGN_CONTEXT_AGENT_CHTKN, fields, {"agent_id": agent_id, "tool_endpoint": endpoint})
    return f"/api/v1/agents/{urllib.parse.quote(agent_id, safe='')}/chtkn/{urllib.parse.quote(endpoint, safe='')}", body


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


def cmd_agent_addtool(a: argparse.Namespace) -> None:
    token = a.token or secrets.token_urlsafe(32)  # ツール代理トークン。省略時は自動発行する
    print("tool_proxy_token(ツールサーバ側のDBにも [認証情報/トークン/エージェント] として保存すること):", token)
    _post(*build_agent_addtool(_load_private_key("TOOL_SERVER_PRIVATE_KEY"), a.agent_id, a.endpoint, a.context, token, _load_json_object(a.params_schema, "--params-schema")))


def cmd_toolserver_chkey_prepare(a: argparse.Namespace) -> None:
    handoff = build_chkey_handoff(_load_private_key("TOOL_SERVER_PRIVATE_KEY"), a.toolserver_id, a.old_public_key)
    print(json.dumps(handoff, ensure_ascii=False))
    print("# 上のJSONを、旧ツールサーバへ渡してください(署名時刻から、数分以内に chkey を実行すること)", file=sys.stderr)


def cmd_toolserver_chkey(a: argparse.Namespace) -> None:
    _post(*build_chkey(_load_private_key("TOOL_SERVER_PRIVATE_KEY"), a.toolserver_id, _load_json_object(a.handoff, "--handoff")))


def cmd_agent_chtkn(a: argparse.Namespace) -> None:
    token = a.token or secrets.token_urlsafe(32)  # 新しいツール代理トークン。省略時は自動発行する
    print("new tool_proxy_token(ツールサーバ側のDBに、先に保存しておくこと。新しいトークンは、CaPassサーバの更新が完了するまで、古いトークンと両方で受け付けると安全):", token)
    _post(*build_agent_chtkn(_load_private_key("TOOL_SERVER_PRIVATE_KEY"), a.agent_id, a.endpoint, token))


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

    p = sub.add_parser("agent-addtool", help="AIエージェントへのツール追加(承認済みツールサーバ)")
    p.add_argument("--agent-id", required=True)
    p.add_argument("--endpoint", required=True, help="ツールエンドポイント")
    p.add_argument("--context", required=True, help="ツールのコンテキスト(説明)")
    p.add_argument("--params-schema", required=True, help="ツールのparamsのスキーマ(JSON Schema)。JSON文字列、または @ファイルパス。各パラメータに description が必要")
    p.add_argument("--token", help="ツール代理トークン(省略時は自動発行)")
    p.set_defaults(func=cmd_agent_addtool)

    p = sub.add_parser("toolserver-chkey-prepare", help="ツールサーバのリプレース: 新ツールサーバで、鍵の所持を証明する署名(handoff)を作る")
    p.add_argument("--toolserver-id", type=int, required=True)
    p.add_argument("--old-public-key", required=True, help="旧ツールサーバの公開鍵(現在登録されているもの)")
    p.set_defaults(func=cmd_toolserver_chkey_prepare)

    p = sub.add_parser("toolserver-chkey", help="ツールサーバのリプレース: 旧ツールサーバで、handoffに署名して、公開鍵の更新を依頼する")
    p.add_argument("--toolserver-id", type=int, required=True)
    p.add_argument("--handoff", required=True, help="新ツールサーバが作ったhandoff(JSON文字列、または @ファイルパス)")
    p.set_defaults(func=cmd_toolserver_chkey)

    p = sub.add_parser("agent-chtkn", help="ツール代理トークンを更新する(ツールサーバの定期更新ジョブ)")
    p.add_argument("--agent-id", required=True)
    p.add_argument("--endpoint", required=True, help="ツールエンドポイント")
    p.add_argument("--token", help="新しいツール代理トークン(省略時は自動発行)")
    p.set_defaults(func=cmd_agent_chtkn)

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

"""CaPassクライアント(CLI)が実装されるまでの暫定クライアント(開発・動作確認用)。

CLIの `keygen` / `regist` などの代わりに、CaPassサーバのRestAPIを、署名付きで直接呼び出す。
秘密鍵は環境変数で渡す(keygenで作ったBase64文字列)。サーバのURLは CAPASS_URL(省略時 http://127.0.0.1:8000)。

  python provisional_client.py keygen
  python provisional_client.py toolserver-register --name "社内ツールサーバA"           # 環境変数 TOOL_SERVER_PRIVATE_KEY
  python provisional_client.py toolserver-approve  --toolserver-id 1                   # 環境変数 ADMIN_PRIVATE_KEY
  python provisional_client.py agent-register      --agent-id agent-1                  # 環境変数 AGENT_PRIVATE_KEY
  python provisional_client.py agent-approve       --agent-id agent-1                  # 環境変数 ADMIN_PRIVATE_KEY
  python provisional_client.py agent-addtool       --agent-id agent-1 \
      --endpoint psql_manager --context "..."                                          # 環境変数 TOOL_SERVER_PRIVATE_KEY
"""
import argparse
import base64
import json
import os
import secrets
import sys
import time
import urllib.error
import urllib.parse
import urllib.request

from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey
from cryptography.hazmat.primitives.serialization import Encoding, NoEncryption, PrivateFormat, PublicFormat

CAPASS_URL = os.environ.get("CAPASS_URL", "http://127.0.0.1:8000")

# 署名メッセージのプレフィックス。サーバ(capass_server/common/signature.py)のSIGN_CONTEXT_*と一致させること
SIGN_CONTEXT_TOOLSERVER_REGISTER = b"capass-toolserver-register-v1\n"
SIGN_CONTEXT_TOOLSERVER_APPROVE = b"capass-toolserver-approve-v1\n"
SIGN_CONTEXT_AGENT_REGISTER = b"capass-agent-register-v1\n"
SIGN_CONTEXT_AGENT_APPROVE = b"capass-agent-approve-v1\n"
SIGN_CONTEXT_AGENT_ADDTOOL = b"capass-agent-addtool-v1\n"


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


def cmd_keygen(_: argparse.Namespace) -> None:
    priv = Ed25519PrivateKey.generate()
    print("PRIVATE:", base64.b64encode(priv.private_bytes(Encoding.Raw, PrivateFormat.Raw, NoEncryption())).decode())
    print("PUBLIC :", _public_key_b64(priv))


def build_toolserver_register(priv: Ed25519PrivateKey, name: str) -> tuple[str, dict]:
    fields = {"tool_server_public_key": _public_key_b64(priv), "tool_server_name": name}
    return "/api/v1/toolservers/register", _signed_body(priv, SIGN_CONTEXT_TOOLSERVER_REGISTER, fields)


def build_toolserver_approve(admin: Ed25519PrivateKey, toolserver_id: int) -> tuple[str, dict]:
    fields = {"admin_public_key": _public_key_b64(admin)}
    body = _signed_body(admin, SIGN_CONTEXT_TOOLSERVER_APPROVE, fields, {"toolserver_id": toolserver_id})
    return f"/api/v1/toolservers/{toolserver_id}/approve", body


def build_agent_register(priv: Ed25519PrivateKey, agent_id: str) -> tuple[str, dict]:
    fields = {"agent_id": agent_id, "agent_public_key": _public_key_b64(priv)}
    return "/api/v1/agents/register", _signed_body(priv, SIGN_CONTEXT_AGENT_REGISTER, fields)


def build_agent_approve(admin: Ed25519PrivateKey, agent_id: str) -> tuple[str, dict]:
    fields = {"admin_public_key": _public_key_b64(admin)}
    body = _signed_body(admin, SIGN_CONTEXT_AGENT_APPROVE, fields, {"agent_id": agent_id})
    return f"/api/v1/agents/{urllib.parse.quote(agent_id, safe='')}/approve", body


def build_agent_addtool(priv: Ed25519PrivateKey, agent_id: str, endpoint: str, context: str, token: str) -> tuple[str, dict]:
    fields = {
        "tool_endpoint": endpoint,
        "context": context,
        "tool_proxy_token": token,
        "tool_server_public_key": _public_key_b64(priv),
    }
    body = _signed_body(priv, SIGN_CONTEXT_AGENT_ADDTOOL, fields, {"agent_id": agent_id})
    return f"/api/v1/agents/{urllib.parse.quote(agent_id, safe='')}/addtool", body


def cmd_toolserver_register(a: argparse.Namespace) -> None:
    _post(*build_toolserver_register(_load_private_key("TOOL_SERVER_PRIVATE_KEY"), a.name))


def cmd_toolserver_approve(a: argparse.Namespace) -> None:
    _post(*build_toolserver_approve(_load_private_key("ADMIN_PRIVATE_KEY"), a.toolserver_id))


def cmd_agent_register(a: argparse.Namespace) -> None:
    _post(*build_agent_register(_load_private_key("AGENT_PRIVATE_KEY"), a.agent_id))


def cmd_agent_approve(a: argparse.Namespace) -> None:
    _post(*build_agent_approve(_load_private_key("ADMIN_PRIVATE_KEY"), a.agent_id))


def cmd_agent_addtool(a: argparse.Namespace) -> None:
    token = a.token or secrets.token_urlsafe(32)  # ツール代理トークン。省略時は自動発行する
    print("tool_proxy_token(ツールサーバ側のDBにも [認証情報/トークン/エージェント] として保存すること):", token)
    _post(*build_agent_addtool(_load_private_key("TOOL_SERVER_PRIVATE_KEY"), a.agent_id, a.endpoint, a.context, token))


def main() -> None:
    parser = argparse.ArgumentParser(description="CaPass暫定クライアント(CLI実装までの代用)")
    sub = parser.add_subparsers(dest="command", required=True)

    sub.add_parser("keygen", help="Ed25519キーペアを作る").set_defaults(func=cmd_keygen)

    p = sub.add_parser("toolserver-register", help="ツールサーバ(公開鍵)の初回登録")
    p.add_argument("--name", required=True, help="ツールサーバの名称(管理者が承認時に識別するため)")
    p.set_defaults(func=cmd_toolserver_register)

    p = sub.add_parser("toolserver-approve", help="ツールサーバの登録承認(管理者)")
    p.add_argument("--toolserver-id", type=int, required=True)
    p.set_defaults(func=cmd_toolserver_approve)

    p = sub.add_parser("agent-register", help="AIエージェント(公開鍵)の初回登録")
    p.add_argument("--agent-id", required=True)
    p.set_defaults(func=cmd_agent_register)

    p = sub.add_parser("agent-approve", help="AIエージェントの登録承認(管理者)")
    p.add_argument("--agent-id", required=True)
    p.set_defaults(func=cmd_agent_approve)

    p = sub.add_parser("agent-addtool", help="AIエージェントへのツール追加(承認済みツールサーバ)")
    p.add_argument("--agent-id", required=True)
    p.add_argument("--endpoint", required=True, help="ツールエンドポイント")
    p.add_argument("--context", required=True, help="ツールのコンテキスト(説明)")
    p.add_argument("--token", help="ツール代理トークン(省略時は自動発行)")
    p.set_defaults(func=cmd_agent_addtool)

    args = parser.parse_args()
    args.func(args)


if __name__ == "__main__":
    main()

# CaPass QUICKSTART(暫定版)

> **この文書は暫定版です。** CaPassクライアント(CLI)がまだ未実装のため、ツールサーバのキー作成(`keygen`)と登録(`regist`)は、Pythonスクリプトで代用しています。管理者によるツールサーバ公開鍵の承認も、承認用のAPI/CLIが未実装のため、SQLを直接実行します。CLIと承認APIの実装後に置き換えます。
> 現時点で動作するAPIは `POST /api/v1/register` のみです(`list executable` と `exec` は未実装)。

## 1. 想定シナリオ

同じツールサーバが `psql` コマンドというツールを提供し、DBユーザ(ロール)として **部長ロール** と **端末管理者ロール** を用意します。これを、CaPassには別々のツールとして登録します。

| ツールエンドポイント | 使うDBロール | AIエージェント | 備考 |
|---|---|---|---|
| `psql_manager` | `psql_manager`(部長ロール) | `agent-1` | 専用のツール代理トークンを持つ |
| `psql_terminal_admin` | `psql_terminal_admin`(端末管理者ロール) | `agent-1` | 専用のツール代理トークンを持つ |

登録の流れは次のとおりです。

1. ツールサーバ提供者が、ツールサーバ側でDBロールを作る
2. ツールサーバ提供者が、ツールサーバのキーペアを作る
3. **CaPassサーバ管理者が、ツールサーバの公開鍵を確認して承認する**(承認されていない公開鍵では登録できない)
4. ツールサーバ提供者が、ツールごとに代理トークンを発行し、署名付きで `register` する

## 2. 事前準備(CaPassサーバ)

```bash
cd server
pip install -e ".[dev]"
```

必要な環境変数(未設定だと起動しません)。

| 環境変数 | 内容 |
|---|---|
| `CAPASS_SERVER_ENV` | `LOCAL_DEV` / `DEV` ではテーブルを自動作成します |
| `CAPASS_SERVER_DB_HOST` / `_DB_PORT` / `_DB_NAME` / `_DB_USER` / `_DB_PASSWORD` | PostgreSQLの接続情報 |
| `CAPASS_SERVER_TOKEN_ENCRYPTION_KEYS` | ツール代理トークンの暗号化鍵(Fernet鍵。カンマ区切りで複数可) |
| `CAPASS_SERVER_SIGNATURE_MAX_SKEW_SEC` | 署名時刻の許容ずれ(秒)。省略時は300 |

暗号化鍵の作り方:

```bash
python -c "from cryptography.fernet import Fernet; print(Fernet.generate_key().decode())"
```

起動:

```bash
capass-server    # http://127.0.0.1:8000 (Swagger UI は /docs)
```

## 3. ツールサーバ側の準備

### 3.1 DBロールを作る(ツールサーバが接続するPostgreSQL)

ツールが何をできるかは、**DBロールの権限(GRANT)で決まります**。CaPassは「どのAIエージェントがどのツールエンドポイントを使ってよいか」を管理するだけです。

```sql
CREATE ROLE psql_manager LOGIN PASSWORD '<パスワード>';
GRANT SELECT ON ALL TABLES IN SCHEMA public TO psql_manager;

CREATE ROLE psql_terminal_admin LOGIN PASSWORD '<パスワード>';
GRANT SELECT, INSERT, UPDATE ON terminals TO psql_terminal_admin;
```

### 3.2 ツールサーバのキーペアを作る(`keygen` の代用)

```python
import base64
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey
from cryptography.hazmat.primitives.serialization import Encoding, NoEncryption, PrivateFormat, PublicFormat

priv = Ed25519PrivateKey.generate()
print("PRIVATE:", base64.b64encode(priv.private_bytes(Encoding.Raw, PrivateFormat.Raw, NoEncryption())).decode())
print("PUBLIC :", base64.b64encode(priv.public_key().public_bytes(Encoding.Raw, PublicFormat.Raw)).decode())
```

- **秘密鍵(PRIVATE)はツールサーバ上だけで保管します**(ファイル権限は `600` など)。CaPassにも管理者にも渡しません。
- 公開鍵(PUBLIC)を、ツールサーバの名称と一緒にCaPassサーバ管理者へ伝えます。メールやチャットなど、**管理者が提供者本人からの連絡と確認できる経路**を使ってください。

## 4. CaPassサーバ管理者による公開鍵の承認(暫定: SQL)

管理者は、提供者から伝えられた公開鍵と名称を確認したうえで、CaPassサーバのDBで次を実行します。

```sql
INSERT INTO tbl_tool_server (tool_server_public_key, tool_server_name, status, created_at, approved_at)
VALUES ('<公開鍵>', '社内ツールサーバA', 'approved', now(), now());
```

`status` は次の3種類です。`register` が許可されるのは `approved` のみです。

| status | 意味 |
|---|---|
| `pending` | 承認待ち |
| `approved` | 承認済み |
| `revoked` | 却下・失効 |

承認を取り消す場合:

```sql
UPDATE tbl_tool_server SET status = 'revoked' WHERE tool_server_public_key = '<公開鍵>';
```

> 現時点では、取り消しは **新規の `register` にだけ効きます**。登録済みのツールの `list executable` / `exec` への反映は、それらの実装時に対応します。

## 5. ツールを登録する(`regist` の代用)

ツールごとに別のツール代理トークンを発行して、署名付きで `register` します。次のスクリプトは `register_tools.py` として保存します。

```python
import base64
import json
import os
import secrets
import time
import urllib.error
import urllib.request

from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey
from cryptography.hazmat.primitives.serialization import Encoding, PublicFormat

CAPASS_URL = os.environ.get("CAPASS_URL", "http://127.0.0.1:8000")
SIGN_CONTEXT = b"capass-register-v1\n"  # サーバの SIGN_CONTEXT_REGISTER と一致させる

private_key = Ed25519PrivateKey.from_private_bytes(base64.b64decode(os.environ["TOOL_SERVER_PRIVATE_KEY"]))
public_key_b64 = base64.b64encode(private_key.public_key().public_bytes(Encoding.Raw, PublicFormat.Raw)).decode()

AGENT_ID = "agent-1"
TOOLS = [
    ("psql_manager", "PostgreSQLに部長ロール(psql_manager)で接続し、SQLを実行する。社員・売上など全社データの参照が可能。"),
    ("psql_terminal_admin", "PostgreSQLに端末管理者ロール(psql_terminal_admin)で接続し、SQLを実行する。端末台帳の参照・更新が可能。"),
]


def build_body(tool_endpoint: str, context: str, tool_proxy_token: str) -> dict:
    body = {
        "tool_endpoint": tool_endpoint,
        "context": context,
        "tool_proxy_token": tool_proxy_token,
        "agent_id": AGENT_ID,
        "tool_server_public_key": public_key_b64,
        "signed_at": int(time.time()),
    }
    # signature以外の全フィールドを正規化JSONにして、プレフィックスを付けて署名する
    canonical = json.dumps(body, sort_keys=True, separators=(",", ":"), ensure_ascii=False).encode("utf-8")
    body["signature"] = base64.b64encode(private_key.sign(SIGN_CONTEXT + canonical)).decode()
    return body


def register(body: dict) -> None:
    req = urllib.request.Request(
        f"{CAPASS_URL}/api/v1/register",
        data=json.dumps(body, ensure_ascii=False).encode("utf-8"),
        headers={"Content-Type": "application/json"},
        method="POST",
    )
    try:
        with urllib.request.urlopen(req) as res:
            print(res.status, res.read().decode("utf-8"))
    except urllib.error.HTTPError as e:
        print(e.code, e.read().decode("utf-8"))


if __name__ == "__main__":
    for endpoint, context in TOOLS:
        token = secrets.token_urlsafe(32)  # ツール代理トークン(ツールサーバ側のDBにも [認証情報/トークン/エージェント] として保存すること)
        register(build_body(endpoint, context, token))
```

実行:

```bash
export TOOL_SERVER_PRIVATE_KEY='<3.2のPRIVATE>'
export CAPASS_URL='http://127.0.0.1:8000'
python register_tools.py
```

発行したトークンは、ツールサーバ側のDB(ツールサーバ付きDB)にも `[認証情報(DBロール)/ツール代理トークン/AIエージェント情報]` として保存する必要があります。`exec` のときにCaPassから渡されるトークンで、ツールサーバが認証情報を引くためです。上のスクリプトはトークンを保存しないので、実運用では保存処理を追加してください。

### 結果の確認

```sql
SELECT tool_endpoint, agent_id, locked FROM tbl_agent_tool;
```

`psql_manager` と `psql_terminal_admin` の2行が、`agent-1` に対して登録されていれば成功です。

### レスポンスの意味

| ステータス | 原因 |
|---|---|
| 201 | 登録成功 |
| 401 | 署名が不正、または署名時刻(`signed_at`)がサーバ時刻から許容範囲を超えてずれている(時刻同期を確認) |
| 403 | 公開鍵が未承認(未登録 / `pending` / `revoked`)。管理者に承認を依頼する |
| 409 | 同じ `[ツールエンドポイント, AIエージェント]` が登録済み |
| 422 | リクエストの形式が不正(公開鍵や署名のBase64が不正、項目の過不足など) |

## 6. 考え方

- **ロールごとに別のツールエンドポイントとして登録します。** ツールエンドポイントはツールサーバで実際にコマンドを起動する受け口なので、`psql_manager` はツールサーバ側で部長ロールの認証情報、`psql_terminal_admin` は端末管理者ロールの認証情報に対応づけます。
- **AIエージェントはツール一覧の `context`(説明)を見てツールを選びます。** そのため、ロール名と、そのロールでできること・できないことを `context` に具体的に書いてください。
- **1つのAIエージェントに両方のロールを使わせる場合は、両方を登録します。** 部長ロールだけ使わせるAIエージェントには、`psql_manager` だけを登録します。
- ツールエンドポイント名には、日本語も使えます(512文字まで)。ただし、ツールサーバ側の識別子と合わせやすいよう、ASCIIの識別子にして、日本語の説明は `context` に書くことをお勧めします。

## 7. 今後置き換わる箇所

| 現在(暫定) | 将来 |
|---|---|
| キーペア作成のPythonスニペット | CaPassクライアントの `keygen` |
| `register_tools.py` | CaPassクライアントの `regist` |
| 承認用のSQL | 承認用のAPI/CLI(管理者認証の設計が必要) |

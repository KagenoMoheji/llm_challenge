# CaPass QUICKSTART(暫定版)

> **この文書は暫定版です。** CaPassクライアント(CLI)がまだ未実装のため、キー作成(`keygen`)や各API呼び出しは、暫定クライアント [`examples/provisional_client.py`](examples/provisional_client.py) で代用しています。CLIの実装後に置き換えます。
> 現時点で動作するAPIは、下表の登録・承認・ツール追加の5つです(`list executable` と `exec` は未実装)。

## 1. 全体像

AIエージェントにツールを使わせるまでに、次の登録と承認が必要です。**ツールサーバ**と**AIエージェント**は、それぞれ自分の公開鍵と申請者のメールアドレスを初回登録(承認待ち)し、**CaPassサーバ管理者**が申請内容を確認して承認して初めて使えるようになります。

| 誰が | API | 内容 |
|---|---|---|
| ツールサーバ提供者 | `POST /api/v1/toolservers/register` | ツールサーバ(公開鍵)の初回登録(承認待ち) |
| CaPassサーバ管理者 | `POST /api/v1/toolservers/{toolserver_id}/approve` | ツールサーバの承認 |
| AIエージェント提供者 | `POST /api/v1/agents/register` | AIエージェント(公開鍵)の初回登録(承認待ち) |
| CaPassサーバ管理者 | `POST /api/v1/agents/{agent_id}/approve` | AIエージェントの承認 |
| ツールサーバ提供者 | `POST /api/v1/agents/{agent_id}/addtool` | 承認済みAIエージェントへのツール追加(承認済みツールサーバのみ) |

登録の順序は次のとおりです。

1. 管理者を、CaPassサーバのDB(`tbl_admin`)に登録する(最初の1回だけ。以降は、追加・無効化のたびにSQLで更新)
2. ツールサーバとAIエージェントが、それぞれキーペアを作り、自分の公開鍵と申請者のメールアドレスを初回登録する(`pending`)
3. 管理者が、申請者に確認の連絡をしたうえで承認する(`approved`。承認した管理者のメールアドレスが記録される)
4. 承認済みのツールサーバが、承認済みのAIエージェントにツールを追加する

## 2. 署名の仕様

登録・承認・ツール追加のリクエストは、全て **Ed25519の署名付き**です。

- 公開鍵(生32バイト)と署名(64バイト)は、標準Base64で送ります。
- 署名するメッセージは、`エンドポイントごとの固定プレフィックス + 正規化JSON` です。
- 正規化JSONは、**`signature` 以外のボディの全フィールド + URLパスのパラメータ**を、`sort_keys=True` / `separators=(',', ':')` / `ensure_ascii=False` でJSON化し、UTF-8でエンコードしたものです。URLパスのパラメータも署名対象にして、別のリソースへのリクエストの使い回しを防ぎます。
- `signed_at`(UNIX秒)がサーバ時刻から許容範囲(デフォルト300秒)を超えてずれていると拒否されます。

| API | プレフィックス | 署名する鍵 | ボディのフィールド(`signature` を除く) | URLパスのパラメータ |
|---|---|---|---|---|
| `toolservers/register` | `capass-toolserver-register-v1\n` | ツールサーバの秘密鍵 | `tool_server_public_key` `tool_server_name` `applicant_email` `signed_at` | なし |
| `toolservers/{toolserver_id}/approve` | `capass-toolserver-approve-v1\n` | 管理者の秘密鍵 | `admin_public_key` `signed_at` | `toolserver_id`(整数) |
| `agents/register` | `capass-agent-register-v1\n` | AIエージェントの秘密鍵 | `agent_id` `agent_public_key` `applicant_email` `signed_at` | なし |
| `agents/{agent_id}/approve` | `capass-agent-approve-v1\n` | 管理者の秘密鍵 | `admin_public_key` `signed_at` | `agent_id`(文字列) |
| `agents/{agent_id}/addtool` | `capass-agent-addtool-v1\n` | ツールサーバの秘密鍵 | `tool_endpoint` `context` `tool_proxy_token` `tool_server_public_key` `signed_at` | `agent_id`(文字列) |

**管理者の本人確認の流れ:** 管理者は、`approve` のリクエストに、自分の公開鍵(`admin_public_key`)と、秘密鍵で作った署名を付けます。サーバは、①署名がその公開鍵で検証できること(=秘密鍵の持ち主であり、内容が改ざんされていないこと)、②その公開鍵が `tbl_admin` に登録された**有効な管理者**のものであることを確認します。署名は暗号化ではなく、サーバが復号するわけではありません。

登録系は、自分の秘密鍵で署名することで**鍵の所持を証明**します(その鍵で登録してよい相手かどうかは、管理者の承認で確認します)。

## 3. 事前準備(CaPassサーバ)

```bash
cd server
pip install -e ".[dev]"
```

環境変数(必須のもの)。

| 環境変数 | 内容 |
|---|---|
| `CAPASS_SERVER_ENV` | `LOCAL_DEV` / `DEV` ではテーブルを自動作成します |
| `CAPASS_SERVER_DB_HOST` / `_DB_PORT` / `_DB_NAME` / `_DB_USER` / `_DB_PASSWORD` | PostgreSQLの接続情報 |
| `CAPASS_SERVER_TOKEN_ENCRYPTION_KEYS` | ツール代理トークンの暗号化鍵(Fernet鍵。カンマ区切りで複数可) |

環境変数(任意のもの)。

| 環境変数 | 内容 | 省略時 |
|---|---|---|
| `CAPASS_SERVER_SIGNATURE_MAX_SKEW_SEC` | 署名時刻の許容ずれ(秒) | 300 |
| `CAPASS_SERVER_RATE_LIMIT_ENABLED` | 初回登録APIのレート制限の有効/無効(`true` / `false`) | `true` |
| `CAPASS_SERVER_RATE_LIMIT_REGISTER_MAX_REQUESTS` | 初回登録APIの、1つのIPあたりの上限回数 | 10 |
| `CAPASS_SERVER_RATE_LIMIT_REGISTER_WINDOW_SEC` | 上記の上限を数える時間幅(秒) | 60 |
| `CAPASS_SERVER_TRUSTED_PROXY_COUNT` | `X-Forwarded-For` を付ける、信頼できるリバースプロキシの段数 | 0 |

暗号化鍵の作り方:

```bash
python -c "from cryptography.fernet import Fernet; print(Fernet.generate_key().decode())"
```

> **既存のDBがある場合:** `tbl_admin` が新設され、`tbl_tool_server` / `tbl_agent` に `applicant_email` / `approver_email` が追加されました。`create_all` は既存のテーブルを変更しないので、開発用DBは作り直してください。

### レート制限について

初回登録のAPI(`toolservers/register` と `agents/register`)は、誰でも呼べるため、**クライアントのIPごと**に回数を制限します(2つのAPIで共通の枠)。上限を超えると `429` と `Retry-After` ヘッダー(再試行までの秒数)を返します。

- カウンタはサーバプロセスのメモリ上にあります。複数プロセス・複数台で動かす場合は、プロセスごとの制限になるので、リバースプロキシやWAFでの制限を併用してください。
- **リバースプロキシの背後で動かす場合は、`CAPASS_SERVER_TRUSTED_PROXY_COUNT` にプロキシの段数を設定してください。** 0のままだと、全クライアントがプロキシのIPとして扱われ、まとめて制限されます。逆に、実際より大きい値にすると、クライアントが `X-Forwarded-For` を偽装して制限を回避できます。

## 4. 管理者を登録する

管理者の追加・無効化は、APIを設けず、**管理者がSQLクライアントで `tbl_admin` を更新して行います。CaPassサーバの再起動は不要**です。

管理者の鍵ペアを作ります。

```bash
cd examples
python provisional_client.py keygen
# PRIVATE: <管理者の秘密鍵>   ← 管理者だけが保管する
# PUBLIC : <管理者の公開鍵>   ← tbl_admin に登録する
```

CaPassサーバを起動して、管理者を登録します(最初の管理者は、DBに直接登録します)。

```bash
capass-server    # http://127.0.0.1:8000 (Swagger UI は /docs)
```

```sql
INSERT INTO tbl_admin (admin_email, admin_public_key, is_active, created_at)
VALUES ('admin@example.com', '<管理者の公開鍵>', true, now());
```

管理者を無効化する場合(以降の承認ができなくなります。承認済みのレコードに記録された承認者メアドは残ります):

```sql
UPDATE tbl_admin SET is_active = false WHERE admin_email = 'admin@example.com';
```

> `tbl_admin` を書き換えられる人は、管理者を追加できます。本番では、DBの更新権限を管理者だけに絞り、CaPassサーバが使うDBユーザには `tbl_admin` の `SELECT` だけを許可することをお勧めします。

## 5. 想定シナリオ: psql を、部長ロールと端末管理者ロールで使い分ける

同じツールサーバが `psql` コマンドというツールを提供し、DBユーザ(ロール)として**部長ロール**と**端末管理者ロール**を用意します。CaPassには、別々のツールとして登録します。

| ツールエンドポイント | 使うDBロール | AIエージェント | 備考 |
|---|---|---|---|
| `psql_manager` | `psql_manager`(部長ロール) | `agent-1` | 専用のツール代理トークンを持つ |
| `psql_terminal_admin` | `psql_terminal_admin`(端末管理者ロール) | `agent-1` | 専用のツール代理トークンを持つ |

### 5.1 ツールサーバ側のDBロールを作る(ツールサーバが接続するPostgreSQL)

ツールが何をできるかは、**DBロールの権限(GRANT)で決まります**。CaPassは「どのAIエージェントがどのツールエンドポイントを使ってよいか」を管理するだけです。

```sql
CREATE ROLE psql_manager LOGIN PASSWORD '<パスワード>';
GRANT SELECT ON ALL TABLES IN SCHEMA public TO psql_manager;

CREATE ROLE psql_terminal_admin LOGIN PASSWORD '<パスワード>';
GRANT SELECT, INSERT, UPDATE ON terminals TO psql_terminal_admin;
```

### 5.2 ツールサーバ・AIエージェントの鍵を作って、初回登録する

```bash
# ツールサーバ提供者
python provisional_client.py keygen        # PRIVATE はツールサーバ上だけで保管する
export TOOL_SERVER_PRIVATE_KEY='<ツールサーバのPRIVATE>'
python provisional_client.py toolserver-register --name "社内ツールサーバA" --email toolserver-owner@example.com
# 201 {"toolserver_id": 1, ..., "applicant_email": "toolserver-owner@example.com", "status": "pending", ...}

# AIエージェント提供者
python provisional_client.py keygen        # PRIVATE はAIエージェントの作業環境だけで保管する
export AGENT_PRIVATE_KEY='<AIエージェントのPRIVATE>'
python provisional_client.py agent-register --agent-id agent-1 --email agent-owner@example.com
# 201 {"agent_id": "agent-1", ..., "applicant_email": "agent-owner@example.com", "status": "pending", ...}
```

秘密鍵は、ツールサーバ/AIエージェント上だけで保管します。CaPassにも管理者にも渡しません。

### 5.3 管理者が申請内容を確認して承認する

承認待ちの申請は、DBで確認します(承認待ち一覧のAPIは未実装です)。

```sql
SELECT id, tool_server_name, applicant_email, tool_server_public_key, created_at
  FROM tbl_tool_server WHERE status = 'pending';
SELECT agent_id, applicant_email, agent_public_key, created_at
  FROM tbl_agent WHERE status = 'pending';
```

管理者は、**申請者にメールで連絡して、申請した本人であること・申請内容(名称、`agent_id`、公開鍵)に間違いがないことを確認**してから承認します。

> **申請者メールアドレスは、申請者の自己申告で、確認されていません。** 悪意のある人が、自分のアドレスを書いて申請することもできます。申請に書かれたアドレスへの返信だけで判断せず、**社内の名簿や組織図など、申請とは別の経路で調べたアドレス**に確認の連絡をしてください。

```bash
export ADMIN_PRIVATE_KEY='<管理者のPRIVATE>'
python provisional_client.py toolserver-approve --toolserver-id 1
python provisional_client.py agent-approve --agent-id agent-1
# 200 {..., "status": "approved", "approver_email": "admin@example.com", ...}
```

承認すると、承認した管理者のメールアドレス(`tbl_admin.admin_email`)が、`approver_email` として記録されます。承認されていない(`pending` / `revoked`)ツールサーバやAIエージェントは、ツール追加ができません。

### 5.4 ツールを追加する

ツールごとに別のツール代理トークンを発行して、`addtool` します(トークンは省略すると自動発行され、画面に表示されます)。

```bash
export TOOL_SERVER_PRIVATE_KEY='<ツールサーバのPRIVATE>'
python provisional_client.py agent-addtool --agent-id agent-1 \
  --endpoint psql_manager \
  --context "PostgreSQLに部長ロール(psql_manager)で接続し、SQLを実行する。社員・売上など全社データの参照が可能。"
python provisional_client.py agent-addtool --agent-id agent-1 \
  --endpoint psql_terminal_admin \
  --context "PostgreSQLに端末管理者ロール(psql_terminal_admin)で接続し、SQLを実行する。端末台帳の参照・更新が可能。"
# 201 {"tool_endpoint": "psql_manager", "agent_id": "agent-1", ...}
```

発行したトークンは、ツールサーバ側のDB(ツールサーバ付きDB)にも `[認証情報(DBロール)/ツール代理トークン/AIエージェント情報]` として保存する必要があります。`exec` のときにCaPassから渡されるトークンで、ツールサーバが認証情報を引くためです。暫定クライアントはトークンを保存しないので、実運用では保存処理を追加してください。

### 5.5 結果の確認

```sql
SELECT id, tool_server_name, status, applicant_email, approver_email FROM tbl_tool_server;
SELECT agent_id, status, applicant_email, approver_email FROM tbl_agent;
SELECT tool_endpoint, agent_id, locked FROM tbl_agent_tool;
```

`tbl_agent_tool` に、`psql_manager` と `psql_terminal_admin` の2行が `agent-1` に対して登録されていれば成功です。

## 6. レスポンスの意味

| ステータス | 原因 |
|---|---|
| 200 / 201 | 成功(承認は200、登録・追加は201)。承認済みへの再承認も200(冪等で、最初の承認者は書き換わりません) |
| 401 | 署名が不正、または `signed_at` が許容範囲を超えてずれている(時刻同期を確認) |
| 403 | 承認系: 署名した鍵が、`tbl_admin` に登録された有効な管理者の鍵ではない。`addtool`: ツールサーバまたはAIエージェントが未承認(`pending` / `revoked` / 未登録) |
| 404 | `toolserver_id` / `agent_id` が存在しない |
| 409 | すでに登録済み(同じ公開鍵、同じ `agent_id`、同じ `[ツールエンドポイント, AIエージェント]`)、または `revoked` を承認しようとした |
| 422 | リクエストの形式が不正(公開鍵や署名のBase64が不正、メールアドレスの形式が不正、項目の過不足、`agent_id` に使えない文字など) |
| 429 | 初回登録APIのレート制限を超えた。`Retry-After` の秒数が経ってから再試行する |

## 7. 考え方と注意点

- **ロールごとに別のツールエンドポイントとして登録します。** ツールエンドポイントはツールサーバで実際にコマンドを起動する受け口なので、`psql_manager` はツールサーバ側で部長ロールの認証情報、`psql_terminal_admin` は端末管理者ロールの認証情報に対応づけます。AIエージェントはツール一覧の `context`(説明)を見てツールを選ぶので、ロールでできること・できないことを具体的に書いてください。
- **初回登録のAPIは、誰でも呼べます。** 承認待ちになるだけで権限は付きませんが、悪意のある登録を承認してしまうと、その鍵を持つ相手にツールやAIエージェントとしての権限を与えてしまいます。承認前に、5.3 の確認を必ず行ってください。
- **承認済みのツールサーバは、承認済みの任意のAIエージェントにツールを追加できます。** 現状は、AIエージェント提供者の同意を確認する仕組みはありません。
- **`revoked` は、現時点では新規の登録・ツール追加にだけ効きます。** 登録済みのツールの `list executable` / `exec` への反映は、それらの実装時に対応します。`revoked` にするAPIはまだ無く、SQLで更新します(`UPDATE tbl_tool_server SET status = 'revoked' WHERE id = 1;`)。

## 8. 今後置き換わる箇所

| 現在(暫定) | 将来 |
|---|---|
| `provisional_client.py keygen` | CaPassクライアントの `keygen` |
| `provisional_client.py *-register` / `agent-addtool` | CaPassクライアントの `regist` など |
| `provisional_client.py *-approve` | 管理者用のCLI |
| 承認待ちの確認(SQL) | 承認待ち一覧のAPI |
| 管理者の追加・無効化(SQL) | 当面はSQLのまま |

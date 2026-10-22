# CaPass QUICKSTART(暫定版)

> **この文書は暫定版です。** CaPassクライアント(CLI)がまだ未実装のため、キー作成(`keygen`)や各API呼び出しは、暫定クライアント [`examples/provisional_client.py`](examples/provisional_client.py) で代用しています。CLIの実装後に置き換えます。
> 動作するAPIは、下表の9つです(登録・承認・ツール追加、AIエージェントによるツール一覧の取得・実行、ツールサーバのリプレース、ツール代理トークンの更新)。

## 1. 全体像

AIエージェントにツールを使わせるまでに、次の登録と承認が必要です。**ツールサーバ**と**AIエージェント**は、それぞれ自分の公開鍵と申請者のメールアドレスを初回登録(承認待ち)し、**CaPassサーバ管理者**が申請内容を確認して承認して初めて使えるようになります。

| 誰が | API | 内容 |
|---|---|---|
| ツールサーバ提供者 | `POST /api/v1/toolservers/register` | ツールサーバ(公開鍵)の初回登録(承認待ち) |
| CaPassサーバ管理者 | `POST /api/v1/toolservers/{toolserver_id}/approve` | ツールサーバの承認 |
| AIエージェント提供者 | `POST /api/v1/agents/register` | AIエージェント(公開鍵)の初回登録(承認待ち) |
| CaPassサーバ管理者 | `POST /api/v1/agents/{agent_id}/approve` | AIエージェントの承認 |
| ツールサーバ提供者 | `POST /api/v1/agents/{agent_id}/addtool` | 承認済みAIエージェントへのツール追加(承認済みツールサーバのみ) |
| AIエージェント | `GET /api/v1/agents/{agent_id}/tools` | 使用できるツールの一覧(ツールエンドポイントとコンテキスト)の取得 |
| AIエージェント | `POST /api/v1/agents/{agent_id}/exec/{tool_endpoint}` | ツールの実行(CaPassサーバがツールサーバへ中継する) |
| ツールサーバ提供者 | `POST /api/v1/toolservers/{toolserver_id}/chkey` | ツールサーバのリプレース(公開鍵の更新。旧・新の両方の署名) |
| ツールサーバ提供者 | `POST /api/v1/agents/{agent_id}/chtkn/{tool_endpoint}` | ツール代理トークンの更新(ツールサーバの定期更新ジョブ) |

登録の順序は次のとおりです。

1. 管理者を、CaPassサーバのDB(`tbl_admin`)に登録する(最初の1回だけ。以降は、追加・無効化のたびにSQLで更新)
2. ツールサーバとAIエージェントが、それぞれキーペアを作り、自分の公開鍵と申請者のメールアドレスを初回登録する(`pending`)
3. 管理者が、申請者に確認の連絡をしたうえで承認する(`approved`。承認した管理者のメールアドレスが記録される)
4. 承認済みのツールサーバが、承認済みのAIエージェントにツールを追加する
5. AIエージェントが、使用できるツールの一覧を取得し、ツールを選んで実行する(CaPassサーバが、ツールサーバへ中継する)
6. (ツールサーバを新しいサーバに置き換えるとき)登録済みの公開鍵を、新しいサーバの公開鍵に更新する(5.9)
7. ツールサーバが、ツール代理トークンを、定期的に更新する(5.10)

## 2. 署名の仕様

登録・承認・ツール追加のリクエストは、全て **Ed25519の署名付き**です。

- 公開鍵(生32バイト)と署名(64バイト)は、標準Base64で送ります。
- 署名するメッセージは、`エンドポイントごとの固定プレフィックス + 正規化JSON` です。
- 正規化JSONは、**`signature` 以外のボディの全フィールド + URLパスのパラメータ**を、`sort_keys=True` / `separators=(',', ':')` / `ensure_ascii=False` でJSON化し、UTF-8でエンコードしたものです。URLパスのパラメータも署名対象にして、別のリソースへのリクエストの使い回しを防ぎます。
- `signed_at`(UNIX秒)がサーバ時刻から許容範囲(デフォルト300秒)を超えてずれていると拒否されます。

| API | プレフィックス | 署名する鍵 | ボディのフィールド(`signature` を除く) | URLパスのパラメータ |
|---|---|---|---|---|
| `toolservers/register` | `capass-toolserver-register-v1\n` | ツールサーバの秘密鍵 | `tool_server_public_key` `tool_server_name` `tool_server_exec_url` `applicant_email` `signed_at` | なし |
| `toolservers/{toolserver_id}/approve` | `capass-toolserver-approve-v1\n` | 管理者の秘密鍵 | `admin_public_key` `signed_at` | `toolserver_id`(整数) |
| `agents/register` | `capass-agent-register-v1\n` | AIエージェントの秘密鍵 | `agent_id` `agent_public_key` `applicant_email` `signed_at` | なし |
| `agents/{agent_id}/approve` | `capass-agent-approve-v1\n` | 管理者の秘密鍵 | `admin_public_key` `signed_at` | `agent_id`(文字列) |
| `agents/{agent_id}/addtool` | `capass-agent-addtool-v1\n` | ツールサーバの秘密鍵 | `tool_endpoint` `context` `params_schema` `tool_proxy_token` `tool_server_public_key` `signed_at` | `agent_id`(文字列) |
| `toolservers/{toolserver_id}/chkey` | 旧: `capass-toolserver-chkey-old-v1\n`、新: `capass-toolserver-chkey-new-v1\n` | 旧ツールサーバと新ツールサーバの、両方の秘密鍵 | `new_tool_server_public_key` `signed_at`(署名は、旧が `signature`、新が `new_key_signature`) | `toolserver_id`(整数) |
| `agents/{agent_id}/chtkn/{tool_endpoint}` | `capass-agent-chtkn-v1\n` | ツールを登録したツールサーバの秘密鍵 | `tool_proxy_token`(新しいトークン) `tool_server_public_key` `nonce` `signed_at` | `agent_id`、`tool_endpoint`(文字列) |
| `agents/{agent_id}/tools`(GET) | `capass-agent-listtools-v1\n` | AIエージェントの秘密鍵 | なし(ボディが無いので、`signed_at` をヘッダーで送る) | `agent_id`(文字列) |
| `agents/{agent_id}/exec/{tool_endpoint}` | `capass-agent-exec-v1\n` | AIエージェントの秘密鍵 | `params` `nonce` `signed_at` | `agent_id`、`tool_endpoint`(文字列) |

**ツールサーバのリプレース(`chkey`)の署名:** 旧ツールサーバと新ツールサーバが、**同じ内容**に、それぞれの秘密鍵で署名します(プレフィックスは役割ごとに違うので、一方の署名を、もう一方として使い回すことはできません)。署名対象は、`new_tool_server_public_key`、`signed_at`、URLパスの `toolserver_id`、そして**サーバに登録されている旧公開鍵 `old_tool_server_public_key`**(リクエストには含めません)です。

**AIエージェントの署名(`tools` と `exec`):** AIエージェントは、`agents/register` で登録して承認された公開鍵に対応する秘密鍵で署名します。サーバは、`tbl_agent` に登録された公開鍵で検証するので、リクエストに公開鍵は含めません。`agent_id` を知っているだけでは、ツールの一覧も実行もできません。

- **`GET .../tools` は、ボディが無いので、署名をヘッダーで送ります。** `X-CaPass-Signed-At`(署名時刻)と `X-CaPass-Signature`(署名)です。署名対象は `{"agent_id": ..., "signed_at": ...}` です。
- **`exec` は、`nonce` をリクエストごとに新しく作ってください**(16〜128文字の英数字と `-` `_`)。ツール実行は副作用があるので、同じ `[agent_id, nonce]` のリクエストは、2回目以降を `401` で拒否します(盗聴した署名付きリクエストの再送対策)。`params` は、ツールパラメータのJSONオブジェクトです(無い場合は `{}`)。ネストしたオブジェクトや配列も、正規化JSONの規則で署名されます。
- **存在しない `agent_id` は、署名不正と区別せず、どちらも `401` です**(AIエージェントの有無を、未認証の相手に知らせないため)。

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
| `CAPASS_SERVER_TOOL_SERVER_TIMEOUT_SEC` | ツールサーバへの中継の制限時間(秒。接続から応答の受信完了まで) | 60 |
| `CAPASS_SERVER_TOOL_SERVER_MAX_RESPONSE_BYTES` | ツールサーバの応答の最大サイズ(バイト)。超えると502 | 10485760(10MiB) |
| `CAPASS_SERVER_TOOL_SERVER_ALLOW_HTTP` | ツールサーバの実行URLに、`http://` を許可するか(`true` / `false`)。ローカル開発だけ `true` にする | `false` |
| `CAPASS_SERVER_TOKEN_MAX_AGE_SEC` | ツール代理トークンの最大経過時間(秒)。ツールサーバは、これより短い間隔で更新する(5.10) | 300 |

暗号化鍵の作り方:

```bash
python -c "from cryptography.fernet import Fernet; print(Fernet.generate_key().decode())"
```

> **既存のDBがある場合:** `tbl_request_nonce` が新設され、`tbl_tool_server` に `exec_url` が、`tbl_agent_tool` に `params_schema` が追加され、`tbl_agent_tool.tool_endpoint` の長さが128文字になりました。`create_all` は既存のテーブルを変更しないので、開発用DBは作り直してください。

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

ツールが何をできるかは、**DBロールの権限で決まります**。CaPassは「どのAIエージェントがどのツールエンドポイントを使ってよいか」を管理するだけです。DBの権限は、2つの仕組みで絞ります。

| 仕組み | 決めること | SQL |
|---|---|---|
| GRANT | どのテーブルに、何(SELECT / INSERT / UPDATE など)ができるか | `GRANT` |
| 行レベルセキュリティ(RLS) | そのテーブルの、**どの行**に対してできるか | `CREATE POLICY` |

以下の例は、次のテーブルがある前提です(説明用)。

```sql
-- terminals(id, hostname, owner_dept, status)   owner_dept: 端末を所有する部署
-- employees(id, name, dept, salary)
```

**(1) ロールの作成と、GRANT(テーブル単位の権限)**

```sql
CREATE ROLE psql_manager LOGIN PASSWORD '<パスワード>';
GRANT SELECT ON ALL TABLES IN SCHEMA public TO psql_manager;

CREATE ROLE psql_terminal_admin LOGIN PASSWORD '<パスワード>';
GRANT SELECT, INSERT, UPDATE ON terminals TO psql_terminal_admin;
```

**(2) CREATE POLICY(行単位の制限)**

GRANTだけだと、許可したテーブルの**全ての行**が対象になります。行を絞りたいテーブルは、RLSを有効にして、ロールごとにポリシーを作ります。

```sql
ALTER TABLE terminals ENABLE ROW LEVEL SECURITY;
ALTER TABLE terminals FORCE ROW LEVEL SECURITY;  -- テーブルの所有者にも適用する(任意)

-- 端末管理者ロール: 情報システム部(IT)の端末だけ、参照・更新できる。新しく登録できるのも、ITの端末だけ
CREATE POLICY terminals_admin_select ON terminals FOR SELECT TO psql_terminal_admin
  USING (owner_dept = 'IT');
CREATE POLICY terminals_admin_update ON terminals FOR UPDATE TO psql_terminal_admin
  USING (owner_dept = 'IT')          -- 更新できる行(今ある行)
  WITH CHECK (owner_dept = 'IT');    -- 更新後の行(他の部署の端末に、付け替えられない)
CREATE POLICY terminals_admin_insert ON terminals FOR INSERT TO psql_terminal_admin
  WITH CHECK (owner_dept = 'IT');

-- 部長ロール: 全ての端末を参照できる
-- (RLSを有効にしたテーブルは、ポリシーが無いロールには、1行も見えなくなる。そのため、このポリシーが必要)
CREATE POLICY terminals_manager_select ON terminals FOR SELECT TO psql_manager
  USING (true);
```

部署ごとに見せる行を変えたい場合は、**部署ごとにDBロールを分けて**、ロールごとに別のツールエンドポイントとして登録します(例: `psql_sales_manager`)。列を隠したい場合は、列単位のGRANTも使えます。

```sql
-- 営業部の部長ロール: 営業部の社員だけ参照でき、給与(salary)の列は見えない
CREATE ROLE psql_sales_manager LOGIN PASSWORD '<パスワード>';
GRANT SELECT (id, name, dept) ON employees TO psql_sales_manager;

ALTER TABLE employees ENABLE ROW LEVEL SECURITY;
CREATE POLICY employees_sales_select ON employees FOR SELECT TO psql_sales_manager
  USING (dept = '営業部');
CREATE POLICY employees_manager_select ON employees FOR SELECT TO psql_manager
  USING (true);
```

**(3) 確認**(スーパーユーザなどで接続して、ロールを切り替えて確認します)

```sql
SET ROLE psql_terminal_admin;
SELECT owner_dept, count(*) FROM terminals GROUP BY owner_dept;  -- IT だけが見える
INSERT INTO terminals (hostname, owner_dept) VALUES ('pc-001', 'sales');  -- エラー(行レベルセキュリティのポリシーに違反)
RESET ROLE;
```

注意点:

- **テーブルの所有者、スーパーユーザ、`BYPASSRLS` 属性を持つロールには、RLSが適用されません**(所有者は、`FORCE ROW LEVEL SECURITY` で適用できます)。ツールが使うロールは、スーパーユーザや `BYPASSRLS` にしないでください。
- **ポリシーの条件に、セッション変数(`SET app.xxx = ...`)を使うのは避けてください。** AIエージェントが任意のSQLを実行できるツールでは、そのSQLで変数を書き換えて、条件を回避できてしまいます。条件ごとにロールを分けるほうが安全です。
- 上のSQLは、説明用の例です(PostgreSQLの実機では確認していません)。実際のテーブルとロールに合わせて、確認してから使ってください。

### 5.2 ツールサーバ・AIエージェントの鍵を作って、初回登録する

```bash
# ツールサーバ提供者
python provisional_client.py keygen        # PRIVATE はツールサーバ上だけで保管する
export TOOL_SERVER_PRIVATE_KEY='<ツールサーバのPRIVATE>'
python provisional_client.py toolserver-register --name "社内ツールサーバA" \
  --exec-url https://toolserver.example.com/capass/exec --email toolserver-owner@example.com
# 201 {"toolserver_id": 1, ..., "tool_server_exec_url": "https://toolserver.example.com/capass/exec", "status": "pending", ...}

# AIエージェント提供者
python provisional_client.py keygen        # PRIVATE はAIエージェントの作業環境だけで保管する
export AGENT_PRIVATE_KEY='<AIエージェントのPRIVATE>'
python provisional_client.py agent-register --agent-id agent-1 --email agent-owner@example.com
# 201 {"agent_id": "agent-1", ..., "applicant_email": "agent-owner@example.com", "status": "pending", ...}
```

秘密鍵は、ツールサーバ/AIエージェント上だけで保管します。CaPassにも管理者にも渡しません。

`--exec-url` は、**CaPassサーバがツール実行を中継する先のURL**です(既定ではhttpsのみ。ローカル開発で `http://localhost` を使う場合は、サーバの `CAPASS_SERVER_TOOL_SERVER_ALLOW_HTTP=true` が必要)。署名の対象で、登録後に変更できません。

### 5.3 管理者が申請内容を確認して承認する

承認待ちの申請は、DBで確認します(承認待ち一覧のAPIは未実装です)。

```sql
SELECT id, tool_server_name, exec_url, applicant_email, tool_server_public_key, created_at
  FROM tbl_tool_server WHERE status = 'pending';
SELECT agent_id, applicant_email, agent_public_key, created_at
  FROM tbl_agent WHERE status = 'pending';
```

管理者は、**申請者にメールで連絡して、申請した本人であること・申請内容(名称、**実行URL**、`agent_id`、公開鍵)に間違いがないことを確認**してから承認します。

> **申請者メールアドレスは、申請者の自己申告で、確認されていません。** 悪意のある人が、自分のアドレスを書いて申請することもできます。申請に書かれたアドレスへの返信だけで判断せず、**社内の名簿や組織図など、申請とは別の経路で調べたアドレス**に確認の連絡をしてください。

```bash
export ADMIN_PRIVATE_KEY='<管理者のPRIVATE>'
python provisional_client.py toolserver-approve --toolserver-id 1
python provisional_client.py agent-approve --agent-id agent-1
# 200 {..., "status": "approved", "approver_email": "admin@example.com", ...}
```

承認すると、承認した管理者のメールアドレス(`tbl_admin.admin_email`)が、`approver_email` として記録されます。承認されていない(`pending` / `revoked`)ツールサーバやAIエージェントは、ツール追加ができません。

### 5.4 ツールを追加する

ツールごとに、**説明(`context`)、paramsのスキーマ(`params_schema`)、別のツール代理トークン**を指定して、`addtool` します(トークンは省略すると自動発行され、画面に表示されます)。paramsのスキーマの書き方は、5.8 を参照してください。

```bash
# psql_schema.json: ツールのparamsのスキーマ(JSON Schema)
cat > psql_schema.json <<'EOF'
{
  "type": "object",
  "properties": {
    "sql": {"type": "string", "description": "実行するSQL文。1文だけ指定する。例: SELECT id, name FROM employees LIMIT 10"}
  },
  "required": ["sql"],
  "additionalProperties": false
}
EOF

export TOOL_SERVER_PRIVATE_KEY='<ツールサーバのPRIVATE>'
python provisional_client.py agent-addtool --agent-id agent-1 \
  --endpoint psql_manager --params-schema @psql_schema.json \
  --context "PostgreSQLに部長ロール(psql_manager)で接続し、SQLを実行する。社員・売上など全社データの参照が可能。"
python provisional_client.py agent-addtool --agent-id agent-1 \
  --endpoint psql_terminal_admin --params-schema @psql_schema.json \
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

### 5.6 AIエージェントが、ツールの一覧を取得して、実行する

```bash
export AGENT_PRIVATE_KEY='<AIエージェントのPRIVATE>'

# 使用できるツールの一覧(CLIの list executable の代用)
python provisional_client.py agent-tools --agent-id agent-1
# 200 {"agent_id": "agent-1", "tools": [{"tool_endpoint": "psql_manager", "context": "...", "params_schema": {...}}, {"tool_endpoint": "psql_terminal_admin", ...}]}

# ツールの実行(CLIの exec の代用)。nonceは、実行のたびに自動で新しく作られる
python provisional_client.py agent-exec --agent-id agent-1 --endpoint psql_manager --params '{"sql": "SELECT 1"}'
# 200 <ツールサーバの応答がそのまま返る>
```

AIエージェントは、一覧の `context`(ツールの説明)を見て使うツールを選び、`params_schema`(paramsのスキーマ)を見てparamsを組み立て、`tool_endpoint` を指定して実行します。

- **使用できるツールが1件も無い場合(ツールが無い、すべてロックされている、ツールサーバの承認が取り消されている)、一覧は、エラーではなく空のリスト(`"tools": []`)です。**
- **`exec` は、paramsがスキーマに合っていないと、ツールサーバへ中継せずに `422` を返します。** `errors` に、問題の場所と内容が入るので、AIエージェントはそれを見てparamsを直せます。
  ```
  422 {"detail": "params does not match the params_schema of the tool", "errors": ["$: 'sql' is a required property"]}
  ```
- 使用できない(未登録・ロック中・ツールサーバが未承認の)ツールを `exec` した場合は、`403`(権限ありません)です。理由は区別されません。

### 5.7 ツールサーバが実装する仕様(CaPassサーバからの呼び出し)

`exec` のとき、CaPassサーバは、ツールサーバの**実行URL**(`toolservers/register` で登録したURL)へ、次のリクエストを送ります。

```
POST <実行URL>
Authorization: Bearer <ツール代理トークン(平文)>
Content-Type: application/json

{"agent_id": "agent-1", "tool_endpoint": "psql_manager", "params": {"sql": "SELECT 1"}}
```

ツールサーバは、ツール代理トークンから認証情報(DBロールなど)を引き、`agent_id` と `tool_endpoint` がそのトークンに紐づくものと一致することを確認して、ツールを実行します。認証情報の権限(スコープ)の範囲外なら、**`403`** を返してください。

- `params` は、CaPassサーバが、登録された `params_schema` で検証してから送ります。**ツールサーバ側でも、`params` を必ず検証してください**(CaPassサーバを経由しない呼び出しや、スキーマの検証でカバーできない値(SQLの中身など)があるため)。
- **CaPassサーバがツールサーバへ接続する方法は、HTTPS(REST)のみです。** ツール自体の種別(CLI、REST API、A2Aなど)は制限されませんが、種別ごとに、実行URLで待ち受けて、ツールへ変換する「受け口」(アダプタ)が、ツールサーバ側に必要です。受け口は、今はツール提供者が実装します(見本: `examples/fake_tool_server.py`)。CaPassクライアントに、この受け口の機能を持たせる構想は、[`docs/TODO.md`](docs/TODO.md) にあります。

CaPassサーバは、ツールサーバの応答を、次のように扱います。

| ツールサーバの応答 | AIエージェントへ返すもの |
|---|---|
| `2xx` | そのまま中継(ボディとContent-Type)。ツール利用日時を更新する |
| `401` | `403` にして中継(AIエージェント自身の認証失敗と紛らわしいため) |
| その他の `4xx` | そのまま中継 |
| `3xx` / `5xx` | `502`(ツールサーバの内部情報は中継しない)。リダイレクトは追わない |
| 接続できない / 応答サイズ超過 | `502` |
| 制限時間内に応答が無い | `504` |

動作確認には、見本のツールサーバ [`examples/fake_tool_server.py`](examples/fake_tool_server.py) が使えます(`addtool` で登録したトークンを、環境変数で渡して起動します。使い方はファイルの先頭に書いてあります)。

### 5.8 paramsのスキーマ(`params_schema`)の書き方

`params_schema` は、**JSON Schema** で書きます。AIエージェントが、ツールの呼び出しに必要なparamsの組み立て方を理解するための説明であり、CaPassサーバが `exec` のときにparamsを検証する基準にもなります。

JSON Schemaを使う理由は、次のとおりです。

- **AIエージェント向けのツール定義の標準形式です。** MCP(`inputSchema`)、Anthropic(`input_schema`)、OpenAI(`parameters`)が、どれもJSON Schemaを使うので、AIエージェントは、一覧の `params_schema` を、そのままツール定義として扱えます。
- **型・必須・選択肢・範囲を、機械で検証できます。** `{"sql": "実行するSQL文をstring型で格納"}` のような独自の形式は、型や必須かどうかが曖昧で、検証できません。

登録のときに、CaPassサーバが確認するのは、次の点です。

- JSON Schemaとして正しいこと
- ルートが `{"type": "object", "properties": {...}}` であること(パラメータが無いツールは `"properties": {}`)
- **各パラメータに、空でない `description` があること**(AIエージェントが、何を渡すべきか分かるようにするため)
- `$ref` は、スキーマ内の参照(`#` から始まるもの)のみ。外部のスキーマは参照できないこと
- サイズが16KiB以下であること

AIエージェントが読みやすいスキーマにするコツ:

- `description` に、**何を渡すか、どんな形式か、例**を書く(「SQL文」だけでなく「1文だけ指定する。例: `SELECT ...`」など)。単位や、使ってはいけない値もここに書く。
- 選択肢が決まっているものは `enum`、数値の範囲は `minimum` / `maximum`、必須のパラメータは `required` を使う(`description` に書くだけにしない)。
- **`"additionalProperties": false` を付ける**と、AIエージェントが存在しないパラメータを付けたときに、`422` で気づける。
- ツール全体の説明は、スキーマではなく `context` に書く。`context` には、「どんなときに使うか」「何ができて何ができないか」を書く。

```json
{
  "type": "object",
  "properties": {
    "sql":    {"type": "string",  "description": "実行するSQL文。1文だけ指定する。例: SELECT id, name FROM employees LIMIT 10"},
    "limit":  {"type": "integer", "description": "取得する最大行数(1〜1000)", "minimum": 1, "maximum": 1000, "default": 100},
    "format": {"type": "string",  "description": "出力形式", "enum": ["json", "csv"], "default": "json"}
  },
  "required": ["sql"],
  "additionalProperties": false
}
```

`default` は、AIエージェントへの説明です。CaPassサーバは、省略されたパラメータにデフォルト値を補いません(ツールサーバが補います)。

### 5.9 ツールサーバをリプレースする(公開鍵の更新)

ツールサーバを新しいサーバに置き換えるときは、登録済みの公開鍵を、新しいサーバの公開鍵に更新します(`chkey`)。**ステータス(承認済み)、名称、実行URL、登録済みのツールは引き継がれ、管理者の承認のやり直しは不要**です。その代わり、**旧ツールサーバと新ツールサーバの、両方の署名**が必要です(旧: 登録元であることの証明、新: 新しい鍵を持っていることの証明)。

```bash
# 1. 新ツールサーバで、キーペアを作り、新しい鍵の所持を証明する署名(handoff)を作る
python provisional_client.py keygen        # PRIVATE は新ツールサーバ上だけで保管する
export TOOL_SERVER_PRIVATE_KEY='<新ツールサーバのPRIVATE>'
python provisional_client.py toolserver-chkey-prepare --toolserver-id 1 \
  --old-public-key '<旧ツールサーバの公開鍵>' > handoff.json

# 2. handoff.json を旧ツールサーバへ渡して、旧ツールサーバで chkey を実行する
export TOOL_SERVER_PRIVATE_KEY='<旧ツールサーバのPRIVATE>'
python provisional_client.py toolserver-chkey --toolserver-id 1 --handoff @handoff.json
# 200 {"toolserver_id": 1, ..., "tool_server_public_key": "<新ツールサーバの公開鍵>", "status": "approved"}
```

- **署名時刻から数分以内(既定は5分)に、`chkey` を実行してください。** handoff の署名時刻は、旧ツールサーバの署名にも使われます。
- **実行URLは変わりません。** CaPassサーバは、同じURLへ中継を続けるので、新ツールサーバが、**同じURLで待ち受けられる**ようにしてください(DNSやロードバランサの切り替えなど)。実行URLを変える必要がある場合は、管理者が内容を確認して、SQLで更新します(`UPDATE tbl_tool_server SET exec_url = '<新しいURL>' WHERE id = 1;`)。
- **ツールサーバ付きDB(`[認証情報/ツール代理トークン/AIエージェント情報]`)は、新ツールサーバへ移行しておいてください。** CaPassサーバが保存しているツール代理トークンは、そのまま使われます。
- **承認済み(`approved`)のツールサーバだけが、リプレースできます。** `pending` や `revoked` は、`403` です(承認が取り消されたツールサーバが、鍵を更新して復帰することはできません)。
- **更新後は、旧公開鍵は使えません。** 旧ツールサーバからの `addtool` などは、できなくなります。AIエージェントの一覧と実行は、更新後もそのまま使えます。

### 5.10 ツール代理トークンを定期的に更新する(chtkn)

ツール代理トークンは、定期的に新しいものに更新します(漏れたトークンを使える期間を短くするため)。**トークンを発行するのはツールサーバなので、更新もツールサーバが行います**(ツールサーバの定期更新ジョブ)。

1. ツールサーバが、新しいトークンを発行して、ツールサーバ付きDBに保存する
2. ツールサーバが、CaPassサーバへ `chtkn` を呼び出して、そのツールのトークンを更新する

```bash
export TOOL_SERVER_PRIVATE_KEY='<ツールサーバのPRIVATE>'
python provisional_client.py agent-chtkn --agent-id agent-1 --endpoint psql_manager
# new tool_proxy_token(...): <新しいトークン>
# 200 {"tool_endpoint": "psql_manager", "agent_id": "agent-1", "tool_proxy_token_updated_at": "...", "locked": false, "token_max_age_sec": 300}
```

- **更新の間隔:** レスポンスの `token_max_age_sec`(`addtool` のレスポンスにも含まれます。既定300秒、設定は `CAPASS_SERVER_TOKEN_MAX_AGE_SEC`)より短い間隔で、更新してください(余裕を持って、半分程度がお勧めです)。**更新から `token_max_age_sec` を過ぎたトークンをロックする、CaPassサーバの監視ジョブは、まだ実装されていません。** 今は、更新しなくても、ロックされません。
- **更新できるのは、そのツールを登録したツールサーバだけです。** 別のツールサーバが、他のツールを更新しようとすると、「ツールが存在しない」(`404`)と同じ扱いになります(他のツールの有無を知らせないため)。承認が取り消された(`pending` / `revoked`)ツールサーバは、更新できません(`403`)。
- **`nonce` は、リクエストごとに新しく作ってください。** 同じ `nonce` の再利用は `401` です(盗聴した古い更新リクエストの再送で、トークンが古いものに巻き戻るのを防ぐため)。
- **ロック中のツールも、トークンは更新できますが、ロックは解除されません**(レスポンスの `locked` で確認できます)。ロックの解除の操作は、まだありません。
- **ツールごとに、1回ずつ呼びます**(複数のツールをまとめて更新するAPIは、ありません)。トークンは、レスポンスには含まれません。

**ツールサーバ側の実装の注意:** ツールサーバが新しいトークンを保存してから、CaPassサーバの更新が完了するまでの間に、`exec` が来ると、CaPassサーバは、まだ**古いトークン**を送ってきます。そのため、**更新の間は、古いトークンと新しいトークンの、両方を受け付けてください。** CaPassサーバの更新が成功したら、古いトークンを(少し猶予を置いて)無効にします。`chtkn` が失敗したときは、古いトークンを使い続けて、リトライします。

## 6. レスポンスの意味

| ステータス | 原因 |
|---|---|
| 200 / 201 | 成功(承認は200、登録・追加は201)。承認済みへの再承認も200(冪等で、最初の承認者は書き換わりません) |
| 401 | 署名が不正、または `signed_at` が許容範囲を超えてずれている(時刻同期を確認)。`tools` / `exec`: 存在しない `agent_id` も同じ。`exec` / `chtkn`: 同じ `nonce` を再利用した。`chkey`: 旧ツールサーバの署名が不正(存在しない `toolserver_id` も同じ)、または、新しい公開鍵の署名が不正(この場合は、`detail` が `invalid signature of the new public key`) |
| 403 | 承認系: 署名した鍵が、`tbl_admin` に登録された有効な管理者の鍵ではない。`addtool`: ツールサーバまたはAIエージェントが未承認(`pending` / `revoked` / 未登録)。`tools` / `exec`: AIエージェントが未承認。`exec`: 使用できないツール(権限ありません)、またはツールサーバが403/401を返した。`chkey` / `chtkn`: ツールサーバが承認済みではない(`chtkn` は、登録されていない鍵も同じ) |
| 404 | `toolserver_id` / `agent_id` が存在しない。`chtkn`: そのツールサーバのツールが存在しない(別のツールサーバのツールも同じ) |
| 409 | すでに登録済み(同じ公開鍵、同じ `agent_id`、同じ `[ツールエンドポイント, AIエージェント]`)、または `revoked` を承認しようとした。`chkey`: 新しい公開鍵が、すでに登録されている(現在の公開鍵と同じ場合を含む) |
| 422 | リクエストの形式が不正(公開鍵や署名のBase64が不正、メールアドレスの形式が不正、項目の過不足、`agent_id` に使えない文字、`params_schema` が不正など)。`exec`: paramsが、ツールの `params_schema` に合っていない(`errors` に詳細) |
| 429 | 初回登録APIのレート制限を超えた。`Retry-After` の秒数が経ってから再試行する |
| 502 | `exec`: ツールサーバに接続できない、5xx/3xxを返した、応答が大きすぎる |
| 504 | `exec`: ツールサーバが制限時間内に応答しなかった |

## 7. 考え方と注意点

- **ロールごとに別のツールエンドポイントとして登録します。** ツールエンドポイントはツールサーバで実際にコマンドを起動する受け口なので、`psql_manager` はツールサーバ側で部長ロールの認証情報、`psql_terminal_admin` は端末管理者ロールの認証情報に対応づけます。AIエージェントはツール一覧の `context`(説明)を見てツールを選ぶので、ロールでできること・できないことを具体的に書いてください。
- **初回登録のAPIは、誰でも呼べます。** 承認待ちになるだけで権限は付きませんが、悪意のある登録を承認してしまうと、その鍵を持つ相手にツールやAIエージェントとしての権限を与えてしまいます。承認前に、5.3 の確認を必ず行ってください。
- **承認済みのツールサーバは、承認済みの任意のAIエージェントにツールを追加できます。** 現状は、AIエージェント提供者の同意を確認する仕組みはありません。
- **`chkey` は、管理者の承認なしに、公開鍵を更新できます。** そのため、**旧ツールサーバの秘密鍵が漏れると、攻撃者は、自分の鍵に更新して、そのツールサーバのツールを乗っ取れます**(新ツールサーバの署名は、攻撃者が自分の鍵で作れるため)。旧ツールサーバの秘密鍵の保管には、注意してください。乗っ取りが分かった場合は、管理者が `revoked` にします(`chkey` で `revoked` から復帰することはできません)。
- **`revoked` は、直ちに効きます。** ツールサーバが `revoked` になると、そのツールサーバのツールは、`addtool` だけでなく、一覧にも出なくなり、実行もできなくなります。AIエージェントが `revoked` になった場合も、一覧・実行ができなくなります。`revoked` にするAPIはまだ無く、SQLで更新します(`UPDATE tbl_tool_server SET status = 'revoked' WHERE id = 1;`)。
- **ツールサーバの実行URLは、管理者が承認時に確認します。** CaPassサーバは、承認されたURLへ、ツール代理トークン付きでリクエストを送ります。URLが正しいツールサーバのものか(別のホストや、内部の管理用URLを指していないか)を、承認前に必ず確認してください。リダイレクトは追いません。
- **ツール実行は、nonceで再送を防いでいますが、署名時刻の許容範囲内では、nonceの記録がDBに残ります。** 期限切れの記録は、次の `exec` のときに削除されます。

## 8. 今後置き換わる箇所

| 現在(暫定) | 将来 |
|---|---|
| `provisional_client.py keygen` | CaPassクライアントの `keygen` |
| `provisional_client.py *-register` / `agent-addtool` | CaPassクライアントの `regist` など |
| `provisional_client.py toolserver-chkey-prepare` / `toolserver-chkey` | CaPassクライアントの `chkey` |
| `provisional_client.py agent-chtkn` | CaPassクライアントの `chtkn`(ツールサーバの定期更新ジョブから呼ぶ) |
| `provisional_client.py agent-tools` / `agent-exec` | CaPassクライアントの `list executable` / `exec` |
| `provisional_client.py *-approve` | 管理者用のCLI |
| 承認待ちの確認(SQL) | 承認待ち一覧のAPI |
| 管理者の追加・無効化(SQL) | 当面はSQLのまま |

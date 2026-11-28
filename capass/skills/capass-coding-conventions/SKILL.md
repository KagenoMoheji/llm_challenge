---
name: capass-coding-conventions
description: CaPass(AIエージェントのツール利用を判定・管理するCapability Gateway。Python3 / FastAPI / SQLAlchemy)のコードを新規作成・修正・レビューするときに必ず従うコーディング規約。各モジュール冒頭の定型ヘッダ(PYPATH/MODNAME/ROOTPATH)、ディレクトリ構成と層の責務、命名規則、設定(config.py)・エラー・署名付きAPI・DB・テストの作り方を定める。CaPassのPythonファイル、APIエンドポイント、DBテーブル、テストを追加・変更するときは、コードを書く前に必ずこのスキルを読むこと。
---

# CaPass コーディング規約

CaPassのコードを書く・直す・レビューするときの規約。コード中のコメント・docstringは日本語で書く。

## 1. モジュール冒頭の定型ヘッダ(最重要)

`__init__.py` を**除く、全てのPythonモジュール**の冒頭に、次のヘッダを書く。

```python
import os
import inspect
import sys
import time
import traceback
PYPATH = os.path.dirname(os.path.abspath(inspect.getfile(inspect.currentframe())))
MODNAME = os.path.splitext(os.path.basename(inspect.getfile(inspect.currentframe())))[0]

# その他のモジュールやROOTPATHのディレクトリ起点の相対パスでのimport
from fastapi import APIRouter          # ← ここから先に、実際のimportを書く
from capass_server.daemon.common.config import DB_HOST
```

- **使っていなくても、ヘッダの `import` は削除しない。**(`sys` / `time` / `traceback` / `PYPATH` / `MODNAME` が未使用でも残す)
- モジュールdocstringを付ける場合は、ヘッダより前(ファイルの先頭)に置く。
- 実際のimportは、ヘッダの後の `# その他のモジュールや...` コメントの下に書く。同じプロジェクトのモジュールは、パッケージ名(`capass_server.` `capass_core.` `capass_toolserver.` `capass_agent.`)から始まる、**ROOTPATH(そのプロジェクトのディレクトリ)起点の絶対パス**でimportする(相対importは使わない)。他のプロジェクト(例: `toolserver` から `capass_core`)は、**インストールされたパッケージ**としてimportする。
- `common/config.py` は、他モジュールをimportしないので、末尾の `# その他のモジュール...` コメントは不要(ヘッダのみ)。

### ROOTPATH の指定(エントリポイントのモジュールだけ)

`ROOTPATH` の定義と `sys.path.append(ROOTPATH)` は、**実行の起点になるモジュールにだけ**書く。ライブラリとして他から呼ばれるモジュール(`controllers/` `services/` `models/` `schemas/` `common/` など)には書かない。

- サーバ(`server/capass_server/daemon/main.py`)、`capass` コマンド(`core/capass_core/cli/main.py`)
- テスト: `tests/` 配下の全モジュール(`conftest.py` `testlib.py` `(ut|it|st|uat)_(cli|daemon)_<名前>.py`。pytestが直接読み込む起点になるため)

`ROOTPATH` は `PYPATH` の次の行で定義し、コメントと `sys.path.append` は `MODNAME` の後に書く。

```python
PYPATH = os.path.dirname(os.path.abspath(inspect.getfile(inspect.currentframe())))
ROOTPATH = os.path.abspath(f"{PYPATH}/..")
MODNAME = os.path.splitext(os.path.basename(inspect.getfile(inspect.currentframe())))[0]
# 以下のROOTPATHでimportの起点を指定
sys.path.append(ROOTPATH)

# その他のモジュールやROOTPATHのディレクトリ起点の相対パスでのimport
```

- `ROOTPATH` は、プロジェクトのディレクトリ(`pyproject.toml` があるディレクトリ)。`tests/*.py` は、1つ上(`{PYPATH}/..`)。エントリポイントは、パッケージの深さに応じて、`capass_server/daemon/main.py` と `capass_core/cli/main.py` は、2つ上(`{PYPATH}/../..`。`server/`、`core/`)。
- `tests/testlib.py` をimportするテスト(と `conftest.py`)は、`sys.path.append(ROOTPATH)` の次の行に `sys.path.append(PYPATH)  # testlib.py(テスト共通の補助関数)をimportするため` を追加する。
- CaPassのコードをimportしない単体スクリプト(`examples/provisional_client.py`)は、ヘッダのみで `ROOTPATH` は使わない。

## 2. ディレクトリ構成と層の責務

**プロジェクト(`pyproject.toml` を持つディレクトリ)は、モードごとに、別々に配布する。** 各プロジェクトは、`<プロジェクト>/<パッケージ>/` の2層(プロジェクトのディレクトリ + importできるパッケージ)にする。パッケージ名は、`capass_` から始める(他のパッケージと、名前が衝突しないように。モードの検出に、パッケージ名を使う)。各モードのパッケージは、`cli/`(`capass` コマンドの、そのモードのコマンド)と、`daemon/`(常駐プロセス)を持つ。

```
core/                       配布名 capass。共通部品と、capass コマンド
  capass_core/
    cli/
      main.py                 capass コマンドの入口(インストール済みのモードを探して、そのCLIを登録する。同居の確認)
      common/                 共通部品: errors, paths, system(OSの操作), fileio, keys, conf, modes(モードの検出と、同居の確認), systemd, init_steps(initの手順の部品), testing(各プロジェクトのテストで使う補助)
  tests/
toolserver/                 配布名 capass-toolserver(モード: ツールサーバ)
  capass_toolserver/
    cli/
      __init__.py             register(subparsers, context)
      commands/               コマンドごとに1モジュール(MVCのController相当。argparseのサブコマンドを登録する)。init.py に、initの手順(run_init)
    daemon/                   常駐プロセス(受け口)。未実装
  tests/
agent/                      配布名 capass-agent(モード: AIエージェント)。待ち受けの機能は持たない
  capass_agent/cli/{commands/}  未実装
  tests/
server/                     配布名 capass-server(モード: CaPassサーバ)
  capass_server/
    __init__.py               バージョン
    cli/{commands/}           未実装
    daemon/                   RestAPIサーバ(v0.1.5までのサーバ)
      main.py            アプリ生成、lifespan、起動
      routes.py          ルータの登録
      controllers/       HTTPの入出力だけ(api_v1.py, root.py, dependencies.py, error_handlers.py)
      services/          業務ロジック。トランザクション(commit/rollback)の境界
      models/            entities.py(テーブル定義)と mappers.py(DBアクセス)
      schemas/           Pydanticのリクエスト/レスポンス
      common/            横断的な部品(config, globals, db, errors, crypto, signature, rate_limit, tool_client)
  tests/               ut_daemon_*.py / it_daemon_*.py、conftest.py、testlib.py
examples/              暫定クライアントと、ツールサーバの見本。skills/ AI向けスキル
```

- **層の責務(`capass_server.daemon`):** controllers → services → models → common。下の層から、上の層をimportしない。
- **CLIの層(`capass_<モード>.cli`):** `commands/`(引数の定義、表示。Controller相当)→ `capass_core.cli.common`(部品)。業務ルールは、`common` の部品か、モードの `commands/<コマンド>.py` の手順(`run_init`)に書く。

## 3. 命名規則

| 対象 | 規則 | 例 |
|---|---|---|
| テーブル | `tbl_` + 単数形のスネークケース | `tbl_agent_tool` |
| エンティティ(クラス) | `Tbl` + パスカルケース | `TblAgentTool` |
| mapperの関数 | テーブル名に揃える | `find_tbl_agent_tool`, `find_tbl_tool_server_by_public_key`, `insert_tbl_agent` |
| 一意制約 | `uq_<テーブル名>_<カラム>` | `uq_tbl_agent_tool_endpoint_agent` |
| 環境変数 | `CAPASS_SERVER_` + 大文字のスネークケース | `CAPASS_SERVER_DB_HOST` |
| 署名プレフィックス定数 | `SIGN_CONTEXT_<対象>_<操作>` = `b"capass-<対象>-<操作>-v1\n"` | `SIGN_CONTEXT_AGENT_ADDTOOL` |
| JSONのフィールド | スネークケース | `tool_proxy_token` |
| 承認ステータス | `ApprovalStatus`(`pending` / `approved` / `revoked`) | |

- 型ヒントは Python 3.10 以降の書き方(`str | None`, `list[str]`)。
- HTTPレスポンスの `detail` と識別子は英語。コメントとdocstringは日本語。

## 4. 定数と設定

固定値と環境変数由来の値は、置き場所を分ける。

| 置き場所 | 入れるもの | 例 |
|---|---|---|
| `common/globals.py` | アプリ全体で共有する**固定値**(文字列長の上限、入力の正規表現、HTTPのヘッダー名・プレフィックス) | `EMAIL_PATTERN`, `AGENT_ID_MAX_LEN`, `API_V1_PREFIX` |
| `common/signature.py` | 署名の規則に属する固定値 | `SIGN_CONTEXT_*`, `ED25519_*` |
| `common/config.py` | **環境変数**から読む値 | `SIGNATURE_MAX_SKEW_SEC`, `TOOL_SERVER_ALLOW_HTTP` |

- 文字列長の上限は、スキーマの `max_length` とエンティティの `String(...)` で**同じ定数を使う**(食い違いを防ぐ)。数値を直接書かない。
- 2か所以上で使う、または使い回す可能性のある固定値は、`globals.py` に置く。1つのモジュールの中だけで意味を持つ値は、そのモジュールに置いてよい。
- `globals.py` は他のモジュールに依存しない。**`from capass_server.daemon.common.globals import X` と名前を指定してimportする**(`from capass_server.daemon.common import globals` とすると、組み込みの `globals()` を隠してしまう)。

### 設定(環境変数)

- 環境変数は **`common/config.py` だけ**で読む(他のモジュールで `os.environ` を使わない)。必須は `os.environ["..."]`、任意は `os.environ.get("...", デフォルト)`。
- 他のモジュールは `from capass_server.daemon.common.config import X` で使う。
- 設定の意味と注意点は、`config.py` のコメントに書く。環境変数を追加・削除したら、`QUICKSTART.md` の環境変数の表も更新する。

## 5. エラー

- serviceは `common/errors.py` の `ServiceError` のサブクラスを `raise` する。
- HTTPステータスへの変換は `controllers/error_handlers.py` の `_STATUS_BY_ERROR` に追加する(サブクラスを先に書く)。
- 目安: 署名不正=401、権限なし/未承認=403、存在しない=404、重複・状態不正=409、形式不正=422(Pydanticが自動)、レート制限=429、ツールサーバの不達・不正応答=502、ツールサーバのタイムアウト=504。

## 6. 署名付きリクエストのAPI

登録・承認・ツール追加は、Ed25519の署名付きリクエスト。

- リクエストのスキーマは `schemas/base.py` の `SignedRequest` を継承する(全フィールド必須、未知のフィールドは拒否)。
- 署名対象は「`signature` 以外の全フィールド + **URLパスのパラメータ**」。URLパスのパラメータは `signed_payload(**path_params)` で署名対象に含める(別リソースへの署名の使い回しを防ぐ)。
- メールアドレスは `EMAIL_PATTERN` で検証する。`EmailStr` は値を正規化して署名とずれるので使わない。
- 署名の検証は `services/signed_request.py` の `verify_signed_request` / `verify_admin_request` を使い、**DB参照より先に**行う(未認証の相手に、登録の有無などを知らせない)。
- プレフィックスは `common/signature.py` に定義する。新しい署名付きAPIを足したら、`QUICKSTART.md` の署名仕様の表と `examples/provisional_client.py` も更新する。
- **ツールサーバのリプレース**は、ステータス(`approved` / `reserved` / `standby` / `revoked`)で遷移を管理する。`reserved` / `standby` は、期限(`status_expires_at`)を持ち、期限切れは使えない。ステータスの更新は、期待した値のままの場合だけ行う条件つきUPDATE(`update_tbl_tool_server_status`)で、並行リクエストとの競合を検出する。
- **ツール(`tbl_tool`)と、AIエージェントへの割り当て(`tbl_agent_tool`)は、別のテーブル**。ツール代理トークンは、ツール(ロール)単位で、`tbl_tool` が持つ。割り当ては、申請(`pending`)→承認(`approved`)→取り消し(`revoked`)で、申請者メアド(`applicant_email`)と承認者メアド(`approver_email`)を記録する。
- **nonce(`tbl_request_nonce`)は、`scope` で区切る**(AIエージェントのリクエストは `agent:<agent_id>`、ツールのトークン更新は `tool:<tool_endpoint>`)。
- **署名を複数持つリクエスト**(ツールサーバのリプレースなど、複数の鍵が署名する場合)は、`SignedRequest.SIGNATURE_FIELDS` に署名のフィールドを全て列挙して、署名対象から除く。署名する役割ごとに、別の署名プレフィックスを定義する(署名の使い回しを防ぐ)。
- **AIエージェントの署名付きAPI**(`tools` と `exec`)は、`services/signed_request.py` の `verify_agent_request` で認証する(`tbl_agent` に登録された公開鍵で検証する)。存在しない `agent_id` は、署名不正と同じ401にする(AIエージェントの有無を知らせない)。ボディが無いGETの署名は、ヘッダー(`HEADER_SIGNED_AT` / `HEADER_SIGNATURE`)で受ける。
- **副作用のあるリクエスト(ツール実行など)には `nonce` を付け**、`consume_request_nonce` で使用済みにしてから処理する(再送対策)。認証に失敗したリクエストのnonceは記録しない。
- ツールサーバへの中継中は、DBのトランザクション(接続)を保持しない(呼び出しの前に `commit()` する)。
- **`params_schema` では、正規表現(`pattern` / `patternProperties`)を禁止する**(ReDoS対策。認可は、CaPassではなく、リソース側のスコープ・GRANTで行うのが前提)。`$ref` は、`#`、`#/$defs/<名前>`、`#/definitions/<名前>` のみ。スキーマを辿る処理は、キーワードの位置を見て辿る(パラメータ名や、`examples` などのデータの中身を、キーワードと取り違えない)。
- **ツールのparamsは、JSON Schema(`params_schema`)で定義する。** 登録時の検証と、実行時のparamsの検証は `common/params_schema.py` に集約する。スキーマは、AIエージェントへの一覧にも含め、各パラメータに `description` を必須にする。
- ツール代理トークンは、平文でDBに保存・ログ出力・レスポンスしない(`common/crypto.py` で暗号化して保存する)。ツールサーバへ渡すときだけ復号する。

## 7. DB

- 管理者(`tbl_admin`)の追加・無効化は、APIを設けず、SQLで直接行う運用。
- 一意制約違反(`IntegrityError`)は、`rollback()` して業務エラーに変換する。
- マイグレーションツールは未導入。`create_all` は `LOCAL_DEV` / `DEV` のみで、既存のテーブルは変更されない。**テーブルや外部キーを変えたら、開発用DBの作り直しが必要**だと、利用者に伝える。

## 8. テスト

- プロジェクト(`core` `toolserver` `agent` `server`)ごとに、そのディレクトリで `pytest` を実行する。`toolserver` と `agent` のテストは、`capass_core` を、インストールして使う(`pip install -e ./core -e "./toolserver[dev]"`)。システムを変更する処理(ユーザ作成、chownなど)は、`capass_core.cli.common.testing` の `FakeSystemOps` と `make_context` で、差し替えて、実際の `/opt/capass` には触れない。
- 命名: `(ut|it|st|uat)_(cli|daemon)_<名前>.py`。`ut` は単体テスト(外部依存なし)、`it` は結合テスト(`daemon` は `TestClient` + インメモリSQLite)、`st` はシステムテスト、`uat` は受け入れテスト。`cli` は `capass` コマンド(`capass_core.cli` と `capass_<モード>.cli`)、`daemon` は常駐プロセスの、テスト。pytestの設定は `pyproject.toml` の `python_files`。
- 共通のfixtureは `conftest.py`(`session_factory` `client` `admin_priv` `fake_tool_server`)、署名付きボディの作成やDBへの前提データ登録は `testlib.py` に置く。PostgreSQLやネットワークは使わない。
- 新しいAPIには、正常系に加えて、401 / 403 / 404 / 409 / 422 の異常系のテストを書く。署名付きAPIは、改ざん・期限切れ・別リソースへの使い回しも確認する。
- 実行時に差し替えたいモジュール変数は、`monkeypatch.setattr` で、**その値を使っているモジュール**に対して差し替える。
- ツールサーバへのHTTP呼び出しは、結合テストでは `fake_tool_server` で差し替え、実際のHTTP通信の挙動は、ローカルのHTTPサーバを立てた単体テスト(`ut_daemon_tool_client.py`)で確認する。
- 実行できなかったテストがある場合(環境にFastAPI等が無いなど)は、その旨を利用者に明記する。

## 9. バージョンと成果物

- バージョンは、各パッケージ(`capass_core` `capass_toolserver` `capass_agent` `capass_server`)の `__init__.py` の `__version__` に書く(同じ値にそろえる。`pyproject.toml` は動的に読む)。**パッケージ間の依存(`capass==0.1.6`、`capass-toolserver==0.1.6` など)も、同じ値に固定しているので、バージョンを上げるときは、そろえる。** **利用者から指示がない限り変えない。**
- 成果物は、同名のトップディレクトリを持つzip(`capass-v0.1.3-1.zip` など)で渡し、**変更したファイルの一覧**も示す。
- 利用者が依頼していない変更をした場合は、その旨と理由を伝える。

## 10. 新しいPythonファイルを足すときのチェックリスト

1. `__init__.py` 以外なら、冒頭に定型ヘッダ(1.)を書いた。エントリポイント(`main.py` / `tests/`)だけ `ROOTPATH` を書いた。
2. 置き場所が、層の責務(2.)に合っている。依存の向きを逆転させていない。
3. 命名が規則(3.)に合っている。固定値は `globals.py`(長さの上限は、スキーマとエンティティで同じ定数)、環境変数は `config.py` 経由。
4. 新しい業務エラーは `errors.py` と `_STATUS_BY_ERROR` に追加した。
5. テストを足し、`QUICKSTART.md` など関連するドキュメントを更新した。

## 11. CLI(`capass` コマンドと、モード)

- **モードごとに、別のパッケージ(別の配布)にする。** サーバの役割は、`toolserver`(ツールサーバ)/ `agent`(AIエージェントの作業環境)/ `server`(CaPassサーバ)。1つのサーバに、1つだけ。`pip install "capass[toolserver]"` は、`capass`(`core/`。共通部品と `capass` コマンド)と、`capass-toolserver` をインストールする(`[toolserver]` は、追加でインストールする、別のパッケージの名前。コードを書き換えるものではない)。使わないモードのコードは、そのサーバに入らない。
- **`capass` コマンドの入口は `capass_core/cli/main.py`。** 次の順に確認する。(1) インストール済みのモードを、`importlib.util.find_spec("capass_<モード>")` で、**importせずに**検出し(`modes.detect_installed_modes`)、ちょうど1つであることを確認する(`modes.ensure_single_mode`。0個はエラー10、2個以上はエラー11)。(2) このサーバに、別のモードの設定・常駐プロセスが無いことを確認する(`modes.ensure_host_mode`。エラー3)。(3) そのモードの CLI(`capass_<モード>.cli`)だけを、**遅延import**で読み込んで、`register(subparsers, context)` を呼ぶ。他のモードのコードは、読み込まない。`capass_<モード>.cli` が無い、または `register` が無いモードは、「未実装」(エラー9)。`--help` と `--version` は、どの状態でも動く(使えない理由は、`--help` に表示する)。
- **サーバ全体の確認(`ensure_host_mode`):** 別のモードの、(a) `/opt/capass/confs/capass.conf` のモード、(b) `/opt/capass/keys/<モード>.key` / `.pub` のファイル名(権限が無くて調べられない場合は、無いものとして扱う)、(c) 稼働中の常駐プロセス(`systemctl is-active capass.service` のサービスは、設定ファイルのモード。`ps` のコマンドラインは、プログラムが pythonかASGIサーバのものだけを見て、`python -m capass_<モード>`、`capass_<モード>.xxx:app`、`capass-<モード>` の起動の形。エディタやシェルの `-c` などは、誤検出しない)。(c)は、目安(docs/TODO.md の 2.1)。
- **モードのパッケージの規約:** パッケージ名は `capass_<モード>`。`capass_<モード>/cli/__init__.py` に `register(subparsers, context)` を書き、コマンドは `capass_<モード>/cli/commands/<コマンド>.py`(コマンドごとに1モジュール。`register(subparsers)` で、argparseのサブコマンドを登録する。MVCのController相当)に書く。常駐プロセスは `capass_<モード>/daemon/`。依存は、`capass==<同じバージョン>`。パッケージの中の、importエラーは、隠さずに、そのまま表示する(CLIが無いこととは、区別する)。
- **`init`(初期導入)の手順は、モードごとに書く:** `capass_<モード>/cli/commands/init.py` の `run_init(options, context)` に、共通の部品(`capass_core.cli.common.init_steps`: `check_root`、`check_systemd_dir`、`check_not_initialized`、`ensure_service_user`、`create_app_dirs`、`write_wrapper`、`write_file`、`validate_options` など。ほかに `keys.create_key_files`、`systemd.render_unit`、`conf.render_conf`、`modes.ensure_host_mode`)を、組み合わせて書く(AIエージェントは、サービスファイルを作らない、など、モードによって手順が違うため)。共通の `run_init` は、持たない。
- **層:** `capass_core/cli/main.py`(入口。確認、遅延import、引数の解析、エラーの表示)→ `capass_<モード>/cli/commands/`(コマンドの定義と表示)→ `capass_core/cli/common/`(部品)。**下の層から上の層をimportしない**。
- **アプリディレクトリは `/opt/capass` で固定**(オプションで変えられない)。異なるモードの同居を、サーバ全体で防ぐため(Python環境やユーザが違っても検出できる)。確認に失敗したら、何も作らない。
- **システムを変更する処理は、`SystemOps`(root権限が必要な操作: ユーザ作成、chown、サービスやプロセスの確認)を通す。** テストでは、`SystemContext`(場所と `SystemOps`)を差し替える(`capass_core.cli.common.testing` の `FakeSystemOps` と `make_context`)。`main(argv, context, find_spec, load_cli)` に渡す(本番は、全て省略)。OSごとの差(ユーザ作成のコマンド、シェルのパス、サービスファイルの場所)は、`system.py` と `paths.py` に集める。
- **初期導入(`init`)の順序(ツールサーバ):** 確認(root権限、環境、オプション、初期化済みか、別のモードか)を、全て先に行い、失敗したら何も変更しない → ユーザ/グループ → ディレクトリ → 実行ファイル → 鍵 → サービスファイル → **設定ファイル(最後。初期化済みの目印)**。途中で失敗しても、設定ファイルが無いので、再実行できる(既存の鍵は、上書きしない)。
- **権限:** 実行ファイルと設定は、rootの持ち物(実行ユーザが書き換えられない)。`keys/` は 0700、秘密鍵は 0600、ともに実行ユーザの持ち物。ファイルは、一時ファイルに書いてから置き換える(`write_atomic`。秘密鍵が、一時的にも、緩い権限にならない)。
- **エラー:** 業務エラーは `capass_core/cli/common/errors.py` の `CapassCliError`(サブクラスが `exit_code` を持つ)を `raise` する。`main` が、`エラー: ...` を標準エラーに出して、`exit_code` で終了する。終了コード: 0=成功、1=エラー、2=使い方の誤り・オプションの不正、3=モードの同居(サーバ)、4=初期化済み、5=ディレクトリ・ファイルを使えない、6=root権限が必要、7=サポート外の環境、8=OSのコマンドの失敗、9=コマンドが未実装のモード、10=モードがインストールされていない、11=2つ以上のモードがインストールされている。
- **鍵の形式:** Ed25519。秘密鍵・公開鍵とも、生の32バイトをBase64にした1行(CaPassサーバの署名の形式と同じ)。
- **表示は日本語。** ただし、秘密鍵などの機密は、表示しない(保存先だけ表示する)。

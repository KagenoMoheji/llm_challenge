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
from capass_server.common.config import DB_HOST
```

- **使っていなくても、ヘッダの `import` は削除しない。**(`sys` / `time` / `traceback` / `PYPATH` / `MODNAME` が未使用でも残す)
- モジュールdocstringを付ける場合は、ヘッダより前(ファイルの先頭)に置く。
- 実際のimportは、ヘッダの後の `# その他のモジュールや...` コメントの下に書く。他のCaPassモジュールは、`capass_server.` から始まる、**ROOTPATH(`server/`)起点の絶対パス**でimportする(相対importは使わない)。
- `common/config.py` は、他モジュールをimportしないので、末尾の `# その他のモジュール...` コメントは不要(ヘッダのみ)。

### ROOTPATH の指定(エントリポイントのモジュールだけ)

`ROOTPATH` の定義と `sys.path.append(ROOTPATH)` は、**実行の起点になるモジュールにだけ**書く。ライブラリとして他から呼ばれるモジュール(`controllers/` `services/` `models/` `schemas/` `common/` など)には書かない。

- サーバ: `capass_server/main.py`
- テスト: `tests/` 配下の全モジュール(`conftest.py` `testlib.py` `ut_*.py` `it_*.py`。pytestが直接読み込む起点になるため)

`ROOTPATH` は `PYPATH` の次の行で定義し、コメントと `sys.path.append` は `MODNAME` の後に書く。

```python
PYPATH = os.path.dirname(os.path.abspath(inspect.getfile(inspect.currentframe())))
ROOTPATH = os.path.abspath(f"{PYPATH}/..")
MODNAME = os.path.splitext(os.path.basename(inspect.getfile(inspect.currentframe())))[0]
# 以下のROOTPATHでimportの起点を指定
sys.path.append(ROOTPATH)

# その他のモジュールやROOTPATHのディレクトリ起点の相対パスでのimport
```

- `ROOTPATH` は、そのファイルの1つ上のディレクトリ(`capass_server/main.py` も `tests/*.py` も `server/`)。
- `tests/testlib.py` をimportするテスト(と `conftest.py`)は、`sys.path.append(ROOTPATH)` の次の行に `sys.path.append(PYPATH)  # testlib.py(テスト共通の補助関数)をimportするため` を追加する。
- CaPassのコードをimportしない単体スクリプト(`examples/provisional_client.py`)は、ヘッダのみで `ROOTPATH` は使わない。

## 2. ディレクトリ構成と層の責務

```
server/capass_server/
  main.py            アプリ生成、lifespan、起動
  routes.py          ルータの登録
  controllers/       HTTPの入出力だけ(api_v1.py, root.py, dependencies.py, error_handlers.py)
  services/          業務ロジック。トランザクション(commit/rollback)の境界
  models/            entities.py(テーブル定義)と mappers.py(DBアクセス)
  schemas/           Pydanticのリクエスト/レスポンス
  common/            横断的な部品(config, db, errors, crypto, signature, rate_limit)
server/tests/        ut_*.py(単体)、it_*.py(結合)、conftest.py、testlib.py
cli/capass_cli/      CaPassクライアント(未実装)
examples/            暫定クライアント。skills/ AI向けスキル
```

依存の向きは `controllers → services → models → common`(`schemas` は controllers と services から使う)。**下の層から上の層をimportしない**(例: `common` は `services` をimportしない)。

- **controllers:** ルート関数は同期 `def`(DBが同期のSQLAlchemyのため)。`Depends(get_db)` でセッションを受け取り、serviceを呼んで、レスポンススキーマに詰めて返すだけ。業務エラーの `try/except` はルート関数に書かない(`error_handlers.py` に集約)。ボディ検証より前に実行したい共通処理(レート制限など)は、`dependencies.py` の関数を `dependencies=[Depends(...)]` で適用する。
- **services:** 業務ルールを書く。`commit()` はここで呼ぶ。業務エラーは `common/errors.py` の例外を `raise` する。
- **models:** `mappers.py` はクエリと `flush()` までで、`commit()` しない。
- **common:** 他の層に依存しない。

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

## 4. 設定(環境変数)

- 環境変数は **`common/config.py` だけ**で読む(他のモジュールで `os.environ` を使わない)。必須は `os.environ["..."]`、任意は `os.environ.get("...", デフォルト)`。
- 他のモジュールは `from capass_server.common.config import X` で使う。
- 設定の意味と注意点は、`config.py` のコメントに書く。環境変数を追加・削除したら、`QUICKSTART.md` の環境変数の表も更新する。

## 5. エラー

- serviceは `common/errors.py` の `ServiceError` のサブクラスを `raise` する。
- HTTPステータスへの変換は `controllers/error_handlers.py` の `_STATUS_BY_ERROR` に追加する(サブクラスを先に書く)。
- 目安: 署名不正=401、権限なし/未承認=403、存在しない=404、重複・状態不正=409、形式不正=422(Pydanticが自動)、レート制限=429。

## 6. 署名付きリクエストのAPI

登録・承認・ツール追加は、Ed25519の署名付きリクエスト。

- リクエストのスキーマは `schemas/base.py` の `SignedRequest` を継承する(全フィールド必須、未知のフィールドは拒否)。
- 署名対象は「`signature` 以外の全フィールド + **URLパスのパラメータ**」。URLパスのパラメータは `signed_payload(**path_params)` で署名対象に含める(別リソースへの署名の使い回しを防ぐ)。
- メールアドレスは `EMAIL_PATTERN` で検証する。`EmailStr` は値を正規化して署名とずれるので使わない。
- 署名の検証は `services/signed_request.py` の `verify_signed_request` / `verify_admin_request` を使い、**DB参照より先に**行う(未認証の相手に、登録の有無などを知らせない)。
- プレフィックスは `common/signature.py` に定義する。新しい署名付きAPIを足したら、`QUICKSTART.md` の署名仕様の表と `examples/provisional_client.py` も更新する。
- ツール代理トークンは、平文でDBに保存・ログ出力・レスポンスしない(`common/crypto.py` で暗号化して保存する)。

## 7. DB

- 管理者(`tbl_admin`)の追加・無効化は、APIを設けず、SQLで直接行う運用。
- 一意制約違反(`IntegrityError`)は、`rollback()` して業務エラーに変換する。
- マイグレーションツールは未導入。`create_all` は `LOCAL_DEV` / `DEV` のみで、既存のテーブルは変更されない。**テーブルや外部キーを変えたら、開発用DBの作り直しが必要**だと、利用者に伝える。

## 8. テスト

- 命名: `ut_*.py` は単体テスト(外部依存なし)、`it_*.py` は結合テスト(`TestClient` + インメモリSQLite)。pytestの設定は `pyproject.toml` の `python_files`。
- 共通のfixtureは `conftest.py`(`session_factory` `client` `admin_priv`)、署名付きボディの作成やDBへの前提データ登録は `testlib.py` に置く。PostgreSQLやネットワークは使わない。
- 新しいAPIには、正常系に加えて、401 / 403 / 404 / 409 / 422 の異常系のテストを書く。署名付きAPIは、改ざん・期限切れ・別リソースへの使い回しも確認する。
- 実行時に差し替えたいモジュール変数は、`monkeypatch.setattr` で、**その値を使っているモジュール**に対して差し替える。
- 実行できなかったテストがある場合(環境にFastAPI等が無いなど)は、その旨を利用者に明記する。

## 9. バージョンと成果物

- バージョンは `capass_server/__init__.py` の `__version__` だけに書く(`pyproject.toml` は動的に読む)。**利用者から指示がない限り変えない。**
- 成果物は、同名のトップディレクトリを持つzip(`capass-v0.1.2-5.zip` など)で渡し、**変更したファイルの一覧**も示す。
- 利用者が依頼していない変更をした場合は、その旨と理由を伝える。

## 10. 新しいPythonファイルを足すときのチェックリスト

1. `__init__.py` 以外なら、冒頭に定型ヘッダ(1.)を書いた。エントリポイント(`main.py` / `tests/`)だけ `ROOTPATH` を書いた。
2. 置き場所が、層の責務(2.)に合っている。依存の向きを逆転させていない。
3. 命名が規則(3.)に合っている。環境変数は `config.py` 経由。
4. 新しい業務エラーは `errors.py` と `_STATUS_BY_ERROR` に追加した。
5. テストを足し、`QUICKSTART.md` など関連するドキュメントを更新した。

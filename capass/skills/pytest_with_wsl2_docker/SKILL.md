---
name: pytest-with-wsl2-docker
description: WSL2 上の Docker コンテナ (python:3.11-slim) を利用し、ホスト環境 (Windows) に Python や uv、pip 等を一切インストールすることなく、完全隔離されたワンライナーで CaPass (toolserver / server) の Python テスト (pytest) を実行・検証するためのスキル。Google Colab やブラウザ連携は不要で、ミリ秒〜数秒でローカル完結する。
---

# WSL2 + Docker による Python テスト隔離実行スキル

Windows ホスト環境に Python や `uv`、依存パッケージを一切インストールすることなく、WSL2 上の Docker コンテナ（`python:3.11-slim`）を利用して完全隔離された環境で pytest を実行するためのスキルです。

---

## 1. 概要とメリット

本スキルでは、**Google Colab やブラウザ操作は一切不要**です。ローカルの WSL2 + Docker のみで高速にテストが完結します。

| 項目 | 本スキル (WSL2 + Docker) | 従来のホスト実行 / Colab MCP |
|---|---|---|
| **ホスト環境の汚染** | **ゼロ**（Python/uv 等のインストール不要） | ホスト側に Python/uv が必要 |
| **Colab / ブラウザ連携** | **不要**（Google アカウント・Chrome 不要） | Colab タブを開いて接続操作が必要 |
| **実行速度** | **超高速**（ローカルで 0.1 秒未満〜数秒で完了） | クラウド接続・セル追加のオーバーヘッドあり |
| **環境のリセット** | **完全自動**（`--rm` によりコンテナ終了時に破棄） | 残留プロセスやポートの管理が必要 |

---

## 2. 前提条件

- **Windows OS**: Windows 10 / 11
- **WSL2**: 有効化されていること (`wsl --status`)
- **Docker**: WSL2 と連携して稼働していること (`wsl docker --version`)
- **Docker イメージ**: `python:3.11-slim`（または `python:3.13-slim` 等）
  - 初回実行時に自動で pull されます（約 125MB と軽量）。

---

## 3. 即座に使える Docker ワンライナー (PowerShell)

Windows の PowerShell からそのままコピー＆ペーストして実行できるワンライナーです。
（※`-e PYTHONDONTWRITEBYTECODE=1` および `-p no:cacheprovider` により、ホスト側に `__pycache__` や `.pytest_cache` などのゴミファイルを一切生成させません）

### ① `toolserver` 配下のテスト実行 (zip ファイル指定)
共通基盤パッケージ `core`（`capass`）を先行インストールした上で、`toolserver` のテスト（全 6 件）を実行します。

```powershell
wsl docker run --rm `
  -v /mnt/c/Users/${env:USERNAME}/path/to/capass-v0.1.6-3.zip:/tmp/capass.zip:ro `
  -v /mnt/c/Users/${env:USERNAME}/git/llm_challenge/main/llm_challenge/capass/skills/pytest_with_wsl2_docker:/workspace `
  -w /workspace `
  -e PYTHONDONTWRITEBYTECODE=1 `
  python:3.11-slim `
  sh -c "python -m zipfile -e /tmp/capass.zip /tmp/src && pip install --no-cache-dir -e /tmp/src/capass-v0.1.6-3/core && pip install --no-cache-dir -e /tmp/src/capass-v0.1.6-3/toolserver[dev] && pytest -vv -p no:cacheprovider /tmp/src/capass-v0.1.6-3/toolserver/tests"
```

### ② `server` 配下のテスト実行 (zip ファイル指定)
サーバーのテストに必要なインメモリ DB 設定を環境変数として注入し、**Fernet 暗号化鍵はコンテナ内部で動的に自動生成**して環境変数に設定して実行します（固定キー直書き不要）。

```powershell
wsl docker run --rm `
  -v /mnt/c/Users/${env:USERNAME}/path/to/capass-v0.1.6-3.zip:/tmp/capass.zip:ro `
  -v /mnt/c/Users/${env:USERNAME}/git/llm_challenge/main/llm_challenge/capass/skills/pytest_with_wsl2_docker:/workspace `
  -w /workspace `
  -e PYTHONDONTWRITEBYTECODE=1 `
  -e CAPASS_SERVER_ENV=LOCAL_DEV `
  -e CAPASS_SERVER_DB_HOST=127.0.0.1 `
  -e CAPASS_SERVER_DB_PORT=5432 `
  -e CAPASS_SERVER_DB_NAME=capass `
  -e CAPASS_SERVER_DB_USER=capass `
  -e CAPASS_SERVER_DB_PASSWORD=capass `
  python:3.11-slim `
  sh -c "export CAPASS_SERVER_TOKEN_ENCRYPTION_KEYS=\`$(python3 -c 'import base64,secrets;print(base64.urlsafe_b64encode(secrets.token_bytes(32)).decode())') && python -m zipfile -e /tmp/capass.zip /tmp/src && pip install --no-cache-dir -e /tmp/src/capass-v0.1.6-3/server[dev] && pytest -vv -p no:cacheprovider /tmp/src/capass-v0.1.6-3/server/tests"
```

### ③ git リポジトリ上のソースツリーを直接テストする場合
zip ではなく、リポジトリに展開済みのソースコードを直接テストする場合は、リポジトリルートをマウントします。

```powershell
# 1. toolserver のテスト実行 (25 件)
wsl docker run --rm `
  -v /mnt/c/Users/${env:USERNAME}/git/llm_challenge/main/llm_challenge/capass:/workspace `
  -w /workspace `
  -e PYTHONDONTWRITEBYTECODE=1 `
  python:3.11-slim `
  sh -c "pip install --no-cache-dir -e ./core && pip install --no-cache-dir -e ./toolserver[dev] && pytest -vv -p no:cacheprovider ./toolserver/tests"

# 2. server のテスト実行 (218 件)
wsl docker run --rm `
  -v /mnt/c/Users/${env:USERNAME}/git/llm_challenge/main/llm_challenge/capass:/workspace `
  -w /workspace `
  -e PYTHONDONTWRITEBYTECODE=1 `
  -e CAPASS_SERVER_ENV=LOCAL_DEV `
  -e CAPASS_SERVER_DB_HOST=127.0.0.1 `
  -e CAPASS_SERVER_DB_PORT=5432 `
  -e CAPASS_SERVER_DB_NAME=capass `
  -e CAPASS_SERVER_DB_USER=capass `
  -e CAPASS_SERVER_DB_PASSWORD=capass `
  python:3.11-slim `
  sh -c "export CAPASS_SERVER_TOKEN_ENCRYPTION_KEYS=\`$(python3 -c 'import base64,secrets;print(base64.urlsafe_b64encode(secrets.token_bytes(32)).decode())') && pip install --no-cache-dir -e ./server[dev] && pytest -vv -p no:cacheprovider ./server/tests"
```

---

## 4. ワンライナーの技術的ポイント

1. **`__pycache__` および `.pytest_cache` の完全抑止**:
   - ホスト側のソースディレクトリをマウントしてテストを実行すると、通常は Python や pytest が `.pyc` やキャッシュファイルを大量に生成し、git の未追跡ファイルとして散らかってしまいます。
   - `-e PYTHONDONTWRITEBYTECODE=1` を指定することで、コンテナ内の Python インタプリタ全体に対してバイトコードキャッシュの生成を禁止し、**`__pycache__` ディレクトリを一切作成させません**。
   - pytest のオプションに `-p no:cacheprovider` を指定することで、**`.pytest_cache` ディレクトリの生成も完全に抑止**します。
   - これにより、ホスト側の git ワーキングツリーを一切汚さずにテストを完結できます。
2. **Fernet 暗号化鍵のコンテナ内動的自動生成**:
   - `server` の暗号化機能（トークン暗号化）では 32 バイトの URL-safe Base64 文字列（Fernet キー）が必須です。
   - 固定のテスト用ダミーキーをホスト側の Docker 引数に直書きする代わりに、コンテナ内のシェルスクリプト先頭で標準ライブラリ（`secrets`, `base64`）を用いて有効な鍵をミリ秒で動的生成・`export` しています。
   - ホスト環境（Windows）に Python や暗号化ツールをインストールする必要がなく、完全なワンライナーで安全に完結します。
   - （※PowerShell から実行する際、`$(...)` が PowerShell のサブ式として解釈されないよう `` `$(...) `` とエスケープしています）
3. **`python -m zipfile -e` での展開**:
   - `python:3.11-slim` などの軽量コンテナには `unzip` コマンドが入っていませんが、Python 標準の `zipfile` CLI を利用することで、追加パッケージをインストールすることなく高速・確実に解凍できます。
4. **コンテナ内 `/tmp` での作業完結**:
   - 解凍先や pip のビルド成果物はすべてコンテナ内の `/tmp` で処理されるため、ホスト側のマウント元ディレクトリにゴミファイルが一切残りません。
5. **`--rm` による自動破棄**:
   - テスト完了（またはエラー終了）と同時にコンテナが自動的に破棄されるため、リソースの解放やプロセス管理が不要です。

---

## 5. ヘルパースクリプトによる実行 (`scripts/run_docker_pytest.ps1`)

長大なワンライナーを毎回手動で組み立てる代わりに、同梱の PowerShell スクリプトを利用して手軽にテストを実行できます（内部で `PYTHONDONTWRITEBYTECODE=1` および `-p no:cacheprovider` が自動適用されます）。

```powershell
# zip を指定して toolserver のテストを実行
.\scripts\run_docker_pytest.ps1 -ZipPath "C:\path\to\capass-v0.1.6-3.zip" -Target toolserver

# zip を指定して server のテストを実行
.\scripts\run_docker_pytest.ps1 -ZipPath "C:\path\to\capass-v0.1.6-3.zip" -Target server

# zip を指定せず、ローカルのリポジトリツリーを直接テスト (toolserver)
.\scripts\run_docker_pytest.ps1 -Target toolserver

# zip を指定せず、ローカルのリポジトリツリーを直接テスト (server)
.\scripts\run_docker_pytest.ps1 -Target server
```

---

## 6. zip の受け渡し仕様と期待ディレクトリ構造

### ① `toolserver` が期待する構造
共通基盤パッケージ `core`（`capass`）が存在している必要があります。
```text
capass-vX.Y.Z/                     # 任意の親フォルダ名
├── core/                          # [必須] 共通基盤パッケージ (capass)
│   ├── capass_core/
│   │   └── __init__.py            # __version__ = "X.Y.Z"
│   └── pyproject.toml             # name = "capass"
└── toolserver/                    # [必須] ツールサーバーパッケージ
    ├── capass_toolserver/
    │   ├── __init__.py            # __version__ = "X.Y.Z"
    │   ├── cli/
    │   └── daemon/
    ├── pyproject.toml             # dependencies = ["capass==X.Y.Z"]
    └── tests/                     # テストコード (it_cli.py 等)
```

### ② `server` が期待する構造
```text
capass-vX.Y.Z/                     # 任意の親フォルダ名
└── server/                        # [必須] サーバーパッケージ
    ├── capass_server/             # パッケージルート
    │   ├── __init__.py            # [必須] __version__ の定義
    │   ├── main.py                # FastAPI アプリ (app)
    │   ├── controllers/
    │   ├── services/
    │   ├── models/
    │   ├── schemas/
    │   └── common/
    ├── pyproject.toml             # name = "capass-server", version = {attr = "capass_server.__version__"}
    └── tests/                     # テストコード (conftest.py, it_*.py 等)
```

---

## 7. 実行結果実例 (`toolserver` 6 passed / 0.08s)

詳細ログ: [resources/sample_result_toolserver.txt](resources/sample_result_toolserver.txt)

```text
============================= test session starts ==============================
platform linux -- Python 3.11.18, pytest-9.2.0, pluggy-1.7.0 -- /usr/local/bin/python3.11
cachedir: .pytest_cache
rootdir: /tmp/src/capass-v0.1.6-3/toolserver
configfile: pyproject.toml
collecting ... collected 6 items

../tmp/src/capass-v0.1.6-3/toolserver/tests/it_cli.py::test_init_spec_describes_the_receiver_service PASSED [ 16%]
../tmp/src/capass-v0.1.6-3/toolserver/tests/it_cli.py::test_capass_init_with_the_real_toolserver_cli PASSED [ 33%]
../tmp/src/capass-v0.1.6-3/toolserver/tests/it_cli.py::test_init_help_names_the_mode PASSED [ 50%]
../tmp/src/capass-v0.1.6-3/toolserver/tests/it_cli.py::test_help_lists_init_as_a_toolserver_command PASSED [ 66%]
../tmp/src/capass-v0.1.6-3/toolserver/tests/it_cli.py::test_init_is_refused_on_a_server_that_is_set_up_as_an_agent PASSED [ 83%]
../tmp/src/capass-v0.1.6-3/toolserver/tests/it_cli.py::test_daemon_package_exists_but_is_not_implemented_yet PASSED [100%]

============================== 6 passed in 0.08s ===============================
```

---

## 8. ディレクトリ資材構成

```
skills/pytest_with_wsl2_docker/
├── SKILL.md                          # 本仕様書 (ワンライナー、仕組み、期待構造、実行例)
├── scripts/
│   └── run_docker_pytest.ps1         # PowerShell 用実行ヘルパースクリプト
└── resources/
    └── sample_result_toolserver.txt  # Docker コンテナ内での実行結果ログ実例 (6 passed)
```

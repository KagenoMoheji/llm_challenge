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

### ① `toolserver` 配下のテスト実行 (zip ファイル指定)
共通基盤パッケージ `core`（`capass`）を先行インストールした上で、`toolserver` のテスト（全 6 件）を実行します。

```powershell
wsl docker run --rm `
  -v /mnt/c/Users/${env:USERNAME}/path/to/capass-v0.1.6-3.zip:/tmp/capass.zip:ro `
  -v /mnt/c/Users/${env:USERNAME}/git/llm_challenge/main/llm_challenge/capass/skills/pytest_with_wsl2_docker:/workspace `
  -w /workspace `
  python:3.11-slim `
  sh -c "python -m zipfile -e /tmp/capass.zip /tmp/src && pip install --no-cache-dir -e /tmp/src/capass-v0.1.6-3/core && pip install --no-cache-dir -e /tmp/src/capass-v0.1.6-3/toolserver[dev] && pytest -vv /tmp/src/capass-v0.1.6-3/toolserver/tests"
```

### ② `server` 配下のテスト実行 (zip ファイル指定)
サーバーのテストに必要なインメモリ DB 設定および Fernet 暗号化鍵をコンテナ起動時（`-e` オプション）に環境変数として注入して実行します。

```powershell
wsl docker run --rm `
  -v /mnt/c/Users/${env:USERNAME}/path/to/capass-v0.1.6-3.zip:/tmp/capass.zip:ro `
  -v /mnt/c/Users/${env:USERNAME}/git/llm_challenge/main/llm_challenge/capass/skills/pytest_with_wsl2_docker:/workspace `
  -w /workspace `
  -e CAPASS_SERVER_ENV=LOCAL_DEV `
  -e CAPASS_SERVER_DB_HOST=127.0.0.1 `
  -e CAPASS_SERVER_DB_PORT=5432 `
  -e CAPASS_SERVER_DB_NAME=capass `
  -e CAPASS_SERVER_DB_USER=capass `
  -e CAPASS_SERVER_DB_PASSWORD=capass `
  -e CAPASS_SERVER_TOKEN_ENCRYPTION_KEYS="dGVzdF9mZXJuZXRfa2V5XzMyYnl0ZXNfbG9uZ19mb3JfdGVzdHM9" `
  python:3.11-slim `
  sh -c "python -m zipfile -e /tmp/capass.zip /tmp/src && pip install --no-cache-dir -e /tmp/src/capass-v0.1.6-3/server[dev] && pytest -vv /tmp/src/capass-v0.1.6-3/server/tests"
```

### ③ git リポジトリ上のソースツリーを直接テストする場合
zip ではなく、リポジトリに展開済みのソースコードを直接テストする場合は、リポジトリルートをマウントします。

```powershell
wsl docker run --rm `
  -v /mnt/c/Users/${env:USERNAME}/git/llm_challenge/main/llm_challenge/capass:/workspace `
  -w /workspace `
  python:3.11-slim `
  sh -c "pip install --no-cache-dir -e ./core && pip install --no-cache-dir -e ./toolserver[dev] && pytest -vv ./toolserver/tests"
```

---

## 4. ワンライナーの技術的ポイント

1. **`python -m zipfile -e` での展開**:
   - `python:3.11-slim` などの軽量コンテナには `unzip` コマンドが入っていませんが、Python 標準の `zipfile` CLI を利用することで、追加パッケージをインストールすることなく高速・確実に解凍できます。
2. **コンテナ内 `/tmp` での作業完結**:
   - 解凍先や pip のビルド成果物はすべてコンテナ内の `/tmp` で処理されるため、ホスト側のマウント元ディレクトリにゴミファイルが一切残りません。
3. **`--rm` による自動破棄**:
   - テスト完了（またはエラー終了）と同時にコンテナが自動的に破棄されるため、リソースの解放やプロセス管理が不要です。

---

## 5. ヘルパースクリプトによる実行 (`scripts/run_docker_pytest.ps1`)

長大なワンライナーを毎回手動で組み立てる代わりに、同梱の PowerShell スクリプトを利用して手軽にテストを実行できます。

```powershell
# zip を指定して toolserver のテストを実行
.\scripts\run_docker_pytest.ps1 -ZipPath "C:\path\to\capass-v0.1.6-3.zip" -Target toolserver

# zip を指定して server のテストを実行
.\scripts\run_docker_pytest.ps1 -ZipPath "C:\path\to\capass-v0.1.6-3.zip" -Target server

# zip を指定せず、ローカルのリポジトリツリーを直接テスト
.\scripts\run_docker_pytest.ps1 -Target toolserver
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

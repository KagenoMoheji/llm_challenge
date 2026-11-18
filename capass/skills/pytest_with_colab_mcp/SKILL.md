---
name: mcp-colab-pytest
description: Google Colab の MCP (colab-mcp) を利用して、ローカルマシン環境を汚さずにリモートの Google Colab インスタンス上で Python パッケージ（CaPass 等）の依存関係インストールおよび pytest テストを自動実行・検証するためのスキル。初期導入手順、MCP設定ファイル、zip受け渡し手順と期待ディレクトリ構造、残留プロセスクリーンアップ、toolserver と server の個別アトミック実行スクリプト、Windows の IPv4/IPv6 ポート不一致回避パッチ、接続タイムアウト延長、マルチパッケージ依存関係解決、環境変数セットアップの手順と実行ログ実例を含む。
---

# Google Colab MCP pytest 実行スキル

Google Colab を MCP (Model Context Protocol) 経由でリモート実行環境として利用し、ローカル PC（Windows など）の環境を汚すことなく、Linux / Python 3.13 上でプロジェクトコードの展開、依存関係のインストール、テスト実行（pytest）、および結果収集を自動化するための導入手順とノウハウをまとめたスキルです。

`toolserver` と `server` のテストは、それぞれ独立した専用スクリプトによる**アトミック（個別・安全）な構成**となっており、個別実行・個別タブでの検証が可能です。

---

## 1. Google Colab MCP 初回導入・セットアップ手順

Colab MCP (`googlecolab/colab-mcp`) をローカル環境から利用可能にするための初期セットアップ手順です。

### ① 前提ツールのインストール
1. **Python パッケージマネージャー `uv`** (推奨):
   - Windows (PowerShell):
     ```powershell
     powershell -ExecutionPolicy ByPass -c "irm https://astral.sh/uv/install.ps1 | iex"
     ```
   - インストール後、`uv --version` で動作確認を行います。
2. **Git**:
   - `colab-mcp` は GitHub から動的に取得されるため、`git --version` が実行できる状態にしてください。
3. **Google Chrome**:
   - Google アカウントにログイン済みで、[Google Colab](https://colab.research.google.com/) にアクセス可能な状態にしてください。

### ② MCP クライアントへの登録設定 (`config/mcp.json`)
Cursor や Claude Desktop、Antigravity などの MCP 設定ファイル（`mcp.json`）に `colab-mcp` を登録します。設定原本は [config/mcp.json](config/mcp.json) に配置されています。

```json
{
  "mcpServers": {
    "colab-mcp": {
      "command": "uvx",
      "args": [
        "git+https://github.com/googlecolab/colab-mcp"
      ],
      "timeout": 120000
    }
  }
}
```

- **Cursor の場合**: `%USERPROFILE%\.cursor\mcp.json` に上記を記述します。
- **Claude Desktop の場合**: `%APPDATA%\Claude\claude_desktop_config.json` の `mcpServers` に上記を記述します。
- **スタンドアロンスクリプト / uv run の場合**:
  直接 `uv run --with git+https://github.com/googlecolab/colab-mcp ...` でスクリプトを実行できるため、グローバルなインストールは不要です。

### ③ 提供される MCP ツール一覧 (`config/colab_mcp_tools.json`)
Colab 連携確立後、以下の 8 つのツールが MCP 経由で呼び出し可能になります（スキーマ詳細は [config/colab_mcp_tools.json](config/colab_mcp_tools.json) 参照）：

| ツール名 | 説明 |
|---|---|
| `open_colab_browser_connection` | Colab ブラウザ接続を開き、ノートブック操作ツール群を初期化 |
| `add_code_cell` | 指定位置にコードセルを挿入し、新しい `cellId` を返却 |
| `add_text_cell` | 指定位置にテキスト/Markdown セルを挿入 |
| `run_code_cell` | 指定された `cellId` のコードを実行し、標準出力・エラー出力を取得 |
| `get_cells` | ノートブック内の全セルまたは指定範囲のセル情報を取得 |
| `update_cell` | 既存セルの内容を更新 |
| `move_cell` | セルの配置順序を変更 |
| `delete_cell` | 指定された `cellId` のセルを削除 |

---

## 2. zip ファイル受け渡し手順と期待するディレクトリ構造

テスト対象コードを zip ファイルとして受け渡し、Colab 上で自動展開・実行する際のルールと期待構造です。

### ① zip 作成・受け渡しの手順
1. **ソースコードの圧縮**:
   - ルートにバージョン名付きディレクトリ（例: `capass-v0.1.6-3/`）を含めた形で zip 化します（直下に直接 `core/` や `server/` を置くのではなく、親ディレクトリで1段ラップします）。
   - PowerShell での圧縮コマンド例:
     ```powershell
     Compress-Archive -Path "capass-v0.1.6-3" -DestinationPath "capass-v0.1.6-3.zip" -Force
     ```
2. **受け渡しと事前検証**:
   - zip をローカル作業ディレクトリに配置します。
   - 実行前に `scripts/inspect_zip.py` で内部構造とテストファイルの存在を確認します:
     ```powershell
     uv run --python 3.13 python scripts/inspect_zip.py path\to\capass-v0.1.6-3.zip --filter "tests/"
     ```

### ② 各スクリプトが期待する zip 内のディレクトリ構造

#### 1. `run_colab_toolserver.py` が期待する構造
`toolserver` は共通基盤パッケージ `capass`（`core/` 配下）に依存しています。そのため、以下の構造を前提としています。

```text
capass-vX.Y.Z/                     # 任意のルートフォルダ名 (スクリプトが自動検出)
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
    └── tests/                     # テストコード
        └── it_cli.py
```
> **処理の仕組み**: スクリプトは `core/` の存在を確認すると、まず `pip install -e core` で共通パッケージを Colab 環境に登録し、その後に `pip install -e toolserver[dev]` でツールサーバーの依存を解決して pytest を実行します。

#### 2. `run_colab_server.py` が期待する構造
`server` は CaPass サーバー本体です。以下の構造を前提としています。

```text
capass-vX.Y.Z/                     # 任意のルートフォルダ名 (スクリプトが自動検出)
└── server/                        # [必須] サーバーパッケージ
    ├── capass_server/             # パッケージルート
    │   ├── __init__.py            # [必須] __version__ の定義 (例: __version__ = "X.Y.Z")
    │   ├── main.py                # FastAPI アプリ (app)
    │   ├── controllers/           # API コントローラー
    │   ├── services/              # 業務ロジック
    │   ├── models/                # DB エンティティ・マッパー
    │   ├── schemas/               # Pydantic スキーマ
    │   └── common/                # DB, config, crypto, signature, rate_limit 等
    ├── pyproject.toml             # name = "capass-server", version = {attr = "capass_server.__version__"}
    └── tests/                     # テストコード (conftest.py, it_*.py, ut_*.py 等)
```
> **重要ポイント**:
> - `pyproject.toml` の `version = {attr = "capass_server.__version__"}` を解決するため、`capass_server/__init__.py` にバージョンが定義されている必要があります（中間階層に置く場合は `__init__.py` でインポートが必要）。
> - `tests/` 配下のテストコードが `from capass_server.main import app` や `from capass_server.common.db import Base` で import しているため、パッケージルート直下にこれらのモジュール・ディレクトリが配置されている必要があります。

---

## 3. 残留プロセスの停止・クリーンアップ手順 (重要)

### なぜクリーンアップが必要か？
`colab-mcp` は内部でローカル WebSocket サーバーをポートバインドし、ブラウザからの接続待機を行います。テストの中断・キャンセルや連続実行を行った際、バックグラウンドに `python.exe` や `uv.exe` のプロセスが残っていると、以下の問題が発生します：
- ポートの競合（`OSError: [Errno 10048] 通常、各ソケット アドレスに対してプロトコル、ネットワーク アドレス、またはポートの重複使用は許可されません`）
- ブラウザが古いセッションへ接続してしまいタイムアウトや初期化エラーになる

### 実行前クリーンアップコマンド
新しいテストを実行する前や、テストを中断・再試行する際は、**必ず事前に以下のコマンドを実行して残留プロセスを終了**させてください。

```powershell
powershell -ExecutionPolicy Bypass -Command "Stop-Process -Name 'python','uv' -Force -ErrorAction SilentlyContinue; Write-Output 'CLEANUP_OK'"
```

---

## 4. コマンド実行手順

### ① 前処理（プロセスクリーンアップ）
```powershell
powershell -ExecutionPolicy Bypass -Command "Stop-Process -Name 'python','uv' -Force -ErrorAction SilentlyContinue; Write-Output 'CLEANUP_OK'"
```

### ② `toolserver` 配下のテスト実行
CLI初期化、systemd設定生成、モード判定等のテストを実行します（共通基盤 `core` が自動で先行インストールされます）。

```powershell
uv run --python 3.13 --with git+https://github.com/googlecolab/colab-mcp python scripts/run_colab_toolserver.py path\to\capass-v0.1.6-3.zip
```

### ③ `server` 配下のテスト実行
CaPass サーバー本体の API / 認証 / DB / レート制限等のテスト（218件）を実行します（テスト用インメモリ DB 設定および Fernet 暗号化鍵が自動注入されます）。

```powershell
uv run --python 3.13 --with git+https://github.com/googlecolab/colab-mcp python scripts/run_colab_server.py path\to\capass-v0.1.6-3.zip
```

### ④ zip 内ファイルの事前確認・調査
zip を展開することなく、内部のファイル構成や特定ファイルの内容を確認できます。

```powershell
# テストファイル一覧の確認
uv run --python 3.13 python scripts/inspect_zip.py path\to\capass-v0.1.6-3.zip --filter "tests/"

# 特定ファイル (例: pyproject.toml) の中身を表示
uv run --python 3.13 python scripts/inspect_zip.py path\to\capass-v0.1.6-3.zip --read "server/pyproject.toml"
```

---

## 5. 解決済みの重要ノウハウ・トラブルシューティング (必読)

本スキルのスクリプト（`run_colab_toolserver.py` / `run_colab_server.py`）には、以下の問題に対する解決策が標準で組み込まれています。

### ① Windows 特有の IPv4/IPv6 デュアルスタック・ポート不一致バグ
- **現象**: Windows 環境で `websockets.serve(host='localhost', port=0)` を実行すると、OS 内部で IPv4 (`127.0.0.1`) と IPv6 (`::1`) に対し**異なるランダムポート番号**が割り当てられる。Chrome が IPv6 で接続した際にポート番号が一致せず `ECONNREFUSED`（接続拒否）が発生する。
- **対処法**: 事前に `socket` で空きポートを1つ確保し、同一ポート番号を固定で渡すモンキーパッチ（`_patched_aenter`）を適用しています。

### ② Colab 接続待機タイムアウトの延長
- **現象**: デフォルトの接続待機時間が 60 秒と短く、Colab タブを開いてランタイム初期化・接続ボタンをクリックする前にタイムアウトして内部タスクが `CancelledError` で終了する。
- **対処法**: 待機時間を 300 秒（5分）に延長しています (`colab_mcp.session.UI_CONNECTION_TIMEOUT = 300.0`)。

### ③ Windows コンソール文字コード (CP932) での UnicodeEncodeError
- **現象**: pytest や pip install の出力にリッチな罫線文字（`╰` など）が含まれる場合、Windows の標準出力エンコーディング（CP932）で `UnicodeEncodeError` が発生してスクリプトが落ちる。
- **対処法**: スクリプト冒頭で `sys.stdout.reconfigure(encoding="utf-8", errors="replace")` を行い、さらに `safe_print` 関数で安全に出力を行っています。

### ④ マルチパッケージ構成のローカル依存解決順序
- **現象**: `capass-toolserver` が `capass==0.1.6`（`core/` に存在するパッケージ）に依存している場合、PyPI には未登録のため直接 `pip install -e ./toolserver` を行うと依存解決エラーとなる。
- **対処法**: Colab 側の実行セル内で、先に共通コアである `core` を editable インストールし、その後に `toolserver` をインストールする手順を自動化しています。

### ⑤ テスト実行に必要な環境変数の自動注入
- **現象**: `server/` 配下のテスト実行時、DB 接続設定や暗号化鍵が環境変数から読み込まれる。設定が存在しないと設定初期化時にエラーとなる。
- **対処法**: インメモリ SQLite 設定および自動生成した Fernet 暗号化鍵を `os.environ` に注入して pytest を起動します。

---

## 6. 出力ログ例

### 例1: `capass-v0.1.6-3/toolserver` 配下のテスト実行 (6 passed)
詳細ログ: [resources/sample_result_toolserver.txt](resources/sample_result_toolserver.txt)

```text
============================= test session starts ==============================
platform linux -- Python 3.13.18, pytest-8.4.2, pluggy-1.7.0 -- /usr/bin/python3
rootdir: /content/capass-src/capass-v0.1.6-3/toolserver
collected 6 items

tests/it_cli.py::test_init_spec_describes_the_receiver_service PASSED    [ 16%]
tests/it_cli.py::test_capass_init_with_the_real_toolserver_cli PASSED    [ 33%]
tests/it_cli.py::test_init_help_names_the_mode PASSED                    [ 50%]
tests/it_cli.py::test_help_lists_init_as_a_toolserver_command PASSED     [ 66%]
tests/it_cli.py::test_init_is_refused_on_a_server_that_is_set_up_as_an_agent PASSED [ 83%]
tests/it_cli.py::test_daemon_package_exists_but_is_not_implemented_yet PASSED [100%]

============================== 6 passed in 0.11s ===============================
PYTEST_EXIT 0
```

### 例2: `capass-v0.1.5-4/server` 配下のテスト実行 (218 passed)
詳細ログ: [resources/sample_result_server.txt](resources/sample_result_server.txt)

```text
============================= test session starts ==============================
platform linux -- Python 3.13.18, pytest-8.4.2, pluggy-1.7.0 -- /usr/bin/python3
rootdir: /content/capass-src/capass-v0.1.5-4/server
collected 218 items

tests/it_agent.py ................                                       [  7%]
tests/it_agent_exec.py ..................................                [ 22%]
tests/it_agent_grant.py ..................                               [ 31%]
tests/it_agent_tools.py ..............                                   [ 37%]
tests/it_rate_limit.py ........                                          [ 40%]
tests/it_root.py .                                                       [ 41%]
tests/it_tool_addtool.py ..........                                      [ 45%]
tests/it_tool_chtkn.py ...............                                   [ 52%]
tests/it_toolserver.py .................                                 [ 61%]
tests/it_toolserver_replace.py ........................                  [ 72%]
tests/ut_crypto.py ......                                                [ 75%]
tests/ut_globals.py .....                                                [ 77%]
tests/ut_params_schema.py ........................                       [ 88%]
tests/ut_rate_limit.py ...........                                       [ 93%]
tests/ut_signature.py .......                                            [ 96%]
tests/ut_tool_client.py ........                                         [100%]

============================= 218 passed in 10.69s =============================
PYTEST_EXIT 0
```

---

## 7. ディレクトリ・資材構成

Git コミット対象の正式な資材構成です。

```
skills/pytest_with_colab_mcp/
├── SKILL.md                          # 本ドキュメント (初期導入、zip仕様、プロセス管理、個別実行コマンド、ノウハウ)
├── config/
│   ├── mcp.json                      # Cursor / Claude Desktop 等の MCP 設定ファイル見本
│   └── colab_mcp_tools.json          # Colab MCP 提供ツールの全スキーマ定義
├── scripts/
│   ├── run_colab_toolserver.py       # toolserver 専用 Colab テスト実行スクリプト
│   ├── run_colab_server.py           # server 専用 Colab テスト実行スクリプト
│   └── inspect_zip.py                # zip 内部ファイル閲覧ユーティリティ
└── resources/
    ├── sample_result_toolserver.txt  # toolserver テスト実行ログ実例 (6 passed)
    └── sample_result_server.txt      # server テスト実行ログ実例 (218 passed)
```

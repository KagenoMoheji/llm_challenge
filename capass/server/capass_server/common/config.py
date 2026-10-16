import os
import inspect
import sys
import time
import traceback
PYPATH = os.path.dirname(os.path.abspath(inspect.getfile(inspect.currentframe())))
MODNAME = os.path.splitext(os.path.basename(inspect.getfile(inspect.currentframe())))[0]

# アプリ実行環境
ENV_TYPE = os.environ["CAPASS_SERVER_ENV"]

# DB設定
DB_HOST = os.environ["CAPASS_SERVER_DB_HOST"]
DB_PORT = int(os.environ["CAPASS_SERVER_DB_PORT"])
DB_NAME = os.environ["CAPASS_SERVER_DB_NAME"]
DB_USER = os.environ["CAPASS_SERVER_DB_USER"]
DB_PASSWORD = os.environ["CAPASS_SERVER_DB_PASSWORD"]
DB_RETRY_COUNT = int(os.environ.get("CAPASS_SERVER_DB_RETRY_COUNT", "3"))
DB_RETRY_DELAY_SEC = int(os.environ.get("CAPASS_SERVER_DB_RETRY_DELAY_SEC", "3"))

# ツール代理トークンの暗号化鍵(Fernet鍵。カンマ区切りで複数指定可。先頭の鍵で暗号化し、全ての鍵で復号を試す=鍵ローテーション用)
## [鍵の作り方]python -c "from cryptography.fernet import Fernet; print(Fernet.generate_key().decode())"
TOKEN_ENCRYPTION_KEYS = [k.strip() for k in os.environ["CAPASS_SERVER_TOKEN_ENCRYPTION_KEYS"].split(",") if k.strip()]

# 署名付きリクエスト(登録/承認/ツール追加)の署名時刻の許容ずれ(秒)
SIGNATURE_MAX_SKEW_SEC = int(os.environ.get("CAPASS_SERVER_SIGNATURE_MAX_SKEW_SEC", "300"))

# レート制限(初回登録API: toolservers/register, agents/register)。クライアントIPごとに、WINDOW_SEC秒間にMAX_REQUESTS回まで受け付け、超えた場合は429を返す
## カウンタはプロセスのメモリ上で持つ。複数プロセス/複数台構成では、プロセスごとの制限になる(その場合はリバースプロキシ等での制限を併用する)
RATE_LIMIT_ENABLED = os.environ.get("CAPASS_SERVER_RATE_LIMIT_ENABLED", "true").lower() in ("1", "true", "yes")
RATE_LIMIT_REGISTER_MAX_REQUESTS = int(os.environ.get("CAPASS_SERVER_RATE_LIMIT_REGISTER_MAX_REQUESTS", "10"))
RATE_LIMIT_REGISTER_WINDOW_SEC = int(os.environ.get("CAPASS_SERVER_RATE_LIMIT_REGISTER_WINDOW_SEC", "60"))
## X-Forwarded-Forを付与する、信頼できるリバースプロキシの段数。0なら接続元のIPをそのまま使う
## リバースプロキシの背後で0のままだと、全クライアントがプロキシのIPとして扱われ、まとめて制限される。逆に、実際の段数より大きい値にしてはならない
TRUSTED_PROXY_COUNT = int(os.environ.get("CAPASS_SERVER_TRUSTED_PROXY_COUNT", "0"))

# ツールサーバ呼び出しのタイムアウト(秒)
TOOL_SERVER_TIMEOUT_SEC = float(os.environ.get("CAPASS_SERVER_TOOL_SERVER_TIMEOUT_SEC", "60"))


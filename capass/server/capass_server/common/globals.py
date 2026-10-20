import os
import inspect
import sys
import time
import traceback
PYPATH = os.path.dirname(os.path.abspath(inspect.getfile(inspect.currentframe())))
MODNAME = os.path.splitext(os.path.basename(inspect.getfile(inspect.currentframe())))[0]

# その他のモジュールやROOTPATHのディレクトリ起点の相対パスでのimport
# アプリ全体で共有する固定値(環境変数で変えない値)を集約する。環境変数由来の設定はconfig.py、署名の規則(署名プレフィックス等)はsignature.pyに置く。
# このモジュールは他のモジュールに依存しない。使うときは `from capass_server.common.globals import X` と名前を指定してimportする(モジュールごとimportすると、組み込みのglobals()を隠してしまう)。

# ---------- 文字列長の上限(スキーマの検証と、DBのカラム長で共有する) ----------
PUBLIC_KEY_MAX_LEN = 64  # Ed25519の生32バイトをBase64にした44文字に、余裕を持たせた長さ
EMAIL_MAX_LEN = 255
TOOL_SERVER_NAME_MAX_LEN = 255
AGENT_ID_MAX_LEN = 128
TOOL_ENDPOINT_MAX_LEN = 128
TOOL_PROXY_TOKEN_MAX_LEN = 1024  # 平文の上限。DBには暗号化して(Textで)保存する
EXEC_URL_MAX_LEN = 2048
NONCE_MAX_LEN = 128
NONCE_MIN_LEN = 16
PARAMS_SCHEMA_MAX_BYTES = 16 * 1024  # ツールのparamsのスキーマ(JSON Schema)の最大サイズ(JSON化したバイト数)
STATUS_MAX_LEN = 16

# ---------- paramsのスキーマ検証の結果(AIエージェントへ返すエラーの上限) ----------
PARAMS_ERROR_MAX_COUNT = 10  # 返すエラーの最大件数
PARAMS_ERROR_MAX_LEN = 300  # エラー1件の最大文字数(長い値をそのまま返さないため)

# ---------- 入力の形式(正規表現。pydanticのRust製エンジンで使えるよう、先読み等は使わない) ----------
# メールアドレスの簡易チェック。EmailStrは値を正規化(ドメインの小文字化等)するため、署名したJSONと一致しなくなる恐れがあり、使わない
EMAIL_PATTERN = r"^[^@\s]+@[^@\s]+\.[^@\s]+$"
# AIエージェントの識別子(URLパスに使うため、英数字と . _ - のみ)
AGENT_ID_PATTERN = rf"^[A-Za-z0-9._-]{{1,{AGENT_ID_MAX_LEN}}}$"
# ツールエンドポイント(URLパス exec/{tool_endpoint} に使うため、スラッシュ・空白・制御文字は不可。日本語は使える)
TOOL_ENDPOINT_PATTERN = rf"^[^/\s\x00-\x1f]{{1,{TOOL_ENDPOINT_MAX_LEN}}}$"
# リクエストごとに一意なnonce(リプレイ防止)
NONCE_PATTERN = rf"^[A-Za-z0-9_-]{{{NONCE_MIN_LEN},{NONCE_MAX_LEN}}}$"
# ツールサーバの実行URL(http/httpsのみ。httpを許可するかは、設定 TOOL_SERVER_ALLOW_HTTP で別途判定する)
EXEC_URL_PATTERN = r"^https?://[^\s]+$"

# ---------- HTTP ----------
API_V1_PREFIX = "/api/v1"
SIGNATURE_AUTH_SCHEME = "CaPass-Signature"  # 401のWWW-Authenticateヘッダーに入れる認証スキーム名
HEADER_SIGNED_AT = "X-CaPass-Signed-At"  # 署名付きGETリクエストの、署名時刻(UNIX秒)のヘッダー
HEADER_SIGNATURE = "X-CaPass-Signature"  # 署名付きGETリクエストの、署名(Base64)のヘッダー

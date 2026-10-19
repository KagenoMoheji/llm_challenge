"""CaPassサーバの動作確認用の、ツールサーバの見本(開発・動作確認用)。

CaPassサーバからのツール実行の依頼(POST)を受け取り、ツール代理トークンの確認をして、パラメータをそのまま返す。
ツールサーバが実装する仕様(CaPassサーバからの呼び出し):
  POST <登録した実行URL>
    Authorization: Bearer <ツール代理トークン>
    ボディ(JSON): {"agent_id": "...", "tool_endpoint": "...", "params": {...}}
  応答: 成功は2xx(ボディはそのままAIエージェントへ中継される)。トークンや権限が不正なら403(または4xx)を返す。

  # 環境変数 FAKE_TOOL_TOKENS に、「トークン: {agent_id, tool_endpoint}」のJSONを渡して起動する(トークンは、addtoolで登録したもの)
  FAKE_TOOL_TOKENS='{"<トークン>": {"agent_id": "agent-1", "tool_endpoint": "psql_manager"}}' \
  python fake_tool_server.py 9000
  # CaPassサーバ側は CAPASS_SERVER_TOOL_SERVER_ALLOW_HTTP=true にして、実行URL http://127.0.0.1:9000/capass/exec で登録する
"""
import os
import inspect
import sys
import time
import traceback
PYPATH = os.path.dirname(os.path.abspath(inspect.getfile(inspect.currentframe())))
MODNAME = os.path.splitext(os.path.basename(inspect.getfile(inspect.currentframe())))[0]

# その他のモジュールやROOTPATHのディレクトリ起点の相対パスでのimport
# (このスクリプトはCaPassサーバのコードをimportしない単体スクリプトなので、ROOTPATHは使わない)
import json
import hmac
from http.server import BaseHTTPRequestHandler, HTTPServer

TOKENS = json.loads(os.environ.get("FAKE_TOOL_TOKENS", "{}"))


class Handler(BaseHTTPRequestHandler):
    def do_POST(self):
        if self.path != "/capass/exec":
            return self._send(404, {"detail": "not found"})
        auth = self.headers.get("Authorization", "")
        token = auth[len("Bearer "):] if auth.startswith("Bearer ") else ""
        body = json.loads(self.rfile.read(int(self.headers.get("Content-Length", "0"))) or b"{}")
        # ツール代理トークンに対応する認証情報(ここでは、許可するagent_idとtool_endpoint)を引く。トークンの比較は、タイミング攻撃を避けるため定数時間で行う
        entry = next((v for k, v in TOKENS.items() if hmac.compare_digest(k.encode(), token.encode())), None)
        if entry is None or entry["agent_id"] != body.get("agent_id") or entry["tool_endpoint"] != body.get("tool_endpoint"):
            return self._send(403, {"detail": "permission denied"})
        self._send(200, {"result": "ok", "tool_endpoint": body["tool_endpoint"], "echo": body.get("params")})

    def _send(self, status, obj):
        data = json.dumps(obj, ensure_ascii=False).encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Content-Length", str(len(data)))
        self.end_headers()
        self.wfile.write(data)


if __name__ == "__main__":
    port = int(sys.argv[1]) if len(sys.argv) > 1 else 9000
    print(f"fake tool server: http://127.0.0.1:{port}/capass/exec")
    HTTPServer(("127.0.0.1", port), Handler).serve_forever()

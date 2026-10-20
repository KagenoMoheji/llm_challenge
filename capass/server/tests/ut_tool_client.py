import os
import inspect
import sys
import time
import traceback
PYPATH = os.path.dirname(os.path.abspath(inspect.getfile(inspect.currentframe())))
# 以下のROOTPATHでimportの起点を指定
ROOTPATH = os.path.abspath(f"{PYPATH}/..")
MODNAME = os.path.splitext(os.path.basename(inspect.getfile(inspect.currentframe())))[0]
sys.path.append(ROOTPATH)

# その他のモジュールやROOTPATHのディレクトリ起点の相対パスでのimport
import json
import threading
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
import pytest
from capass_server.common.errors import ToolServerBadResponseError, ToolServerTimeoutError, ToolServerUnavailableError
from capass_server.common.tool_client import ToolServerResponse, call_tool_server


class _Handler(BaseHTTPRequestHandler):
    """テスト用のツールサーバ。パスで挙動を変える。受け取ったリクエストは、server.receivedに記録する。"""

    def log_message(self, *args):  # テスト出力を静かにする
        pass

    def do_POST(self):
        length = int(self.headers.get("Content-Length", "0"))
        body = self.rfile.read(length)
        self.server.received.append({"path": self.path, "headers": dict(self.headers), "body": json.loads(body) if body else None})
        if self.path == "/ok":
            self._send(200, b'{"result": "ok"}', "application/json")
        elif self.path == "/forbidden":
            self._send(403, b'{"detail": "permission denied"}', "application/json")
        elif self.path == "/error":
            self._send(500, b"boom", "text/plain")
        elif self.path == "/redirect":
            self.send_response(302)
            self.send_header("Location", "/ok")
            self.send_header("Content-Length", "0")
            self.end_headers()
        elif self.path == "/slow":
            threading.Event().wait(2)
            self._send(200, b"late", "text/plain")
        elif self.path == "/big":
            self._send(200, b"x" * 5000, "application/octet-stream")
        else:
            self._send(404, b"", None)

    def _send(self, status, body, content_type):
        self.send_response(status)
        if content_type:
            self.send_header("Content-Type", content_type)
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)


@pytest.fixture
def tool_server():
    server = ThreadingHTTPServer(("127.0.0.1", 0), _Handler)
    server.received = []
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    yield server
    server.shutdown()
    server.server_close()


def _url(server, path):
    return f"http://127.0.0.1:{server.server_address[1]}{path}"


def _call(server, path, timeout_sec=5, max_bytes=1024 * 1024):
    payload = {"agent_id": "agent-1", "tool_endpoint": "psql_部長ロール", "params": {"sql": "SELECT '日本語'"}}
    return call_tool_server(_url(server, path), "secret-token", payload, timeout_sec, max_bytes, user_agent="CaPass/test")


def test_sends_token_as_bearer_and_payload_as_json(tool_server):
    res = _call(tool_server, "/ok")
    assert res == ToolServerResponse(200, b'{"result": "ok"}', "application/json")
    received = tool_server.received[0]
    assert received["headers"]["Authorization"] == "Bearer secret-token"
    assert received["headers"]["Content-Type"].startswith("application/json")
    assert received["headers"]["User-Agent"] == "CaPass/test"
    assert received["body"] == {"agent_id": "agent-1", "tool_endpoint": "psql_部長ロール", "params": {"sql": "SELECT '日本語'"}}


def test_returns_4xx_and_5xx_responses_instead_of_raising(tool_server):
    forbidden = _call(tool_server, "/forbidden")
    assert (forbidden.status_code, forbidden.body) == (403, b'{"detail": "permission denied"}')
    error = _call(tool_server, "/error")
    assert (error.status_code, error.body, error.content_type) == (500, b"boom", "text/plain")


def test_does_not_follow_redirects(tool_server):
    res = _call(tool_server, "/redirect")
    assert res.status_code == 302  # リダイレクト先へは接続しない
    assert [r["path"] for r in tool_server.received] == ["/redirect"]


def test_times_out_on_slow_server(tool_server):
    with pytest.raises(ToolServerTimeoutError):
        _call(tool_server, "/slow", timeout_sec=0.5)


def test_rejects_too_large_response(tool_server):
    with pytest.raises(ToolServerBadResponseError):
        _call(tool_server, "/big", max_bytes=1000)
    assert _call(tool_server, "/big", max_bytes=5000).status_code == 200  # 上限ちょうどなら受け付ける


def test_connection_refused_is_unavailable(tool_server):
    url = _url(tool_server, "/ok")
    tool_server.shutdown()
    tool_server.server_close()
    with pytest.raises(ToolServerUnavailableError):
        call_tool_server(url, "t", {}, 2, 1024)


def test_invalid_url_is_unavailable():
    with pytest.raises(ToolServerUnavailableError):
        call_tool_server("https://no-such-host.invalid/exec", "t", {}, 2, 1024)

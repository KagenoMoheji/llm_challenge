import os
import inspect
import sys
import time
import traceback
PYPATH = os.path.dirname(os.path.abspath(inspect.getfile(inspect.currentframe())))
MODNAME = os.path.splitext(os.path.basename(inspect.getfile(inspect.currentframe())))[0]

# その他のモジュールやROOTPATHのディレクトリ起点の相対パスでのimport
import http.client
import json
import socket
import urllib.error
import urllib.request
from typing import NamedTuple
from capass_server.common.errors import ToolServerBadResponseError, ToolServerTimeoutError, ToolServerUnavailableError

_CHUNK_SIZE = 64 * 1024


class ToolServerResponse(NamedTuple):
    status_code: int
    body: bytes
    content_type: str | None


class _NoRedirectHandler(urllib.request.HTTPRedirectHandler):
    """リダイレクトを追わない(登録されたURL以外へ接続しないため)。3xxは、そのままHTTPErrorになる。"""

    def redirect_request(self, req, fp, code, msg, headers, newurl):
        return None


# 環境変数のプロキシ設定は使わない(ProxyHandler({}))。リダイレクトも追わない。TLS証明書は検証する
_opener = urllib.request.build_opener(urllib.request.ProxyHandler({}), _NoRedirectHandler)


def call_tool_server(url: str, token: str, payload: dict, timeout_sec: float, max_response_bytes: int, user_agent: str = "CaPass") -> ToolServerResponse:
    """ツールサーバの実行URLへ、POSTでツール実行を依頼する。

    リクエスト: Authorization: Bearer <ツール代理トークン(平文)>、ボディ(JSON)は payload
    応答は、ステータスによらず(4xx/5xxも)ToolServerResponseとして返す。接続失敗・タイムアウト・応答のサイズ超過は、業務エラーを送出する。
    timeout_secは、接続から応答の受信完了までの全体の制限時間。
    """
    deadline = time.monotonic() + timeout_sec
    data = json.dumps(payload, ensure_ascii=False).encode("utf-8")
    req = urllib.request.Request(
        url,
        data=data,
        method="POST",
        headers={
            "Authorization": f"Bearer {token}",
            "Content-Type": "application/json; charset=utf-8",
            "Accept": "application/json",
            "User-Agent": user_agent,
        },
    )
    try:
        with _opener.open(req, timeout=timeout_sec) as res:
            return _read_response(res, res.status, deadline, max_response_bytes)
    except urllib.error.HTTPError as e:  # 4xx/5xx/3xx(リダイレクトは追わない)
        try:
            return _read_response(e, e.code, deadline, max_response_bytes)
        finally:
            e.close()
    except (socket.timeout, TimeoutError):
        raise ToolServerTimeoutError()
    except urllib.error.URLError as e:
        if isinstance(e.reason, (socket.timeout, TimeoutError)):
            raise ToolServerTimeoutError()
        raise ToolServerUnavailableError()
    except (http.client.HTTPException, OSError, ValueError):
        raise ToolServerUnavailableError()


def _read_response(res, status_code: int, deadline: float, max_response_bytes: int) -> ToolServerResponse:
    chunks: list[bytes] = []
    size = 0
    while True:
        if time.monotonic() > deadline:
            raise ToolServerTimeoutError()
        chunk = res.read(_CHUNK_SIZE)
        if not chunk:
            break
        size += len(chunk)
        if size > max_response_bytes:
            raise ToolServerBadResponseError("response too large")
        chunks.append(chunk)
    return ToolServerResponse(status_code, b"".join(chunks), res.headers.get("Content-Type"))

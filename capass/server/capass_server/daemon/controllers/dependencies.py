import os
import inspect
import sys
import time
import traceback
PYPATH = os.path.dirname(os.path.abspath(inspect.getfile(inspect.currentframe())))
MODNAME = os.path.splitext(os.path.basename(inspect.getfile(inspect.currentframe())))[0]

# その他のモジュールやROOTPATHのディレクトリ起点の相対パスでのimport
from fastapi import Request
from capass_server.common.config import (
    RATE_LIMIT_ENABLED,
    RATE_LIMIT_REGISTER_MAX_REQUESTS,
    RATE_LIMIT_REGISTER_WINDOW_SEC,
    TRUSTED_PROXY_COUNT,
)
from capass_server.common.errors import RateLimitExceededError
from capass_server.common.rate_limit import SlidingWindowRateLimiter, extract_client_ip

# 初回登録API(toolservers/register, agents/register)で共有するレート制限。クライアントIPごとにカウントする
register_rate_limiter = SlidingWindowRateLimiter(RATE_LIMIT_REGISTER_MAX_REQUESTS, RATE_LIMIT_REGISTER_WINDOW_SEC)


def rate_limit_register(request: Request) -> None:
    """初回登録APIのレート制限。ルートに dependencies=[Depends(rate_limit_register)] で適用する。
    ボディの検証より先に実行されるので、不正なリクエストも回数に数える。"""
    if not RATE_LIMIT_ENABLED:
        return
    client_host = request.client.host if request.client else None
    client_ip = extract_client_ip(client_host, request.headers.get("x-forwarded-for"), TRUSTED_PROXY_COUNT)
    allowed, retry_after_sec = register_rate_limiter.allow(client_ip)
    if not allowed:
        raise RateLimitExceededError(retry_after_sec)

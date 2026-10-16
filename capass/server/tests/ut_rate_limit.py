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
import pytest
from capass_server.common.rate_limit import SlidingWindowRateLimiter, extract_client_ip


def test_allows_up_to_max_then_denies_with_retry_after():
    limiter = SlidingWindowRateLimiter(max_requests=3, window_sec=60)
    assert limiter.allow("1.1.1.1", now=100) == (True, 0)
    assert limiter.allow("1.1.1.1", now=101) == (True, 0)
    assert limiter.allow("1.1.1.1", now=102) == (True, 0)
    allowed, retry_after = limiter.allow("1.1.1.1", now=110)
    assert allowed is False
    assert retry_after == 50  # 最初のリクエスト(t=100)が窓から外れるt=160まで、あと50秒


def test_window_slides_and_frees_budget():
    limiter = SlidingWindowRateLimiter(max_requests=2, window_sec=60)
    assert limiter.allow("k", now=0)[0] is True
    assert limiter.allow("k", now=30)[0] is True
    assert limiter.allow("k", now=59)[0] is False
    assert limiter.allow("k", now=61)[0] is True  # t=0の分が窓から外れた
    assert limiter.allow("k", now=62)[0] is False  # t=30, t=61 で再び満杯


def test_denied_requests_are_not_counted():
    limiter = SlidingWindowRateLimiter(max_requests=1, window_sec=10)
    assert limiter.allow("k", now=0)[0] is True
    for t in range(1, 10):
        assert limiter.allow("k", now=t)[0] is False  # 拒否され続けても、回数に数えない
    assert limiter.allow("k", now=10.5)[0] is True  # 最初の1回が窓から外れれば、すぐ再開できる


def test_keys_are_independent():
    limiter = SlidingWindowRateLimiter(max_requests=1, window_sec=60)
    assert limiter.allow("a", now=0)[0] is True
    assert limiter.allow("a", now=1)[0] is False
    assert limiter.allow("b", now=1)[0] is True


def test_reset_clears_counters():
    limiter = SlidingWindowRateLimiter(max_requests=1, window_sec=60)
    assert limiter.allow("a", now=0)[0] is True
    limiter.reset()
    assert limiter.allow("a", now=1)[0] is True


def test_memory_is_bounded_by_max_keys():
    limiter = SlidingWindowRateLimiter(max_requests=1, window_sec=60, max_keys=3)
    for i in range(10):
        assert limiter.allow(f"ip-{i}", now=i)[0] is True
    assert len(limiter._hits) <= 3


def test_expired_keys_are_swept_before_evicting_active_ones():
    limiter = SlidingWindowRateLimiter(max_requests=1, window_sec=10, max_keys=2)
    limiter.allow("old-1", now=0)
    limiter.allow("old-2", now=1)
    limiter.allow("fresh", now=100)  # old-1, old-2は期限切れなので掃除される
    assert set(limiter._hits) == {"fresh"}


def test_invalid_arguments_are_rejected():
    for args in ((0, 60), (1, 0), (1, -1)):
        with pytest.raises(ValueError):
            SlidingWindowRateLimiter(*args)


def test_extract_client_ip_without_trusted_proxy_ignores_forwarded_header():
    assert extract_client_ip("10.0.0.9", "1.2.3.4", 0) == "10.0.0.9"  # 信頼できるプロキシが無い場合、偽装可能なヘッダーは使わない
    assert extract_client_ip(None, None, 0) == "unknown"


def test_extract_client_ip_with_one_trusted_proxy_uses_rightmost():
    assert extract_client_ip("10.0.0.9", "203.0.113.5", 1) == "203.0.113.5"
    assert extract_client_ip("10.0.0.9", "6.6.6.6, 203.0.113.5", 1) == "203.0.113.5"  # 左側(クライアントが付けた偽装)は無視される


def test_extract_client_ip_with_two_trusted_proxies():
    assert extract_client_ip("10.0.0.9", "6.6.6.6, 203.0.113.5, 10.0.0.1", 2) == "203.0.113.5"


def test_extract_client_ip_falls_back_when_header_is_missing_or_short():
    assert extract_client_ip("10.0.0.9", None, 1) == "10.0.0.9"
    assert extract_client_ip("10.0.0.9", "", 1) == "10.0.0.9"
    assert extract_client_ip("10.0.0.9", "203.0.113.5", 2) == "10.0.0.9"  # 段数に満たない=不審なので接続元を使う

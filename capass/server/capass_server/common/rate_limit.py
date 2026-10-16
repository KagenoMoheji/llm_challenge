import os
import inspect
import sys
import time
import traceback
PYPATH = os.path.dirname(os.path.abspath(inspect.getfile(inspect.currentframe())))
MODNAME = os.path.splitext(os.path.basename(inspect.getfile(inspect.currentframe())))[0]

# その他のモジュールやROOTPATHのディレクトリ起点の相対パスでのimport
import math
import threading
from collections import deque


class SlidingWindowRateLimiter:
    """キーごとのスライディングウィンドウ方式のレート制限(プロセス内メモリ。スレッドセーフ)。

    直近window_sec秒間に、同じキーで受け付けた回数がmax_requestsに達していたら拒否する。拒否したリクエストは回数に数えない。
    キーの数がmax_keysに達したら、期限切れのキーを掃除し、それでも満杯なら最も古く登録されたキーを破棄する(メモリを無制限に増やさないため)。
    """

    def __init__(self, max_requests: int, window_sec: float, max_keys: int = 10000) -> None:
        if max_requests < 1 or window_sec <= 0 or max_keys < 1:
            raise ValueError("max_requests and max_keys must be >= 1, window_sec must be > 0")
        self._max_requests = max_requests
        self._window_sec = window_sec
        self._max_keys = max_keys
        self._hits: dict[str, deque[float]] = {}
        self._lock = threading.Lock()

    def allow(self, key: str, now: float | None = None) -> tuple[bool, int]:
        """(受け付けるか, 拒否した場合の再試行までの待ち時間(秒、切り上げ))を返す。nowはテスト用(省略時はtime.monotonic())。"""
        current = time.monotonic() if now is None else now
        cutoff = current - self._window_sec
        with self._lock:
            hits = self._hits.get(key)
            if hits is None:
                if len(self._hits) >= self._max_keys:
                    self._sweep(cutoff)
                if len(self._hits) >= self._max_keys:
                    self._hits.pop(next(iter(self._hits)))
                hits = self._hits.setdefault(key, deque())
            while hits and hits[0] <= cutoff:
                hits.popleft()
            if len(hits) >= self._max_requests:
                return False, max(1, math.ceil(hits[0] + self._window_sec - current))
            hits.append(current)
            return True, 0

    def reset(self) -> None:
        with self._lock:
            self._hits.clear()

    def _sweep(self, cutoff: float) -> None:
        for key in [k for k, hits in self._hits.items() if not hits or hits[-1] <= cutoff]:
            del self._hits[key]


def extract_client_ip(client_host: str | None, x_forwarded_for: str | None, trusted_proxy_count: int) -> str:
    """レート制限のキーにするクライアントIPを決める。

    X-Forwarded-Forは、クライアント自身が偽装できる。信頼できるプロキシがN段ある場合、プロキシは接続元のIPをヘッダーの右端に追加するので、
    右からN番目がクライアントIPになる(左側の値は、クライアントが付けたものかもしれないので使わない)。
    N=0、ヘッダーが無い、またはN個に満たない場合は、接続元のIPを使う。
    """
    if trusted_proxy_count > 0 and x_forwarded_for:
        hops = [h.strip() for h in x_forwarded_for.split(",") if h.strip()]
        if len(hops) >= trusted_proxy_count:
            return hops[-trusted_proxy_count]
    return client_host or "unknown"

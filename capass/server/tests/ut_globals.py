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
import re
from capass_server.common.globals import (
    AGENT_ID_MAX_LEN,
    AGENT_ID_PATTERN,
    EMAIL_PATTERN,
    EXEC_URL_PATTERN,
    NONCE_MAX_LEN,
    NONCE_MIN_LEN,
    NONCE_PATTERN,
    TOOL_ENDPOINT_MAX_LEN,
    TOOL_ENDPOINT_PATTERN,
)


def _ok(pattern, value):
    return re.search(pattern, value) is not None


def test_email_pattern():
    for ok in ("a@example.com", "first.last+tag@sub.example.co.jp"):
        assert _ok(EMAIL_PATTERN, ok), ok
    for ng in ("", "not-an-email", "a@b", "a b@example.com", "@example.com", "a@@example.com"):
        assert not _ok(EMAIL_PATTERN, ng), ng


def test_agent_id_pattern():
    for ok in ("agent-1", "Agent_01.prod", "a", "a" * AGENT_ID_MAX_LEN):
        assert _ok(AGENT_ID_PATTERN, ok), ok
    for ng in ("", "bad/agent", "bad agent", "エージェント", "a" * (AGENT_ID_MAX_LEN + 1)):
        assert not _ok(AGENT_ID_PATTERN, ng), ng


def test_tool_endpoint_pattern_allows_japanese_but_not_slash_or_whitespace():
    for ok in ("psql_manager", "psql_部長ロール", "db.query-v2", "x" * TOOL_ENDPOINT_MAX_LEN):
        assert _ok(TOOL_ENDPOINT_PATTERN, ok), ok
    for ng in ("", "cli://db/query", "a/b", "has space", "tab\there", "ctrl\x01char", "x" * (TOOL_ENDPOINT_MAX_LEN + 1)):
        assert not _ok(TOOL_ENDPOINT_PATTERN, ng), ng


def test_nonce_pattern():
    assert _ok(NONCE_PATTERN, "a" * NONCE_MIN_LEN)
    assert _ok(NONCE_PATTERN, "Ab-_0123456789xyzXYZ")
    assert _ok(NONCE_PATTERN, "a" * NONCE_MAX_LEN)
    for ng in ("", "a" * (NONCE_MIN_LEN - 1), "a" * (NONCE_MAX_LEN + 1), "has space 0123456789", "日本語日本語日本語日本語日本語"):
        assert not _ok(NONCE_PATTERN, ng), ng


def test_exec_url_pattern():
    for ok in ("https://toolserver.example.com/capass/exec", "http://localhost:9000/exec"):
        assert _ok(EXEC_URL_PATTERN, ok), ok
    for ng in ("", "ftp://example.com", "example.com/exec", "file:///etc/passwd", "https://exa mple.com", "https://"):
        assert not _ok(EXEC_URL_PATTERN, ng), ng

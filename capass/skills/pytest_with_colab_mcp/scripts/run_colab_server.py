"""Google Colab MCP pytest Runner for capass-server

Google Colab 上で capass-server の依存インストール、環境変数設定および
pytest をリモート自動実行するためのアトミックスクリプト。
"""

from __future__ import annotations

import argparse
import asyncio
import base64
import json
import logging
import socket
import sys
import traceback
from pathlib import Path

import websockets
from websockets.typing import Subprotocol
from fastmcp import Client, FastMCP
from mcp.types import TextContent

import colab_mcp.websocket_server
from colab_mcp.websocket_server import ColabWebSocketServer
import colab_mcp.session
from colab_mcp.session import ColabSessionProxy

# Windows コンソールのエンコーディング対応 (CP932 等での UnicodeEncodeError を防止)
if sys.stdout and hasattr(sys.stdout, "reconfigure"):
    try:
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    except Exception:
        pass
if sys.stderr and hasattr(sys.stderr, "reconfigure"):
    try:
        sys.stderr.reconfigure(encoding="utf-8", errors="replace")
    except Exception:
        pass


def safe_print(*args, **kwargs):
    try:
        print(*args, **kwargs)
    except UnicodeEncodeError:
        text = " ".join(str(a) for a in args)
        clean = text.encode(sys.stdout.encoding or "ascii", errors="replace").decode(
            sys.stdout.encoding or "ascii"
        )
        print(clean, **kwargs)


# 1. 接続待機タイムアウトを 300秒に延長
colab_mcp.session.UI_CONNECTION_TIMEOUT = 300.0


# 2. Windows 向けポートバインド・パッチ (IPv4/IPv6 ポート不一致対策)
def _get_free_port() -> int:
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
        s.bind(("127.0.0.1", 0))
        return s.getsockname()[1]


async def _patched_aenter(self):
    port = _get_free_port()
    self._server = await websockets.serve(
        self._connection_handler,
        host=self.host,
        port=port,
        subprotocols=[Subprotocol("mcp")],
        origins=self.allowed_origins,
        process_request=self._validate_authorization,
    )
    self.port = port
    logging.info(
        f"Starting WebSocket server on ws://{self.host}:{self.port} "
        f"(dual-stack: {[s.getsockname() for s in self._server.sockets]})"
    )
    return self


ColabWebSocketServer.__aenter__ = _patched_aenter


def dump_result(obj) -> str:
    parts: list[str] = []
    content = getattr(obj, "content", None)
    if content:
        for item in content:
            if isinstance(item, TextContent):
                parts.append(item.text)
            else:
                parts.append(str(item))
    structured = getattr(obj, "structured_content", None) or getattr(obj, "data", None)
    if structured is not None:
        parts.append(json.dumps(structured, ensure_ascii=False, default=str, indent=2))
    if not parts:
        parts.append(repr(obj))
    return "\n".join(parts)


def generate_server_code(zip_b64: str, zip_name: str, root_folder_name: str) -> str:
    return f'''
from pathlib import Path
import base64
import os
import subprocess
import sys
import zipfile

zip_path = Path("/content/{zip_name}")
zip_path.write_bytes(base64.b64decode({zip_b64!r}))

extract_dir = Path("/content/capass-src")
if extract_dir.exists():
    import shutil
    shutil.rmtree(extract_dir)
extract_dir.mkdir(parents=True)

with zipfile.ZipFile(zip_path) as zf:
    zf.extractall(extract_dir)

root = extract_dir / "{root_folder_name}"
server_dir = root / "server"

print("EXTRACT_OK", server_dir)
print("TEST_FILES", sorted(p.name for p in (server_dir / "tests").glob("*.py")))

# 1. capass-server をインストール (psycopg, fastapi, sqlalchemy 等)
cmd_srv = [sys.executable, "-m", "pip", "install", "-e", ".[dev]"]
print("INSTALL_SERVER", cmd_srv)
proc = subprocess.run(cmd_srv, cwd=server_dir, capture_output=True, text=True)
print(proc.stdout)
print(proc.stderr, file=sys.stderr)
if proc.returncode != 0:
    raise SystemExit(f"pip install server failed: {{proc.returncode}}")

# 2. テスト用環境変数の構成 (インメモリ SQLite / Fernet 暗号化鍵)
from cryptography.fernet import Fernet
env = os.environ.copy()
env["CAPASS_SERVER_ENV"] = "LOCAL_DEV"
env["CAPASS_SERVER_DB_HOST"] = "127.0.0.1"
env["CAPASS_SERVER_DB_PORT"] = "5432"
env["CAPASS_SERVER_DB_NAME"] = "capass"
env["CAPASS_SERVER_DB_USER"] = "capass"
env["CAPASS_SERVER_DB_PASSWORD"] = "capass"
env["CAPASS_SERVER_TOKEN_ENCRYPTION_KEYS"] = Fernet.generate_key().decode()

# 3. pytest 実行
test_cmd = [sys.executable, "-m", "pytest", "-vv", "tests"]
print("PYTEST", test_cmd)
proc = subprocess.run(test_cmd, cwd=server_dir, capture_output=True, text=True, env=env)
print(proc.stdout)
print(proc.stderr, file=sys.stderr)
print("PYTEST_EXIT", proc.returncode)
raise SystemExit(proc.returncode)
'''.strip()


async def run_pipeline(zip_path: Path, out_dir: Path | None = None) -> int:
    if not zip_path.is_file():
        safe_print(f"Error: Zip file not found: {zip_path}", file=sys.stderr)
        return 1

    if out_dir is None:
        out_dir = zip_path.parent
    out_dir.mkdir(parents=True, exist_ok=True)

    url_file = out_dir / "colab_mcp_url_server.txt"
    tools_file = out_dir / "colab_mcp_tools.json"
    result_file = out_dir / "colab_mcp_result_server.txt"

    zip_bytes = zip_path.read_bytes()
    zip_b64 = base64.b64encode(zip_bytes).decode("ascii")

    import zipfile
    with zipfile.ZipFile(zip_path) as zf:
        first_part = zf.namelist()[0].split("/")[0]
        root_folder_name = first_part if first_part else zip_path.stem

    mcp = FastMCP(name="ColabMCP-Server")
    session_mcp = ColabSessionProxy()
    await session_mcp.start_proxy_server()
    mcp.mount(session_mcp.proxy_server)
    for middleware in session_mcp.middleware:
        mcp.add_middleware(middleware)

    wss = session_mcp.wss
    colab_url = (
        f"https://colab.research.google.com/notebooks/empty.ipynb"
        f"#mcpProxyToken={wss.token}&mcpProxyPort={wss.port}"
    )
    url_file.write_text(colab_url, encoding="utf-8")

    safe_print("\n" + "=" * 70)
    safe_print("【COLAB_MCP_URL (Server)】", colab_url)
    safe_print("=" * 70 + "\n")
    safe_print(f"Saved URL to: {url_file}")

    try:
        async with Client(mcp) as client:
            safe_print("calling open_colab_browser_connection (waiting up to 300s for user to connect in Colab)...")
            opened = await client.call_tool("open_colab_browser_connection")
            res_str = dump_result(opened)
            safe_print("open_result:", res_str)

            if "true" not in res_str.lower() and not session_mcp.wss.connection_live.is_set():
                err_msg = "TIMEOUT: Colab UI did not connect.\n" + colab_url
                result_file.write_text(err_msg, encoding="utf-8")
                safe_print("TIMEOUT waiting for Colab connection")
                return 2

            safe_print("\n" + "=" * 70)
            safe_print("★ SUCCESS: Colab UI connected and initialized!")
            safe_print("=" * 70 + "\n")

            tools = await client.list_tools()
            tool_names = [t.name for t in tools]
            safe_print("TOOLS:", tool_names)

            tool_info = [
                {
                    "name": t.name,
                    "description": t.description,
                    "inputSchema": getattr(t, "inputSchema", None),
                }
                for t in tools
            ]
            tools_file.write_text(
                json.dumps(tool_info, ensure_ascii=False, indent=2, default=str),
                encoding="utf-8",
            )

            code = generate_server_code(zip_b64, zip_path.name, root_folder_name)
            safe_print("Adding code cell to Colab for server...")
            added = await client.call_tool(
                "add_code_cell",
                {"cellIndex": 0, "language": "python", "code": code},
            )
            add_dump = dump_result(added)
            safe_print("add_code_cell result:", add_dump)

            cell_id = None
            structured = getattr(added, "structured_content", None) or {}
            if isinstance(structured, dict):
                cell_id = (
                    structured.get("newCellId")
                    or structured.get("cellId")
                    or structured.get("id")
                    or structured.get("result")
                )
            if cell_id is None:
                for line in add_dump.splitlines()[::-1]:
                    line = line.strip().strip('"')
                    if line and " " not in line and len(line) < 80:
                        cell_id = line
                        break

            if not cell_id:
                err_msg = "Could not parse cell id from add_code_cell:\n" + add_dump
                result_file.write_text(err_msg, encoding="utf-8")
                return 3

            safe_print(f"Executing cell {cell_id} on Colab... (running pip install & pytest for server)")
            ran = await client.call_tool("run_code_cell", {"cellId": str(cell_id)})
            text = dump_result(ran)

            result_file.write_text(f"cellId={cell_id}\n{text}\n", encoding="utf-8")
            safe_print("\n" + "=" * 70)
            safe_print("【COLAB TEST RESULT (Server)】")
            safe_print("=" * 70)
            safe_print(text)

            if "PYTEST_EXIT 0" in text or '"evalue": "0"' in text:
                safe_print("\n>>> server tests PASSED successfully! <<<")
                return 0
            else:
                safe_print("\n>>> server tests FAILED. <<<")
                return 1

    except Exception as e:
        safe_print(f"\nExecution failed with error: {e}", file=sys.stderr)
        traceback.print_exc()
        result_file.write_text(f"ERROR: {e}\n{traceback.format_exc()}", encoding="utf-8")
        return 4


def main():
    parser = argparse.ArgumentParser(description="Run server pytest on Google Colab via colab-mcp")
    parser.add_argument("zip_path", type=Path, help="Path to project source zip file")
    parser.add_argument(
        "--out-dir",
        type=Path,
        default=None,
        help="Directory to save URL, tools JSON, and result output",
    )
    args = parser.parse_args()

    exit_code = asyncio.run(run_pipeline(zip_path=args.zip_path, out_dir=args.out_dir))
    sys.exit(exit_code)


if __name__ == "__main__":
    main()

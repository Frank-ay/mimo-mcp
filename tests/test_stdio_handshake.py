"""真·stdio 握手:启动 mimo-mcp 子进程,发送 initialize + tools/list,验证响应。

这个测试比 in-process 的 mcp.list_tools() 更接近真实 Claude Code / Codex 调用情形。
"""

from __future__ import annotations

import asyncio
import json
import shutil
import sys
from pathlib import Path

import pytest

REQUESTS = [
    {
        "jsonrpc": "2.0",
        "id": 1,
        "method": "initialize",
        "params": {
            "protocolVersion": "2024-11-05",
            "capabilities": {},
            "clientInfo": {"name": "mimo-smoke", "version": "0.1"},
        },
    },
    {"jsonrpc": "2.0", "method": "notifications/initialized"},
    {"jsonrpc": "2.0", "id": 2, "method": "tools/list"},
]


def _entry() -> str | None:
    if shutil.which("mimo-mcp"):
        return "mimo-mcp"
    venv_bin = Path(sys.executable).parent / "mimo-mcp"
    if venv_bin.exists():
        return str(venv_bin)
    return None


@pytest.mark.asyncio
async def test_stdio_initialize_and_list_tools() -> None:
    entry = _entry()
    if entry is None:
        pytest.skip("mimo-mcp 入口未安装(需要先 uv sync)")

    proc = await asyncio.create_subprocess_exec(
        entry,
        stdin=asyncio.subprocess.PIPE,
        stdout=asyncio.subprocess.PIPE,
        stderr=asyncio.subprocess.PIPE,
    )
    assert proc.stdin and proc.stdout

    payload = "\n".join(json.dumps(r) for r in REQUESTS) + "\n"
    proc.stdin.write(payload.encode("utf-8"))
    await proc.stdin.drain()

    responses: list[dict] = []
    try:
        async with asyncio.timeout(10):
            while len(responses) < 2:
                line = await proc.stdout.readline()
                if not line:
                    break
                try:
                    responses.append(json.loads(line.decode("utf-8")))
                except json.JSONDecodeError:
                    continue
    finally:
        proc.stdin.close()
        try:
            await asyncio.wait_for(proc.wait(), timeout=2)
        except asyncio.TimeoutError:
            proc.terminate()
            await proc.wait()

    assert responses, "未收到任何响应"
    init_resp = next(r for r in responses if r.get("id") == 1)
    assert "result" in init_resp, f"initialize 失败:{init_resp}"
    assert init_resp["result"].get("serverInfo", {}).get("name") == "mimo-mcp"

    list_resp = next(r for r in responses if r.get("id") == 2)
    assert "result" in list_resp, f"tools/list 失败:{list_resp}"
    names = {t["name"] for t in list_resp["result"]["tools"]}
    expected = {
        "mimo.chat",
        "mimo.image_understand",
        "mimo.video_understand",
        "mimo.tts",
        "mimo.voice_clone_create",
        "mimo.voice_design_create",
        "mimo.voice_list",
        "mimo.voice_delete",
        "mimo.asr",
        "mimo.health",
        "mimo.usage",
    }
    missing = expected - names
    assert not missing, f"stdio 握手缺失 tool:{missing}"

"""排查鉴权失败:三种鉴权头各发一次最小 chat,定位到底是 key 问题还是头格式问题。"""

from __future__ import annotations

import asyncio
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))


async def main() -> int:
    import httpx
    from mimo_mcp.config import get_settings

    settings = get_settings()
    if not settings.has_api_key:
        print("× MIMO_API_KEY 未配置")
        return 1

    key = settings.api_key
    masked = (key[:6] + "…" + key[-4:]) if len(key) > 10 else "***"
    print(f"  API Key:{masked}  长度={len(key)}  前缀={key.split('-', 1)[0] if '-' in key else 'NO-DASH'}")
    print(f"  base_url:{settings.base_url}")

    body = {
        "model": settings.default_text_model,
        "messages": [{"role": "user", "content": "ping"}],
        "max_tokens": 8,
    }

    variants: list[tuple[str, dict[str, str]]] = [
        ("Authorization Bearer", {"Authorization": f"Bearer {key}"}),
        ("api-key (lower)", {"api-key": key}),
        ("Api-Key (mixed)", {"Api-Key": key}),
    ]

    async with httpx.AsyncClient(base_url=settings.base_url, timeout=30.0) as client:
        for label, headers in variants:
            print(f"\n[{label}]")
            try:
                resp = await client.post("/chat/completions", json=body, headers=headers)
                print(f"  status = {resp.status_code}")
                text = resp.text[:600]
                try:
                    pretty = json.dumps(json.loads(text), ensure_ascii=False)
                    print(f"  body  = {pretty}")
                except Exception:
                    print(f"  body  = {text}")
            except httpx.HTTPError as e:
                print(f"  网络异常:{e!r}")

    return 0


if __name__ == "__main__":
    raise SystemExit(asyncio.run(main()))

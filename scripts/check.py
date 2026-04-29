"""一键自检:读 .env → 跑 mimo.health → 漂亮地打印结果。

用法:
    uv run python scripts/check.py

把 .env 中的 MIMO_API_KEY 填好后,运行此脚本就能看到:
- API Key 是否被识别
- base_url 是否可达
- 鉴权是否合法
- 云端 ASR 是否开放
"""

from __future__ import annotations

import asyncio
import sys

# 项目根加入 path,方便从仓库根运行
ROOT = __import__("pathlib").Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))


def _icon(ok: bool | None) -> str:
    if ok is True:
        return "[OK]"
    if ok is False:
        return "[X ]"
    return "[? ]"


async def main() -> int:
    from mimo_mcp.api.usage import health_check  # noqa: WPS433

    print()
    print("====================  mimo-mcp 健康检查  ====================")
    result = await health_check()

    rows = [
        ("API Key 已配置", result.api_key_configured),
        ("base_url 可达", result.base_url_reachable),
        ("鉴权合法", result.auth_valid),
        ("云端 ASR 可用", result.asr_cloud_available),
    ]
    width = max(len(label) for label, _ in rows)
    for label, ok in rows:
        print(f"  {_icon(ok)}  {label.ljust(width)}")

    print(f"\n  base_url = {result.base_url}")

    if result.notes:
        print("\n  提示:")
        for note in result.notes:
            print(f"    · {note}")

    print()
    if not result.api_key_configured:
        print("→ 请先编辑 .env,把 MIMO_API_KEY 改为真实 key 后重跑。")
        return 1
    if result.auth_valid is False:
        print("→ key 无效或已过期,去 platform.xiaomimimo.com 重新生成。")
        return 2
    if result.base_url_reachable is False:
        print("→ 网络不可达,检查代理 / VPN / MIMO_BASE_URL。")
        return 3

    print("→ 一切正常,可以把 mimo-mcp 注册到 Claude Code / Codex 了。")
    return 0


if __name__ == "__main__":
    raise SystemExit(asyncio.run(main()))

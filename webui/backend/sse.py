"""公共 SSE 帧格式化工具。

所有 SSE 路由应使用此函数生成帧字符串,保证格式一致。
"""

from __future__ import annotations

import json
from typing import Any


def sse_event(event: str, data: Any) -> str:
    """生成一个 SSE 帧字符串。

    格式::

        event: {event}\\n
        data: {json.dumps(data)}\\n
        \\n

    与各路由原 ``_sse`` 函数产生的字节完全相同。
    """
    return f"event: {event}\ndata: {json.dumps(data, ensure_ascii=False)}\n\n"

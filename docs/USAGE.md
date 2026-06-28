# mimo-mcp 使用指南

> 把小米 MiMo 的全模态能力(对话 / 图像 / 视频 / TTS / 声音克隆 / 声音设计 / ASR)接到日常工作流。
>
> 文档配套版本:**v0.1**(M0 仓库脚手架 + M1 SDK 适配层已完成)
> PRD 全文:[`docs/PRD.md`](PRD.md)

---

## 一、开始前的检查清单

按顺序勾掉,任何一项失败都不要往下走:

```bash
cd /Users/Frank-ay/Desktop/xiaomi-MIMO

# 1) Python 依赖装好
uv sync

# 2) .env 填好 key 和 base_url
cp .env.example .env   # 第一次需要;之后跳过
#   编辑 .env:
#   - MIMO_API_KEY      = 平台控制台拿到的真 key(普通 sk- / 套餐 tp- 都行)
#   - MIMO_BASE_URL     = 普通 key 用 https://api.xiaomimimo.com/v1
#                          套餐 key 用控制台「专属 Base URL」给的地址
#                          (例:https://token-plan-cn.xiaomimimo.com/v1)

# 3) 一键自检(应当至少前 3 项 [OK])
uv run python scripts/check.py
```

期望输出:

```
[OK]  API Key 已配置
[OK]  base_url 可达
[OK]  鉴权合法
[? ]  云端 ASR 可用      ← Token Plan 套餐不含 ASR,显示 [X] 也算正常
```

如果 base_url 通但鉴权不通,99% 是「套餐 key 用了普通 base_url」——用控制台「专属 Base URL」覆盖 `MIMO_BASE_URL`。

---

## 二、三种使用方式

### 方式 1:Claude Code / Codex 里调 MCP tool(最日常)

注册一次(已做过可跳):

```bash
# Claude Code
python3 -c "
import json, pathlib
p = pathlib.Path.home() / '.claude' / 'settings.local.json'
d = json.loads(p.read_text())
d.setdefault('mcpServers', {})['mimo-mcp'] = {
    'command': '/Users/Frank-ay/Desktop/xiaomi-MIMO/scripts/run_mcp.sh'
}
p.write_text(json.dumps(d, indent=2, ensure_ascii=False) + '\n')
"

# Codex
cat >> ~/.codex/config.toml <<'EOF'

[mcp_servers.mimo-mcp]
command = "/Users/Frank-ay/Desktop/xiaomi-MIMO/scripts/run_mcp.sh"
EOF
```

**重启** Claude Code / Codex 让它们加载新配置。然后在对话框里就能用自然语言唤起:

> 「用 mimo.tts 把下面这段话用茉莉的声音读出来:今天天气真不错。」
> 「先调用 mimo.image_understand 看看 ~/Desktop/x.png,然后总结一句话。」
> 「调 mimo.voice_list 列出我有哪些音色。」

### 方式 2:本地 Web 控制台(适合调试和管理)

```bash
# 终端 1 — 后端(FastAPI :7801)
./scripts/run_web.sh

# 终端 2 — 前端开发模式(:5173,代理到后端)
cd webui/frontend
./node_modules/.bin/vite
# 或者:pnpm dev
```

打开浏览器:<http://127.0.0.1:5173/>

7 个页面用途见本文 §五。

> 生产部署:`./scripts/build_frontend.sh` 把前端打到 `webui/frontend/dist`,后端启动后会同源托管,只需访问 <http://127.0.0.1:7801/>。

### 方式 3:直接当 Python SDK(适合脚本化批处理)

```python
# script.py
import asyncio
from mimo_mcp.api.chat import chat_completion
from mimo_mcp.api.tts import synthesize, seed_default_voices
from mimo_mcp.config import get_settings
from mimo_mcp.models import ChatMessage, ChatRequest, TTSRequest
from mimo_mcp.storage import Storage


async def main():
    settings = get_settings()
    storage = Storage(settings.db_path)
    await storage.init()
    await seed_default_voices(storage)

    # 文本对话
    chat = await chat_completion(ChatRequest(
        messages=[ChatMessage(role="user", content="用一句话介绍小米 MiMo。")],
        model="mimo-v2.5",
    ))
    print(chat["choices"][0]["message"]["content"])

    # 文本转语音
    tts = await synthesize(
        TTSRequest(text="你好,这是脚本化批处理的演示。", voice="苏打"),
        storage,
    )
    print("音频写入:", tts["audio_path"])


asyncio.run(main())
```

运行:`uv run python script.py`

---

## 三、11 个 MCP Tool 速查

| # | Tool | 用途 | 输入要点 | 返回要点 |
|---|---|---|---|---|
| 1 | `mimo.chat` | 多模态对话 | `messages[]`,`model?` 默认 v2.5-pro,`max_tokens?` 默认 4096 | OpenAI 格式响应,thinking 模型把推理放在 `reasoning_content` |
| 2 | `mimo.image_understand` | 图像理解 | `images[]`(每项 path/url/base64 三选一),`prompt` | 文本描述 |
| 3 | `mimo.video_understand` | 视频理解 | `video_url`(http(s)),`prompt` | 文本描述 |
| 4 | `mimo.tts` | 文本合成语音 | `text`,`voice` 或 `voice_id` | `{audio_path, voice, source, model, bytes}` |
| 5 | `mimo.voice_clone_create` | 上传参考音频克隆 | `reference_audio_path`,`name` | `VoiceRecord`(含可复用 voice_id) |
| 6 | `mimo.voice_design_create` | 文字描述生成音色 | `voice_prompt`,`name`,`sample_text?` | `VoiceRecord` |
| 7 | `mimo.voice_list` | 列本地音色库 | `source?`(default/clone/design) | `VoiceRecord[]` |
| 8 | `mimo.voice_delete` | 删本地音色 | `voice_id` | `{deleted: bool}` |
| 9 | `mimo.asr` | 语音转写 | `audio_path` 或 `audio_url`,`language?`(auto/zh/en) | 纯文本转写结果(长音频自动分段,可选说话人分离) |
| 10 | `mimo.health` | 健康自检 | — | `{api_key_configured, base_url_reachable, auth_valid, asr_cloud_available}` |
| 11 | `mimo.usage` | 本地用量统计 | `since_hours?` 默认 24 | `{calls, errors, by_tool, ...}` |

### 预置 voice 列表(F4 / F5 / F6 都能用)

| voice_id | 类型 | 风格 |
|---|---|---|
| `mimo_default` | 中性 | 默认音色,清晰中性 |
| `冰糖` | 中文女 | 温暖甜润 |
| `茉莉` | 中文女 | 端庄大方 |
| `苏打` | 中文女 | 活泼明亮 |
| `白桦` | 中文男 | 沉稳磁性 |
| `Mia` | 英文女 | clear & natural |
| `Chloe` | 英文女 | soft & warm |
| `Milo` | 英文男 | friendly & casual |
| `Dean` | 英文男 | deep & authoritative |

---

## 四、典型场景脚本(可复制即用)

### 4.1 一句话配音 demo

**MCP 路径(Claude Code 里):**
> 用 mimo.tts 把"欢迎来到小米 MiMo 的演示世界"用 苏打 的声音合成。

返回的 `audio_path` 比如 `data/artifacts/tts/20260430/abc123.wav`,在 macOS 终端:

```bash
afplay data/artifacts/tts/20260430/abc123.wav
```

**Web 路径**(更直观):浏览器打开 <http://127.0.0.1:5173/tts> → 输入文本 → 选 苏打 → 点合成,网页里直接播放 + 下载。

### 4.2 克隆我的声音 → 朗读任意文本

录一段 10–15 秒清晰参考音频(用任何手机/电脑录音),保存为 `~/Desktop/me.wav`。

**Claude Code 里两步:**

1. > 用 mimo.voice_clone_create 上传 ~/Desktop/me.wav,命名"我"

   → 返回 `voice_id: clone_xxxxxx`,且自动生成一段试听 wav 在 `data/artifacts/tts/<日期>/<voice_id>_sample.wav`,先试听一下满不满意。

2. > 用 mimo.tts 把这段文章用 voice_id=clone_xxxxxx 读完:<粘贴文章>

   背后会自动路由到 `mimo-v2.5-tts-voiceclone` 模型 + 重建参考音频 DataURL。

### 4.3 设计一个音色 → 朗读

> 用 mimo.voice_design_create 创建音色:voice_prompt="40 岁男性纪录片旁白,沉稳带磁性,语速偏慢",name="纪录片男声"

返回 `voice_id: design_xxxxxx`,试听一段。然后:

> 用 mimo.tts 把这段解说稿用 voice_id=design_xxxxxx 读出来。

(voicedesign 是 stateless 接口。创建时会生成一段试听音频并固化到本地 `reference_path`;后续用该 voice_id 朗读新文本时,实际改走 `voiceclone` 模型复刻那段试听音频,而非每次重新生成设计,以此锁定音色避免漂移。)

### 4.4 看图说话 → 配音

> 第一步:用 mimo.image_understand 看 ~/Desktop/poster.png,用 80 字概括它的主要内容。
> 第二步:把上面的概括用 mimo.tts(voice="冰糖")合成一段语音。

### 4.5 视频内容总结 + 旁白

`mimo.video_understand` 现在的 `video` 参数自动识别 4 种输入:

```
mimo.video_understand(video="~/Desktop/clip.mp4", prompt="...")           # 本地路径
mimo.video_understand(video="https://www.bilibili.com/video/BVxxxx/", ...)  # B 站(yt-dlp)
mimo.video_understand(video="https://example.com/clip.mp4", ...)            # 直链(自动下载)
mimo.video_understand(video="data:video/mp4;base64,...", ...)               # DataURL
```

后端会:
1. 把所有输入归一化成 base64 DataURL(最稳定)
2. B 站/YouTube/抖音 等页面型链接走 yt-dlp 下载
3. 直链 mp4 走 httpx.stream 本地下载
4. 本地路径 / DataURL 直接读

文件 ≤ 50 MB(原始字节),约对应 30 秒-2 分钟 720p 视频。

(实测发现:MiMo 服务端对外网 URL 的主动下载不可靠,所以本仓库统一在客户端落地后再发 DataURL。详见本文[附录:API 实测备注](#附录api-实测备注)。)

### 4.6 长视频分段分析(突破 50 MB 上限)

MiMo 单次请求 base64 ≤ 50 MB(实测约对应 35 MB 原始 / 90 秒 720p)。要分析 5 分钟 / 1GB 视频,用「分段分析」模式:

**Web 路径**(推荐):浏览器 `/vision` → 视频模式 → 勾选「长视频分段分析」 → 拖动滑块设每段时长(20-90 秒)→ 上传文件或贴 URL → 实时看每段处理进度 + 最终综合输出。

**SDK 路径**(脚本化):
```python
from mimo_mcp.api.vision import video_understand_chunked

async for evt in video_understand_chunked(
    "/path/to/long_video.mp4",
    "描述这段视频",
    segment_seconds=50,
):
    if evt["kind"] == "plan":
        print(f"切成 {evt['total']} 段,总时长 {evt['duration']:.0f}s")
    elif evt["kind"] == "segment":
        print(f"段 {evt['index']+1}: {evt['description'][:80]}…")
    elif evt["kind"] == "summary":
        print("综合分析:", evt["text"])
```

**API 路径**(curl + SSE):
```bash
curl -N -X POST http://127.0.0.1:7801/api/vision/video/chunked \
  -F 'file=@long.mp4' -F 'prompt=描述视频' -F 'segment_seconds=50'
```

实测 47 MB / 107 秒 AV1 视频 → 切 2 段 → 完整综合分析,总耗时 ~3 分钟。

### 4.7 长文批量配音(增量任务 1 新增)

**Web 路径**(推荐,可视化进度):浏览器 `/tts` → 切到「批量切段」 Tab → 贴一段 1000 字以上长文 → 拖滑块到 100-150 字/段 → 点合成 → 每段做完立刻在页面出现并可单独播放,全部完成后在「本会话历史」可一次性回看。

**SDK 路径**(脚本化):
```python
from mimo_mcp.api.tts import synthesize_batch
from mimo_mcp.config import get_settings
from mimo_mcp.storage import Storage

storage = Storage(get_settings().db_path)
await storage.init()
async for seg in synthesize_batch("……长文……", voice="苏打", segment_max_chars=120, storage=storage):
    print(f"段 {seg.index+1}/{seg.total}: {seg.audio_path} ({seg.bytes} B)")
```

---

## 五、Web 控制台 8 个页面用法

| 页面 | URL | 你能在这里做什么 |
|---|---|---|
| 概览 | `/` | 看 API Key 状态 / base_url 可达性 / 鉴权 / ASR / 24h 用量 |
| 聊天沙盒 | `/sandbox` | 切换模型(v2.5-pro / v2.5 / v2-pro / v2-flash),发文本对话验真 |
| **文字转语音** | `/tts` | **单段或批量长文朗读 · 9 个预置 voice + 已克隆/设计的全部 · wav/mp3 · localStorage 历史** |
| 图像 / 视频 | `/vision` | 上传图片;视频支持 **本地文件** 或 **B 站 / YouTube / 抖音 / 小红书 URL**(yt-dlp 自动下载)。单次 ≤ 35 MB / 90 秒。**勾「长视频分段分析」可分析任意时长视频**(自动切段+综合,突破 50 MB 上限) |
| 音色库 | `/voices` | 浏览 / 试听 / 删除全部音色(default + clone + design) |
| 声音克隆 | `/voices/clone` | 拖一段参考音频 + 命名 + 备注 → 一键创建 |
| 声音设计 | `/voices/design` | 写音色 prompt + 试听文本 → 一键生成 |
| 语音转写 | `/asr` | 上传音频做 ASR(中英自动/指定);长音频自动分段转写;可选 sherpa-onnx 离线说话人分离;支持导出 .txt / SRT / JSON |
| 审计日志 | `/audit` | 看最近 200 次 MCP/Web 调用,5 秒自动刷新 |

### 5.1 「文字转语音」页详解

- **单段模式**:输入 ≤ 200 字 → 选音色 → 选 wav/mp3 → 点合成 → 页面播放器自动播放,可下载
- **批量模式**:贴长文 → 拖动"分段字数上限"滑块(20–300)→ 合成会按句末标点自动切段 → SSE 流逐段返回,前端就绪一段播一段
- **音色下拉**:三组(预置 / 克隆 / 设计),与「音色库」实时同步——刚克隆的 voice 立刻能在这里选用
- **历史**:本次会话最多 20 条,localStorage 持久(刷新还在,换会话清空);每条可展开看所有段落 + 重新试听
- **隐藏字段**:`audio.speed`/`audio.style` 实测无效(speed 反向、style 字节不变),UI 不暴露、字段已移除;风格请改用 `instructions` 自然语言描述(v2.5 导演模式)

### 5.2 后端 TTS API(供脚本化调用)

| Endpoint | 用途 |
|---|---|
| `POST /api/tts/synthesize` | 单段一次性,JSON 返回 `{audio_url, voice, model, bytes}` |
| `POST /api/tts/batch` | 批量切段,SSE 流(`event: plan` / `event: segment` / `event: done` / `event: error`) |
| `GET /api/tts/audio/<filename>` | 反代 `data/artifacts/tts/**` 与 `voice_refs/`,给 `<audio src>` 直接用 |

> Web 与 MCP **共享同一份 SQLite + 同一个 voice 库** —— 在 Claude Code 里克隆出来的 voice 立刻在 Web 看得到,反之亦然。

---

## 六、常见问题(FAQ)

**Q1:跑 mimo.tts 报 `Unknown voice: xxx`?**
A:你用的 `voice` 不在预置列表里。要么用 §三 表里 9 个之一,要么先 `mimo.voice_clone_create` / `mimo.voice_design_create` 拿到 voice_id 再传。

**Q2:Claude Code 看不到 mimo 的 tool?**
A:① 确认 `~/.claude/settings.local.json` 里有 `mcpServers.mimo-mcp` 段;② 重启 Claude Code;③ 跑 `./scripts/run_mcp.sh` 直接看终端输出,验证脚本本身能起。

**Q3:返回 401 / Invalid API Key?**
A:绝大多数情况是 `MIMO_BASE_URL` 与 key 类型不匹配。
- key 以 `tp-` 开头 → 套餐 key,用控制台「专属 Base URL」(典型 `https://token-plan-cn.xiaomimimo.com/v1`)
- key 以 `sk-` 开头 → 普通 key,用 `https://api.xiaomimimo.com/v1`

**Q4:chat 返回 `content` 为空只有 `reasoning_content`?**
A:v2.5 系列是 thinking 模型,默认会先做思考。给的 `max_tokens` 太小会让它没机会输出最终回复。本仓库已默认 4096,长任务可临时调到 8192+。

**Q5:ASR 转写怎么用?支持哪些语言?**
A:`mimo.asr` 工具支持 `language=auto`(默认)/ `zh` / `en`。内部走 `/chat/completions` 接口,以 base64 `input_audio` 传音频,模型 `mimo-v2.5-asr`。返回**纯文本**,无时间戳或说话人信息。

长音频会自动用 ffmpeg 按时长切段后逐段转写再拼接。Web UI(`/asr`)还额外支持 **sherpa-onnx 离线说话人分离**(自动检测人数或手动指定),并可导出三种格式:带说话人标注的 `.txt`、SRT 字幕、JSON 结构化数据。

**Q6:产物 wav 在哪?**
- 单次 TTS:`data/artifacts/tts/<yyyymmdd>/<uuid>.wav`
- 克隆参考音频:`data/artifacts/voice_refs/<voice_id>.wav`
- 设计试听样本:同上目录,文件名 `<voice_id>.wav`
- 克隆首次试听:`data/artifacts/tts/<yyyymmdd>/<voice_id>_sample.wav`

整个 `data/` 已在 `.gitignore`,放心。

**Q7:套餐"仅限编程工具"会不会被风控?**
A:本仓库的 mimo-mcp + Web 沙盒都属合规用法(都是编程工具开发链路)。**避免**做以下事情:
- 把套餐 key 包到面向终端用户的应用里
- 高频自动化压测 / 爬虫式批量调用
- 把 key 上传到任何公网

**Q8:怎么停掉后端 / 前端?**
```bash
lsof -ti:7801 | xargs kill   # 后端
lsof -ti:5173 | xargs kill   # 前端
```

---

## 七、调试与故障排查

```bash
# 健康自检(不消耗 token)
uv run python scripts/check.py

# 跨进程 stdio 握手测试(模拟 Claude Code 调用路径)
uv run pytest -q tests/test_stdio_handshake.py

# 真·联网集成测试(消耗少量 token,验证 SDK 全链路)
MIMO_RUN_LIVE=1 uv run pytest -q tests/test_live.py

# 查看本地 audit_log(SQLite)
sqlite3 data/mimo.db 'SELECT ts, channel, tool, status, error FROM audit_log ORDER BY id DESC LIMIT 20;'

# 测试一发 chat 看 raw 响应结构
uv run python - <<'PY'
import asyncio, sys, json
sys.path.insert(0, 'src')
from mimo_mcp.api.chat import chat_completion
from mimo_mcp.models import ChatMessage, ChatRequest

async def main():
    r = await chat_completion(ChatRequest(
        messages=[ChatMessage(role='user', content='ping')],
        model='mimo-v2.5'))
    print(json.dumps(r, ensure_ascii=False, indent=2))

asyncio.run(main())
PY
```

---

## 八、扩展(给开发者)

| 想做的事 | 改哪里 |
|---|---|
| 加新模型默认值 | `src/mimo_mcp/config.py` 的 `MimoSettings` 字段 |
| 新增 MCP tool | 在 `src/mimo_mcp/server.py` 用 `@mcp.tool()` 装饰新函数,业务编排放 `src/mimo_mcp/api/<feature>.py` |
| 新增 Web API | 在 `webui/backend/routers/` 加新文件,`webui/backend/main.py` 里 `include_router` |
| 新增前端页面 | `webui/frontend/src/pages/` 加文件 + `App.tsx` 注册路由 + `components/Layout.tsx` 加导航项 |
| 改 thinking max_tokens 默认 | 修 `.env` 的 `MIMO_DEFAULT_MAX_TOKENS` |

---

## 九、参考链接

- PRD 全文:[docs/PRD.md](PRD.md)
- 官方文档:<https://platform.xiaomimimo.com/docs/api/chat/openai-api>
- 官方模型矩阵:<https://mimo.xiaomi.com/>
- LiteLLM provider:<https://docs.litellm.ai/docs/providers/xiaomi_mimo>

---

## 附录:API 实测备注

以下为 Phase 0(2026-04-30)实测的硬结论,作为代码层设计依据长期存档。

### TTS stream=true 是"伪流式"

`stream: true` 时接口返回 SSE,但 wav 数据在**单一 chunk** 内一次性返回,并非 chunk-by-chunk 增量音频。因此前端不需要 MediaSource API,"边生成边播"不可行,实际行为是"等完整 wav 收到后立即播放"。

### audio.speed / audio.style 实测无效

| 字段 | 行为 |
|---|---|
| `audio.speed=0.5/1.0/2.0` | 字段被接受,但 speed 越大 duration 反而越长(效果与预期相反) |
| `audio.style="gentle but tired"/"happy"` | 字段被接受,但产物字节完全一致,风格未变化 |

结论:两个字段**当前不可用**。UI 不暴露,字段已从请求模型移除。风格控制请改用 `instructions` 自然语言描述(v2.5 导演模式)。

### TTS format 支持矩阵

| format | 状态 | 备注 |
|---|---|---|
| `wav` | ✅ | RIFF 头,默认推荐 |
| `mp3` | ✅ | MPEG ADTS,体积约为 wav 的 1/5 |
| `pcm` | ✅(SDK 专用) | 原始 PCM,适合后端二次处理 |
| `pcm16` | ✅(SDK 专用) | 16-bit PCM |
| `opus` | ❌ | 报错 `Unsupported audio format: opus` |

UI 仅暴露 wav / mp3;pcm / pcm16 仅留 SDK 给高级用户。

### 视频输入稳定性矩阵

| 输入形式 | 可靠性 | 说明 |
|---|---|---|
| `data:video/mp4;base64,...` DataURL | ✅ 最稳定,推荐 | 本仓库统一归一为此形式 |
| 直链 mp4 URL(http(s)) | ⚠️ 不可靠 | MiMo 后端拉外网时随机报 400 `failed to download url data` |
| B 站/YouTube/抖音等页面型 URL | ❌ 不可用 | MiMo 直接拿不到 mp4(返回 HTML) |

本仓库统一在客户端落地:直链走 `httpx.stream` 本地下载,B 站等走 `yt-dlp` 下载,本地路径直读,全部转为 DataURL 后上传。文件 ≤ 50 MB 原始字节(base64 后 ~67 MB)。

Laybot 待命中!

# MiMo MCP Server — 产品需求文档(PRD v1.0)

> 注:本 PRD 为立项基线文档,部分 F7(ASR)/TTS 设计已演进,实际实现以代码与 docs/USAGE.md 为准。

> 项目代号:**mimo-mcp**
> 文档归属:`docs/PRD.md`
> 撰写日期:2026-04-29(M0 + M1 + 增量任务 1 实施完毕,内容已包含全部实测发现)

**已确认的关键路径**(2026-04-29 用户拍板):
- 实现语言:**Python 3.11 + FastMCP**(用 uv 管理依赖)
- Transport:**仅 stdio**(Claude Code + Codex 双注册)
- Web 前端栈:**Vite + React + shadcn/ui**(独立打包,本地 127.0.0.1)
- MVP 范围:**全功能 F1-F8**(Chat / 图像 / 视频 / TTS / 声音克隆 / 声音设计 / ASR / Dashboard 全部纳入 V1)
- ASR 兜底:**仅云端**,无本地兜底,云端缺失则 F7 显式 `unavailable`

---

## 1. 背景(Context)

小米 MiMo 在 2026-04 正式开放 V2.5 系列模型,在同价位段提供了少见的"1M 上下文 + 全模态(图/视频/音) + 工具调用 + 语音克隆/合成/识别"全栈能力,且明确兼容 OpenAI Chat Completions 协议、官方文档承诺与 Claude Code、Codex、Cline 等开发工具链互通。

但 MiMo **目前没有官方 MCP Server**,要把它的高级能力(尤其是语音克隆、TTS、图像/视频理解)接到日常工作流(Claude Code、Codex)里,只能手写 wrapper、来回切换工具。这阻碍了 Void 战机内容流水线、电影编剧多媒体闭环、日常成本优化路由等已规划项目的落地。

## 2. 目标与非目标

### 目标(In Scope)
- **G1**:封装 MiMo 核心能力为一个 MCP Server,**同时被 Claude Code 与 Codex 当作 tool 调用**,用 stdio 注册即可零运维使用。
- **G2**:覆盖**最高级模型**优先(`mimo-v2.5-pro` / `mimo-v2.5` / `mimo-v2.5-tts*` / `mimo-v2.5-asr`),Flash/Omni 作为可选回退路径。
- **G3**:提供配套**本地 Web 管理页面**,完成 stdio MCP 难以承载的"上传素材 / 试听音频 / 浏览视频结果 / 管理克隆音色库"。
- **G4**:工程上可管理、可演进——清晰的目录、可单测的 SDK 适配层、可独立运行的 Web、可单独发布的 MCP。

### 非目标(Out of Scope,V1 不做)
- 多用户/SaaS 化部署、OAuth、计费体系
- 训练 / 微调能力
- 在本地部署 MiMo 开源模型(全部走云 API)
- 移动端 / 桌面 GUI
- 中文以外的产品 UI 语言

## 3. 目标用户与典型使用场景

**主用户**:本机用户(Claude Code / Codex 重度用户)。

**典型场景**:
- **场景 A**(Claude Code 开发):写代码到一半,想给 README 生成一段配音 demo → 调 `mimo.tts(...)` tool → 拿到音频文件路径,直接嵌入产物。
- **场景 B**(Codex 自动化):脚本里收到一段用户上传的语音 → 调 `mimo.asr(...)` 转写 → 后续逻辑串联。
- **场景 C**(Void 战机内容流水线):为新关卡 Boss 生成 30 秒台词 → 先 `mimo.voice_clone(reference)` 注册音色 → 再 `mimo.tts(text, voice_id)` 批量出音。
- **场景 D**(多模态调研):导演拿一段 1 分钟视频 + 5 张分镜图 → 调 `mimo.video_understand(...)` 与 `mimo.image_understand(...)` 输出剧本初稿,V2.5 长上下文一次吃完。
- **场景 E**(Web 管理):打开 `http://localhost:7801`,上传参考音频→生成克隆 voice_id→站内 H5 player 试听→满意后入库,后续 MCP tool 可直接用 `voice_id`。

## 4. 核心功能列表(MVP)

| 编号 | 功能 | MCP Tool | Web 页面 | 备注 |
|---|---|---|---|---|
| F1 | **多模态对话**(文本+图像+视频统一聊天) | `mimo.chat` | ✓(对话沙盒页) | 模型可选 `v2.5-pro` / `v2.5` / `v2-flash` |
| F2 | **图像理解**(单张/多张分析、OCR、定位) | `mimo.image_understand` | ✓(上传图 → 文本结果) | OpenAI 标准 image_url / base64 |
| F3 | **视频理解**(场景描述、内容摘要) | `mimo.video_understand` | ✓(上传视频 → 文本结果) | 优先 URL 模式;时长上限以平台为准 |
| F4 | **TTS 语音合成**(默认音色、风格标签) | `mimo.tts` | ✓(文本 → 音频试听 + 下载) | 输出 wav,可指定 `voice_id` |
| F5 | **声音克隆**(上传参考音频 → voice_id) | `mimo.voice_clone_create` / `mimo.voice_list` | ✓(音色库 + 试听) | voice_id 持久化到本地 SQLite |
| F6 | **声音设计**(文字描述 → 自定义音色) | `mimo.voice_design_create` | ✓(prompt 输入 → 试听 → 入库) | 同样产出 voice_id |
| F7 | **ASR 语音转写**(多语种 / 方言) | `mimo.asr` | ✓(上传音频 → 文本+时间戳) | 若云端 API 缺失,V1 仅做 stub |
| F8 | **健康检查 & 用量** | `mimo.health` / `mimo.usage` | ✓(顶部 dashboard) | 显示余额、限流、最近调用 |

> **优先级(已定稿)**:F1-F8 全部纳入 V1。F7 ASR 云端 API 形态需在 M1 阶段实测确认;若实测云端 API 不存在,F7 在 V1 内 tool/Web 状态显式置为 `unavailable`,并给出"等待 MiMo 官方开放"的清晰提示——**不预置任何本地模型**(决定见 §15-Q6)。

## 5. MVP vs Future

| 阶段 | 内容 |
|---|---|
| **V1 (MVP,本次交付)** | F1-F8 全量(含 ASR);stdio MCP + 本地 Web;支持 Claude Code/Codex 双注册;voice 库 SQLite 持久化 |
| **V1.1** | 流式 TTS;Web 端批量任务队列;ASR 长音频分片;Web 国际化 |
| **V2** | HTTP/SSE 远程 transport;OAuth;多用户音色库;与 Void/lay-screenwriter/libtv 等 skill 串联工作流模板 |

## 6. 技术架构

### 6.1 总体结构(模块边界)

```
/Users/Frank-ay/Desktop/xiaomi-MIMO/
├── pyproject.toml             # uv 管理,Python 3.11+
├── README.md                  # 一页快速上手
├── .env.example               # MIMO_API_KEY、MIMO_BASE_URL、PORT 等
├── src/mimo_mcp/
│   ├── __init__.py
│   ├── config.py              # 环境变量加载、默认值
│   ├── client.py              # HTTPX async 客户端,包装 OpenAI 兼容接口 + 多模态扩展
│   ├── models.py              # pydantic 模型(请求/响应/voice 记录)
│   ├── storage.py             # SQLite + 本地文件管理(voice/audio/image/video)
│   ├── api/
│   │   ├── chat.py            # F1
│   │   ├── vision.py          # F2/F3
│   │   ├── tts.py             # F4
│   │   ├── voice_clone.py     # F5
│   │   ├── voice_design.py    # F6
│   │   ├── asr.py             # F7
│   │   └── usage.py           # F8
│   ├── server.py              # FastMCP 入口,绑定全部 tools
│   └── tools/                 # 每个 MCP tool 一个文件,薄壳 + schema
├── webui/                     # 本地管理 UI
│   ├── backend/               # FastAPI 路由,复用 src/mimo_mcp 的 SDK
│   │   ├── main.py            # uvicorn 入口,挂载 / 静态产物 + /api/* 路由
│   │   └── routers/           # voices.py / chat.py / vision.py / asr.py / usage.py
│   └── frontend/              # Vite + React + shadcn/ui (pnpm)
│       ├── package.json
│       ├── vite.config.ts
│       ├── src/pages/         # Sandbox / Voices / VoiceClone / VoiceDesign / ASR / AuditLog
│       ├── src/components/ui/ # shadcn 生成的组件
│       └── src/lib/api.ts     # 封装到 FastAPI /api 的客户端
├── data/                      # 运行期产物(.gitignore)
│   ├── mimo.db                # SQLite:voices, sessions, audit_log
│   └── artifacts/             # 生成的音频、上传的素材
├── scripts/
│   ├── run_mcp.sh             # stdio 启动脚本(Codex 因 TOML 不支持 env 复杂值)
│   └── run_web.sh             # Web UI 启动脚本
└── tests/                     # pytest,client + tools 单测,Web smoke 测
```

### 6.2 技术栈(已定稿)

| 层 | 选型 | 理由 |
|---|---|---|
| MCP Server | **Python 3.11 + FastMCP** | 装饰器式 tool 注册 + 内置 schema 推导,迭代速度快;与 anthropic-skills `mcp-builder` 推荐一致 |
| HTTP Client | **httpx (async)** | 与 FastMCP/FastAPI 异步生态一致,支持流式 |
| 数据校验 | **pydantic v2** | 请求/响应/Tool inputSchema 一处定义 |
| 持久化 | **SQLite + 本地文件系统** | 零运维,voice 库 < 1 万条够用 |
| Web 后端 | **FastAPI**(与 MCP 同 codebase,独立进程) | 共享 SDK 适配层,避免重复实现 |
| Web 前端 | **Vite + React 18 + TypeScript + shadcn/ui + Tailwind** | 轻、构建快、组件库成熟,音视频试听交互友好;独立 `webui/frontend` 打包,产物由 FastAPI 静态托管 |
| 状态管理 | **TanStack Query** | 调用 FastAPI 的 voice/usage 列表用 query,无需引 Redux |
| 包管理 | **uv**(后端) + **pnpm**(前端) | 与本机 `adb-mysql-mcp-server` 范本一致(参考 `~/.claude/settings.local.json`) |
| Transport | **stdio 单一**(Claude Code + Codex 共享) | MVP 不上 HTTP/SSE,降低 V1 范围 |

### 6.3 复用的现有资产(已经过本机调研)

| 资产 | 路径 | 复用方式 |
|---|---|---|
| Python MCP 服务器骨架 | `/Users/Frank-ay/Downloads/mcp/alibabacloud-adb-mysql-mcp-server/src/adb_mysql_mcp_server/server.py` | 直接拷 Tool/Resource/Error 注册模式,把 `pymysql` 换成 `httpx` |
| FastMCP 简化范式 | `/Users/Frank-ay/Downloads/mcp/blender-mcp/src/blender_mcp/server.py` | 用 `@mcp.tool()` 装饰器替代 `Server` 类,样板更少 |
| Stdio 注册写法 | `~/.claude/settings.local.json`(L30-46) + `~/.codex/config.toml`(L41-47) | 抄成 `mimo-mcp` 段落,改 command/env |
| 异步任务轮询模式 | `~/.agents/skills/libtv-skill/scripts/` | 视频理解/克隆审核走"提交→轮询"时复用此模式 |
| MCP 高质量构建指南 | `~/.claude/plugins/marketplaces/claude-plugins-official/plugins/mcp-server-dev/skills/build-mcp-server/SKILL.md` | 按其检查清单做 schema/error/instructions/progress |
| 现有 skill 联动接口 | `~/.claude/skills/{void-story-generator,lay-screenwriter,libtv-skill}` | V2 阶段做 workflow 模板时引用 |

## 7. MCP Tool 表(暴露给 Claude Code / Codex)

| Tool 名 | 输入(关键字段) | 输出 | 模型默认 |
|---|---|---|---|
| `mimo.chat` | `messages[]`、`model?`、`tools?`、`stream?` | 文本(可流) | `mimo-v2.5-pro` |
| `mimo.image_understand` | `images[]` (path/url/base64)、`prompt`、`model?` | 文本 | `mimo-v2.5` |
| `mimo.video_understand` | `video` (path/url)、`prompt`、`model?` | 文本 | `mimo-v2.5` |
| `mimo.tts` | `text`、`voice_id?`、`format?` (wav)、`style?` | 本地音频文件路径 | `mimo-v2.5-tts` |
| `mimo.voice_clone_create` | `reference_audio` (path)、`name`、`description?` | `voice_id` + 状态 | `mimo-v2.5-tts-voiceclone` |
| `mimo.voice_design_create` | `voice_prompt`、`name` | `voice_id` | `mimo-v2.5-tts-voicedesign` |
| `mimo.voice_list` | `query?` | voice 元数据数组 | — |
| `mimo.voice_delete` | `voice_id` | OK | — |
| `mimo.asr` | `audio` (path/url)、`language?` (auto)、`with_timestamps?` | 文本 + 段落 | `mimo-v2.5-asr` |
| `mimo.health` | — | base_url 可达性、API key 有效性 | — |
| `mimo.usage` | `since?` | 余额、最近调用统计 | — |

> **设计原则**:`tool` 数量目前 11 个,落在 anthropic 推荐的"单工具模式 < 15"范围内,**不必引入 search+execute 模式**。

## 8. Web 本地管理页面(端口默认 7801)

| 模块 | 功能 |
|---|---|
| **顶部 dashboard** | API 余额 / 最近 24h 调用次数 / MCP server 健康状态 |
| **聊天沙盒** | 选模型、上传图/视频、看流式输出 — 用于快速验证 |
| **音色库** | 列出 voices(默认 + 克隆 + 设计);可试听、改名、删除、设为默认 |
| **声音克隆向导** | 上传参考音频 → 命名 → 提交 → 轮询状态 → 成功后试听并入库 |
| **声音设计向导** | 文字 prompt → 生成 → 试听 → 入库 |
| **ASR 工作台** | 上传音频 → 实时显示转写 + 时间戳 |
| **审计日志** | 最近 100 次 MCP/Web 调用,含 tokens/耗时/错误 |

## 9. 数据与存储

- **SQLite**(`data/mimo.db`)
  - `voices(voice_id PK, name, source[default|clone|design], reference_path, voice_prompt, status, created_at)`
  - `sessions(id PK, kind, payload_json, created_at)`(Web 沙盒会话)
  - `audit_log(id PK, ts, channel[mcp|web], tool, model, input_tokens, output_tokens, latency_ms, status, error)`
- **文件系统**(`data/artifacts/`)
  - `voice_refs/<voice_id>.wav` 参考音频
  - `tts/<yyyymmdd>/<uuid>.wav` 合成产物
  - `uploads/<yyyymmdd>/<uuid>.{jpg|mp4|...}` 用户上传
- **保留策略**:V1 不自动清理,Web 提供"清理 30 天前"按钮。

## 10. 配置与部署

### 10.1 环境变量(`.env`)

```env
MIMO_API_KEY=sk-xxx              # 必填
MIMO_BASE_URL=https://api.xiaomimimo.com/v1
MIMO_DEFAULT_TEXT_MODEL=mimo-v2.5-pro
MIMO_DEFAULT_VISION_MODEL=mimo-v2.5
MIMO_DEFAULT_TTS_MODEL=mimo-v2.5-tts
MIMO_WEB_PORT=7801
MIMO_DATA_DIR=./data
```

### 10.2 Claude Code 注册(`~/.claude/settings.local.json` 追加)

```json
"mcpServers": {
  "mimo-mcp": {
    "command": "uv",
    "args": ["--directory", "/Users/Frank-ay/Desktop/xiaomi-MIMO", "run", "mimo-mcp"],
    "env": { "MIMO_API_KEY": "sk-xxx" }
  }
}
```

### 10.3 Codex 注册(`~/.codex/config.toml` 追加)

```toml
[mcp_servers.mimo-mcp]
command = "/Users/Frank-ay/Desktop/xiaomi-MIMO/scripts/run_mcp.sh"
```

> Codex 的 TOML 不便传递复杂 env,统一通过 `run_mcp.sh` 加载 `.env` 后再启动 `uv run mimo-mcp`。

## 11. 非功能要求

- **安全**:API Key 仅出现在 `.env`(.gitignore)、不写日志;Web UI 默认仅 `127.0.0.1` 监听,不暴露公网;克隆素材本地保存,前端禁止外链。
- **错误处理**:所有 tool 实现统一 `try/except` → 转 `McpError` + 错误码;HTTP 401/402/429 给出明确文案与建议(检查 key / 充值 / 退避)。
- **可观测**:结构化 JSON 日志,字段含 `request_id`、`tool`、`model`、`tokens_in/out`、`latency_ms`;Web 审计页直读 `audit_log` 表。
- **性能**:单 tool 调用 P95 ≤ MiMo API P95 + 50ms 包装开销;并发上限 = MiMo 平台限流(读 response header)。
- **兼容**:Python 3.11+,macOS 14+,Claude Code 当前版 + Codex 当前版均通过冒烟。

## 12. 里程碑(单人全职预估)

| 阶段 | 内容 | 时长 |
|---|---|---|
| M0 仓库脚手架 | uv 项目、`.env.example`、CI(ruff+pytest)、空 `server.py` 跑通 stdio 握手 | 0.5 天 |
| M1 SDK 适配层 | `client.py` + chat/vision/tts/asr/voice_clone/voice_design **全部端点用真 API key 单测打通**;此阶段同时确认 §14 中 ASR/视频/克隆的 3 个未公开细节 | 2-3 天 |
| M2 MCP 工具层 | 11 个 tool 接入 FastMCP + Claude Code/Codex 双注册冒烟通过(stdio) | 1 天 |
| M3 Web 后端 | FastAPI 路由(`/api/voices` `/api/chat` `/api/vision` `/api/asr` `/api/usage`) + SQLite + 文件存储 | 1 天 |
| M4 Web 前端 | 7 个页面(见 §8),Vite+React+shadcn 脚手架 + 联调 | 2-3 天 |
| M5 联调 + 文档 | 端到端真实流(克隆 → 入库 → MCP 出音)、README、错误文案、`run_mcp.sh` | 1 天 |
| **合计** | **≈ 8-10 个工作日(F1-F8 全功能 MVP)** | |

## 13. 验收标准(Done = 全绿)

- ✅ 在 Claude Code 中输入 "用 mimo 把这段文字读出来" → 自动调用 `mimo.tts` → 拿到 `data/artifacts/tts/.../*.wav` 路径
- ✅ 在 Codex 中调用 `mimo.image_understand` 传入本地图 → 输出文本描述
- ✅ Web `http://localhost:7801` 能上传参考音频 → 5 分钟内拿到 voice_id → 用该 voice_id 在 Claude Code 里 `mimo.tts` 出音
- ✅ `mimo.usage` 返回正确余额(对照官网控制台)
- ✅ 异常路径:故意错 API Key → 401 文案"请检查 MIMO_API_KEY";故意超限 → 429 给退避建议
- ✅ `pytest -q` 全绿,核心 SDK 覆盖率 ≥ 80%
- ✅ `README.md` 三步上手(注册/装/跑)且确实可被新手照抄成功

## 14. 风险与未决问题

| 风险 | 概率 | 缓解 |
|---|---|---|
| MiMo TTS 实际是 `/chat/completions` + `audio` 字段而非标准 `/audio/speech` | 高 | M1 第一步:用真 key 各打一发请求,以实际响应为准再写适配层 |
| 视频理解的上传/URL 模式未在公开文档中确认 | 中 | M1 优先 URL 模式,失败回退到"先调用 upload endpoint" |
| **ASR 云端 API 形态**(M1 已实测) | **已确认** | 走 `/chat/completions`,音频以 base64 DataURL 作 `input_audio` 字段传入,model=`mimo-v2.5-asr`,language 支持 `auto/zh/en`,返回纯文本在 `choices[0].message.content`。`/audio/transcriptions` 在 MiMo 网关 404。 |
| 声音克隆 voice_id 字段命名/审核流程未公开 | 中 | M1 用真账号试 1 次提交,以实际响应字段为准;UI 显示"审核中"中间状态 |
| Codex 对 stdio MCP 的稳定性偶现重连失败 | 低 | `run_mcp.sh` 健壮启动 + `mimo.health` 检查 tool + Web Dashboard 显示 MCP 心跳 |
| 大文件(视频/音频)在 stdio 协议下传输慢 | 中 | 约定 tool 入参传"本地路径"或"http(s) URL",**不传 base64 大对象**;Web UI 上传走 FastAPI 不走 MCP |
| **Token Plan 套餐 ≠ 普通 API Key**(M1 实测发现) | **已确认** | 套餐 key 前缀 `tp-`,必须用专属 base URL `https://token-plan-cn.xiaomimimo.com/v1`;套餐**不含 v2-flash / v2.5-asr**;限"编程工具"使用,Web 沙盒只做轻量调试 |
| **v2.5 全系是 thinking 模型**(M1 实测发现) | **已确认** | reasoning chain 默认开启,会先吃 max_tokens 做思考,再生成 content;若 max_tokens 不足只返回 `reasoning_content` + 空 content。已在 `config.default_max_tokens=4096` 兜底,长文任务可调到 8192+ |

## 15. 关键决策点

### 已确认(2026-04-29)

| # | 议题 | 选定 |
|---|---|---|
| Q1 | 实现语言 | **Python 3.11 + FastMCP**(uv 管理) |
| Q2 | Transport | **仅 stdio**;HTTP/SSE 推到 V2 |
| Q3 | Web 前端栈 | **Vite + React 18 + TypeScript + shadcn/ui + Tailwind**(pnpm) |
| Q4 | MVP 范围 | **F1-F8 全量**(含 ASR、声音克隆、声音设计) |
| Q5 | 是否预置 Void/编剧 skill 联动 | **V1 不做**,V2 阶段以工作流模板形式接入 |

### 已确认(续)

| # | 议题 | 选定 |
|---|---|---|
| Q6 | ASR 兜底策略 | **仅 MiMo 云端**;若 M1 实测云端 API 不存在,F7 在 V1 状态置为 `unavailable` 并给出明确提示;**不预置任何本地模型**,不增加项目体积 |

> 至此所有关键路径均已明确,无剩余阻塞决策。

---

## 附录 A:推荐目录树(待 Q1/Q3 拍板后微调)

(已在 §6.1 给出)

## 附录 B:参考文档索引

- 官方 API 文档:`https://platform.xiaomimimo.com/docs/api/chat/openai-api`
- 官方首页 / 模型矩阵:`https://mimo.xiaomi.com/`
- LiteLLM Provider:`https://docs.litellm.ai/docs/providers/xiaomi_mimo`
- 社区 Python wrapper:`https://github.com/Water008/MiMo2API`
- MCP 官方 SDK / 高质量构建指南:`~/.claude/plugins/marketplaces/claude-plugins-official/plugins/mcp-server-dev/skills/build-mcp-server/SKILL.md`

---

# 增量任务 1:Web 文字转语音(TTS)页面 — 进阶版 + 流式

> 撰写日期:2026-04-30
> 状态:**用户已就 4 个关键决策点拍板,本节作为新一轮 plan 进入实施**

## A. 背景(Context)

当前 Web 控制台有 7 个页面,但漏了一个最日常的入口——**任意文本朗读**:
- VoiceClone / VoiceDesign 页只创建音色,创建后没法回到一个统一界面"用这个 voice 朗读任意文本"
- 聊天沙盒只做文本对话,不出音
- 音色库页只是 list + delete

而 SDK 适配层 `src/mimo_mcp/api/tts.py` 的 `synthesize` 已经实现了三模型路由(default / clone / design 各自走对应 MiMo 端点),且本 PRD §8 表里 F4 行写着"文本 → 音频试听 + 下载"——本身就是 V1 应交付的页面,只是 M4 阶段为了保证 7 页面骨架先成型,把 TTS 入口跳过了。本任务把这块补齐,并按用户决策升级到进阶能力。

## B. 已确认的关键决策(2026-04-30)

| # | 议题 | 选定 |
|---|---|---|
| T-Q1 | 页面位置 | **新增独立页 `/tts`**;侧边栏导航新增"文字转语音"项 |
| T-Q2 | 功能范围 | **进阶版**:单段 + **批量长文自动切段** + 本会话历史列表 |
| T-Q3 | 流式 | **V1 即支持流式播放**(边生成边说);非流式作回退 |
| T-Q4 | 高级控制项 | **暴露 voice + format + speed + style 文本标签**(emotion tag 推迟) |

## C. 风险与未知(实施前必须 probe)

| # | 未知 | 缓解 |
|---|---|---|
| R1 | MiMo `/chat/completions` 在 `stream=true` + TTS 模型下返回什么(每 chunk 是不是含 `audio.data` 增量?是不是 SSE 格式?) | Phase 0 探针:发一发 `stream=true` 看响应结构 |
| R2 | `audio.speed` 字段名与取值范围 | Phase 0 探针:试 0.5 / 1.0 / 1.5 / 2.0 |
| R3 | `audio.style` 接受文本标签如 `"gentle but tired"` 还是别的字段 | Phase 0 探针 |
| R4 | `audio.format = mp3 / opus` 是否被接受 | Phase 0 探针,3 种各试一次 |
| R5 | 流式音频前端怎么播(wav 不适合 MSE,可能要落地为 chunk 文件后轮播) | 视 R1 结果决定:① 每 chunk 落 wav + Audio 元素轮播(简单);② Web Audio API 解 PCM scheduler(复杂);③ 后端把 chunk 拼成 mp3 流,前端 MediaSource(中等) |

## D. 实施路线(分阶段)

### Phase 0 — 探针(✅ 已完成 2026-04-30)

详见 `docs/USAGE.md` 附录「API 实测备注」。要点:

| Risk | 实测结论 | 影响 Phase 1+ 范围 |
|---|---|---|
| R1 stream | SSE 工作,但只在 1 个 event 推完整 wav,**非真增量** | 流式简化为"伪流式"(SSE 推一次完整 wav + done),前端 `<audio>.play()` |
| R2 speed | 字段接受但效果反向,**当前不可用** | **UI 不暴露 speed**(SDK 透传保留以备修复) |
| R3 style | 字段接受但产物字节完全一致,**当前不可用** | **UI 不暴露 style** |
| R4 format | wav / mp3 / pcm / pcm16 ✅,opus ❌ | UI 暴露 wav/mp3 |

**收敛后 UI 高级项**:仅 voice + format(原 T-Q4 的 speed/style 因实测无效降级到"SDK 透传不在 UI 暴露")

### Phase 1 — 扩 SDK + 后端(0.5-1 天)

**`src/mimo_mcp/client.py`**:
- 新增 `tts_stream(text, voice, *, model, audio_format, **opts) -> AsyncIterator[bytes]`(若 R1 显示不支持流式,则保留 stub 抛 NotSupportedError,此时前端 fallback 一次性)

**`src/mimo_mcp/api/tts.py`**:
- 扩 `synthesize` 把 `req.speed` `req.style` 透传到 `client.tts(extra_audio={...})`
- 新增 `synthesize_stream(req, storage) -> AsyncIterator[bytes]`,沿用三模型路由
- 新增 `synthesize_batch(text, segment_max_chars=120, voice, ..., storage) -> AsyncIterator[BatchSegment]`
  - 切段算法:按 `[。!?;\n]` 切,二次合并保证每段 ≤ `segment_max_chars` 字符,避免拆碎太碎
  - yield 顺序合成结果,前端可"边来边渲染"

**`webui/backend/routers/tts.py`**(新文件):
- `POST /api/tts/synthesize`:body `{text, voice, format, speed, style}` → JSON `{audio_url, voice, source, model, bytes, transcript_id}`
- `POST /api/tts/stream`:同上 → SSE,事件类型:`{audio_chunk_b64, finished, error}`
- `POST /api/tts/batch`:body `{text, voice, segment_max_chars, ...}` → SSE,每段一个事件 `{index, text, audio_url, bytes}`
- `GET /api/tts/audio/<filename>`:把 `data/artifacts/tts/**/<filename>` 反代给前端的 `<audio src>`(已通过 path 校验,防越权读其他目录)

**`webui/backend/main.py`**:`include_router(tts.router, prefix="/api/tts")`

### Phase 2 — 前端 `/tts` 页面(1-1.5 天)

**`webui/frontend/src/pages/TTS.tsx`**(新文件,布局):
```
┌─────────────────────────────────────────────────┐
│ 文字转语音                                       │
│ [模式 Tab:单段 / 批量]   [流式开关:●(默认开)]│
├──────────────────────────┬──────────────────────┤
│ <textarea 主输入>         │  音色 [下拉]          │
│ rows=10, 字数统计 / 限制   │  · default(9)        │
│                           │  · clone(N)          │
│                           │  · design(N)         │
│                           │                      │
│                           │  格式 [wav/mp3/opus] │
│                           │  语速 [滑块 0.5-2.0] │
│                           │  风格标签 [text]      │
│                           │  (批量)分段字数 [120] │
│                           │                      │
│                           │  [合成] 按钮          │
├──────────────────────────┴──────────────────────┤
│ 结果区(单段/批量两种渲染):                      │
│ - 单段:<audio controls> + 文件信息 + 下载       │
│ - 批量:段落列表,每段 audio + 文本 + 状态       │
├─────────────────────────────────────────────────┤
│ 本次会话历史(最多 20 条,localStorage 兜底)    │
│ [▶] 14:03  茉莉  "今天天气真不错"  3.2s 1.4MB  │
└─────────────────────────────────────────────────┘
```

**`webui/frontend/src/lib/api.ts`** 新增:
- `api.ttsSynthesize(body)` 一次性
- `api.ttsStream(body, onChunk, onDone)` SSE
- `api.ttsBatch(body, onSegment, onDone)` SSE

**流式播放策略**(基于 R5 三选一,Phase 0 后定):
- 简单方案:后端每 chunk 落 wav 文件,SSE 推 `audio_url`,前端用 `<audio>` 队列轮播
- 复杂方案:后端推 base64 PCM 数据,前端 Web Audio API decode + schedule

**`webui/frontend/src/App.tsx`**:加 `<Route path="tts" element={<TTS />} />`

**`webui/frontend/src/components/Layout.tsx`**:NAV 数组在 `Sandbox` 后插入 `{ to: "/tts", icon: Volume2, label: "文字转语音" }`(`Volume2` 来自 lucide-react)

### Phase 3 — 测试 + 文档(0.5 天)

- `tests/test_live.py` 新增 2 个 case(`MIMO_RUN_LIVE=1` 才跑):
  1. `synthesize` 带 speed=1.5 + format=mp3,验证产物 magic 是 ID3 而非 RIFF
  2. `synthesize_batch` 跑 ~300 字,断言 yield 出 ≥2 段且每段 wav 都有效
- `docs/USAGE.md`:替换"五、Web 控制台 7 个页面用法"中"语音转写"前的占位,新增"文字转语音"小节;在"4.1 一句话配音 demo"补一行说明 Web 路径
- `pytest -q` 全套通过(离线 + 联网)

## E. 关键文件清单

**新建**(均为 plan 实施时落盘):
- `scripts/_probe_tts_advanced.py`(临时,Phase 3 末删)
- `webui/backend/routers/tts.py`
- `webui/frontend/src/pages/TTS.tsx`
- `tests/test_live_tts_advanced.py`(可与 `test_live.py` 合并)

**修改**:
- `src/mimo_mcp/client.py`(加 `tts_stream`)
- `src/mimo_mcp/api/tts.py`(加 `synthesize_stream` / `synthesize_batch`,扩 `synthesize` 透传 speed/style)
- `webui/backend/main.py`(注册 `/api/tts` router)
- `webui/frontend/src/App.tsx`(加路由)
- `webui/frontend/src/components/Layout.tsx`(加 NAV 项)
- `webui/frontend/src/lib/api.ts`(加 ttsSynthesize / ttsStream / ttsBatch)
- `docs/USAGE.md`(新章节)
- `docs/USAGE.md`(附录「API 实测备注」收录 Phase 0 R1-R4 实测结论)

## F. 验证(端到端 done)

| 验证项 | 期望 |
|---|---|
| 浏览器打开 `http://127.0.0.1:5173/tts` | 看到文本框 + 右侧侧栏 + 模式 Tab |
| 输入"你好世界" + 默认 voice + 流式开 + 合成 | 1-2 秒内开始播放,音质正常 |
| 切 format=mp3 + speed=1.5 + 茉莉 + 合成 | 产物 mp3,语速更快;`file <产物>` 看到 `MPEG ADTS` 或 `Audio file` |
| 风格标签填 "gentle but tired" + 合成 | 产物风格切换(若 R3 支持) |
| 切批量模式 + 贴 800 字 + 分段 120 | 看到 7-8 段卡片,每段独立播放,顺序就绪 |
| 历史列表 | 本次会话内的合成都在,刷新仍在(localStorage),换会话清空 |
| `/api/usage/audit?limit=20` | 看到 `channel=web tool=mimo.tts` 记录 |
| `pytest -q` + `MIMO_RUN_LIVE=1 pytest -q tests/test_live.py` | 全绿 |

## G. 不做(明确边界)

- 不做长文 SSML 解析
- 不做用户上传 .txt / .md 文件批量(只支持粘贴文本)
- 不做后端持久化历史(audit_log 已记录元数据,实际产物在 data/artifacts/tts/,前端历史用 localStorage)
- 不做 emotion tag(`<inhale>` `<laugh>` `<sob>`)—— 推迟到下一个增量任务
- 不做并发批量(顺序合成对套餐限流更友好,且简化前端 UI)

## H. 时长估算

| 阶段 | 时长 |
|---|---|
| Phase 0 探针 | 0.5 天 |
| Phase 1 SDK + 后端 | 0.5-1 天 |
| Phase 2 前端 | 1-1.5 天 |
| Phase 3 测试 + 文档 | 0.5 天 |
| **合计** | **2.5-3.5 个工作日** |
- 错误码官方页(待平台注册后核对):`https://platform.xiaomimimo.com/docs/quick-start/error-codes`

# mimo-mcp

把小米 MiMo 全模态能力(Chat / 图像 / 视频 / TTS / 声音克隆 / 声音设计 / ASR)封装为一个 stdio MCP Server,供 **Claude Code** 与 **Codex** 同时调用,并附带本地 Web 管理面板。

> 文档位置:[`/.claude/plans/mimo-mimo-mcp-smooth-rainbow.md`](../.claude/plans/mimo-mimo-mcp-smooth-rainbow.md)(PRD v1.0)
> 当前阶段:**M0 仓库脚手架已完成**。M1 将用真 API key 实测各端点并填充 `client.py` 与 `api/*.py` 中的 `NotImplementedError`。

---

## 1. 三步上手

### 1.1 安装依赖

```bash
# 后端(Python 3.11+ + uv)
uv sync

# 前端(Node 22+ + pnpm)
cd webui/frontend && pnpm install && cd ../..
```

### 1.2 配置 API Key

```bash
cp .env.example .env
# 用编辑器打开 .env,把 MIMO_API_KEY 改成你在 platform.xiaomimimo.com 拿到的真实 key
```

### 1.3 启动

| 用途 | 命令 |
|---|---|
| stdio MCP server(给 Claude Code / Codex 用) | `./scripts/run_mcp.sh` |
| 本地 Web 控制台后端(:7801) | `./scripts/run_web.sh` |
| 前端开发模式(:5173,代理到 7801) | `cd webui/frontend && pnpm dev` |
| 前端构建到 dist(后端会托管) | `./scripts/build_frontend.sh` |

打开 <http://localhost:7801>(已构建)或 <http://localhost:5173>(开发模式)即可看到控制台。

---

## 2. 项目结构(对应 PRD §6.1)

```
src/mimo_mcp/        # 共享 SDK 适配层 + FastMCP server
├── api/             # F1-F8 业务编排
├── client.py        # httpx async,包装 OpenAI 兼容接口
├── config.py        # pydantic-settings,前缀 MIMO_
├── models.py        # 请求/响应/voice 数据模型
├── server.py        # FastMCP 入口,注册 11 个 tool
└── storage.py       # SQLite + 文件存储

webui/
├── backend/         # FastAPI(独立进程,共享 SDK 适配层)
│   └── routers/     # voices / chat / vision / asr / usage
└── frontend/        # Vite + React + TS + Tailwind v4 + shadcn 风格

scripts/             # 启动 / 构建脚本
tests/               # pytest(M0 冒烟覆盖)
data/                # 运行期数据(已 .gitignore)
```

---

## 3. 注册到 Claude Code / Codex

### 3.1 Claude Code(`~/.claude/settings.local.json`)

把下面这段合并到 `mcpServers` 字段:

```json
{
  "mcpServers": {
    "mimo-mcp": {
      "command": "/Users/liuaiyi/Desktop/xiaomi-MIMO/scripts/run_mcp.sh"
    }
  }
}
```

> 也可以直接用 `uv run --directory /Users/liuaiyi/Desktop/xiaomi-MIMO mimo-mcp` 当 command,
> 然后在 `env` 里传 `MIMO_API_KEY`。脚本方式更省心,因为它自动加载 `.env`。

### 3.2 Codex(`~/.codex/config.toml`)

```toml
[mcp_servers.mimo-mcp]
command = "/Users/liuaiyi/Desktop/xiaomi-MIMO/scripts/run_mcp.sh"
```

### 3.3 验证

注册后重启 Claude Code / Codex,问一句 "调用 mimo.health",应该能拿到结构化的健康检查结果。

---

## 4. 11 个 MCP Tool

| Tool | 说明 |
|---|---|
| `mimo.chat` | 多模态对话(messages 兼容 OpenAI) |
| `mimo.image_understand` | 图像理解(url / path / base64) |
| `mimo.video_understand` | 视频理解(URL 模式) |
| `mimo.tts` | 文本合成语音,返回 wav 路径 |
| `mimo.voice_clone_create` | 上传参考音频创建克隆音色 |
| `mimo.voice_design_create` | 文字描述生成自定义音色 |
| `mimo.voice_list` | 列出本地音色库 |
| `mimo.voice_delete` | 删除本地音色 |
| `mimo.asr` | 语音转写(F7 仅云端,云端缺失时返回 unavailable) |
| `mimo.health` | 健康检查(配置 / 网络 / 鉴权 / ASR 可用性) |
| `mimo.usage` | 本地 audit_log 聚合的最近用量 |

> **大文件约定**:tool 入参传"本地路径"或"http(s) URL",**不要传 base64 大对象**(stdio 协议 + 大对象会很慢)。Web UI 上传走 FastAPI 不走 MCP。

---

## 5. 路线图

- **M0 仓库脚手架** ✅(本次提交)
- **M1 SDK 适配层** — 拿真 API key 实测所有端点,确认 §14 中 3 个未公开细节,填充 `client.py` 与 `api/*.py` 的 `NotImplementedError`
- **M2 MCP 工具层** — Claude Code / Codex 双注册冒烟通过
- **M3 Web 后端** — 与 SDK 联通(已具备框架)
- **M4 Web 前端** — 7 个页面已成型,补完真实联调
- **M5 联调 + 文档** — 端到端真实流(克隆 → 入库 → MCP 出音)

---

## 6. 关键决策(PRD §15)

| # | 议题 | 选定 |
|---|---|---|
| Q1 | 实现语言 | Python 3.11 + FastMCP(`mcp[cli]`) |
| Q2 | Transport | 仅 stdio |
| Q3 | Web 前端栈 | Vite + React + TS + Tailwind v4 + shadcn 风格 |
| Q4 | MVP 范围 | F1-F8 全量 |
| Q5 | skill 联动 | V1 不做,V2 模板形式 |
| Q6 | ASR 兜底 | 仅 MiMo 云端,云端缺失则 F7 显式 unavailable |

---

## 7. 测试

```bash
uv run pytest -q
```

M0 冒烟覆盖:模块可 import / Storage CRUD / health_check 不抛 / 11 个 tool 完整注册。

---

## 8. 安全

- API Key 仅出现在 `.env`(已 .gitignore),日志不打印
- Web UI 默认 `127.0.0.1`,不暴露公网
- 上传素材保存在本地 `data/artifacts/`,前端禁止外链

---

## 9. Token Plan 套餐使用提示(M1 实测确认)

如果你买的是「Token Plan 套餐」(API Key 以 `tp-` 开头):

1. **必须用专属 base URL**,否则报 `Invalid API Key`。在 platform.xiaomimimo.com 控制台「我的套餐」页面复制「专属 Base URL → 兼容 OpenAI 接口协议」,典型形式 `https://token-plan-cn.xiaomimimo.com/v1`,填到 `.env` 的 `MIMO_BASE_URL`。
2. **套餐含**:V2.5-Pro / V2.5 / V2.5-TTS / V2.5-TTS-VoiceClone / V2.5-TTS-VoiceDesign / V2-Pro / V2-Omni / V2-TTS。**不含**:V2-Flash 与 V2.5-ASR(F7 因此显式 `unavailable`,符合 PRD §15-Q6 决策)。
3. **v2.5 是 thinking 模型**:返回的 `message.reasoning_content` 是思考链,真正回复在 `message.content`。如果 `max_tokens` 太小(< 1024)会只见思考、不见回复。本仓库已把默认 `MIMO_DEFAULT_MAX_TOKENS=4096`,长文任务可临时调到 8192+。
4. **使用范围**:套餐合规用法是「在编程工具中使用」(Claude Code / Codex / OpenCode 等);本仓库的 mimo-mcp 正属于这类。Web 沙盒在本机做轻量调试也无问题,不要做高频自动化压测。

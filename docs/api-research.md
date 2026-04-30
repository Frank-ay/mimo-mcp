# MiMo API 调研笔记

按时间倒序记录每次实测的发现,作为 PRD §14 风险表的事实依据。

---

## 2026-04-30 增量任务 2 — 视频理解输入归一化

### 实测确认

| 输入形式 | MiMo 接受程度 |
|---|---|
| `data:video/mp4;base64,...` DataURL | ✅ 稳定可用,recommended |
| 直链 mp4 URL(http(s)) | ⚠️ MiMo 后端去拉外网时会随机 400 `failed to download url data`(早上能用现在可能不能,不可靠) |
| B 站 / YouTube / 抖音 / 小红书等"页面型" URL | ❌ MiMo 直接拿不到 mp4(返回 HTML) |
| 本地路径 | n/a(需客户端转 DataURL) |

### 实施决策

统一所有"非 DataURL 输入"在客户端落地为本地 mp4 → base64 → DataURL,完全绕开
MiMo 服务器去拉外链。直链用 `httpx.stream` 本地下载,B 站等用 `yt-dlp` 下载。

- 文件大小上限 50 MB(base64 后 ~67 MB,够 30 秒-2 分钟视频)
- yt-dlp 优先选 `best[ext=mp4][filesize<40M]`,避免 4K 几百 MB

---

## 2026-04-30 增量任务 1 / Phase 0 — TTS 高级特性探针

### R1 stream=true 的 SSE 协议

- **支持** `stream: true`,`Content-Type: text/event-stream`
- 单段短文(如"你好世界。今天天气真好。")完整事件流:
  ```
  data: { ...delta: { reasoning_content, content: "" } }   ← 思考占位
  data: { ...delta: { audio: { id, data:<完整 base64 wav>, expires_at, transcript } } }   ← 唯一含 data 的 chunk
  data: { ...delta: { reasoning_content } }                ← 收尾
  data: [DONE]
  ```
- **重要**:wav 在**单一** chunk 内一次性返回,**不是 chunk-by-chunk 增量音频**
- 因此前端不需要 MediaSource API。"边生成边播"在当前实现下不可行,只能"等完整 wav,立刻自动播"

### R2 audio.speed 字段(实测无效)

| speed 取值 | duration | bytes |
|---|---|---|
| 0.5 | 5.440 s | 261164 |
| 1.0 | 5.600 s | 268844 |
| 2.0 | 6.080 s | 291884 |

- 字段被 API 接受(不报 400)
- 但**效果与文档预期相反**:speed 越大反而 duration 越长
- 结论:**当前不可用**,UI 不暴露;SDK 保留透传(以备将来修复)

### R3 audio.style 字段(实测无效)

| style 取值 | bytes |
|---|---|
| `"gentle but tired"` | 69164 |
| `"happy"` | 69164 |
| `"sad and slow"` | 69164 |

- 字段被 API 接受,但产物字节完全一致 → 风格未变化
- 结论:**当前不可用**,UI 不暴露

### R4 audio.format 字段(部分支持)

| format | 状态 | 备注 |
|---|---|---|
| `wav` | ✅ | RIFF 头,默认推荐 |
| `mp3` | ✅ | MPEG ADTS,体积约为 wav 的 1/5 |
| `pcm` | ✅(平台 400 提示) | 原始 PCM,适合后端二次处理 |
| `pcm16` | ✅(平台 400 提示) | 16-bit PCM |
| `opus` | ❌ | 报错 `Unsupported audio format: opus. Supported formats: wav, mp3, pcm, pcm16` |

- UI 决定:暴露 **wav / mp3** 两项;pcm/pcm16 留 SDK 给高级用户

### 衍生决策(影响增量任务 1 实施范围)

1. **流式简化**:V1 取消"真流式"野心,改做"伪流式"——后端 `/api/tts/synthesize` 走 SSE 推送一次 `audio_chunk` 事件 + 一次 `done`,前端收到立刻播。后端实现极简,前端一行 `audio.play()`
2. **批量保留 SSE**:`/api/tts/batch` 仍然 SSE 推每段(每段是一个完整 wav),前端按事件追加列表
3. **UI 高级控制项收敛**:从 plan T-Q4 的"voice + format + speed + style"改为"voice + format"(speed/style 不可用,移到 SDK 透传,UI 不暴露)
4. **预置 voice 列表**:已知 `mimo_default 冰糖 茉莉 苏打 白桦 Mia Chloe Milo Dean`(2026-04-29 实测)

---

## 2026-04-29 M1 阶段实测发现

(已合并到 PRD §14 风险表 + README §9)

- TTS 端点:`/chat/completions`,messages 必须含 `role=assistant` 消息(承载朗读文本)
- VoiceClone:`audio.voice` 必须是 `data:audio/wav;base64,...` DataURL,**stateless**(每次合成都要传 reference)
- VoiceDesign:`messages = [{user: prompt}, {assistant: sample_text}]`,**stateless**(无独立 voice_id)
- VideoUnderstand:走 v2.5 + `{type: "video_url", video_url: {url}}`,video_tokens + audio_tokens 单独计费
- v2.5 全系是 thinking 模型,默认 `max_tokens=4096` 兜底
- Token Plan 套餐 key 前缀 `tp-`,必须用专属 base URL(如 `https://token-plan-cn.xiaomimimo.com/v1`)
- 套餐**不含** `mimo-v2-flash` 与 `mimo-v2.5-asr`

## 参考

- 官方:<https://platform.xiaomimimo.com/docs/api/chat/openai-api>
- 模型矩阵:<https://mimo.xiaomi.com/>
- LiteLLM provider:<https://docs.litellm.ai/docs/providers/xiaomi_mimo>

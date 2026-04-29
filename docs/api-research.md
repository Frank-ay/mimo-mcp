# MiMo API 调研笔记(M1 阶段实测前的"已知 / 待验证"清单)

> 来源:Phase 1 调研报告。M1 阶段拿到真 key 后,逐项做"hello world"请求,以实际响应为准更新本文。

## 已确认

- **Base URL**:`https://api.xiaomimimo.com/v1`
- **鉴权**:`Authorization: Bearer $MIMO_API_KEY`(也支持 `api-key:` 头)
- **Chat**:`POST /chat/completions`,完全 OpenAI 兼容
- **图像**:`messages[].content` 数组里 `{"type":"image_url","image_url":{"url": <url|data:base64>}}`
- **视频**:MiMo-V2.5 / V2-Omni 原生支持,不必客户端分帧
- **OCR**:vision 模型支持
- **Tool calling + 图像**:可并存
- **多语种 / 方言 ASR**:开源模型支持,云端 API 形态待确认

## 待 M1 实测

| 主题 | 待确认 |
|---|---|
| TTS | endpoint(`/audio/speech` 还是 `/chat/completions` + `audio`)、返回是 base64 还是二进制流、`voice` 字段名、`speed` 参数形式 |
| 声音克隆 | 上传 endpoint、参考音频时长/格式要求、voice_id 字段名、是否有审核流程 |
| 声音设计 | prompt 字段名、是否同步返回 voice_id |
| 视频上传 | 是否需要先 upload 再引用,还是直接 `video_url` |
| ASR | `/audio/transcriptions` 是否存在;若不存在,F7 显式 unavailable(决策见 PRD §15-Q6) |
| 限流 | RPM / TPM / 并发数,从响应 header 读 |
| 错误码 | 401/402/429 之外的业务码 |

## 实测 checklist(M1 阶段填)

- [ ] `/v1/models` 拉模型列表,确认 v2.5 系列模型 ID
- [ ] `mimo-v2.5-pro` chat hello world
- [ ] `mimo-v2.5` 图像理解(URL + base64 各一发)
- [ ] `mimo-v2.5-tts` TTS 一句中文 + 一句英文,看返回结构
- [ ] `mimo-v2.5-tts-voicedesign` 设计音色
- [ ] `mimo-v2.5-tts-voiceclone` 克隆音色 + 用 voice_id 出音
- [ ] `mimo-v2.5-asr` 是否可调用(决定 F7 状态)
- [ ] 视频:URL 模式跑通
- [ ] 余额 / 用量 endpoint:是否存在 `/dashboard/...`

## 参考

- 官方:<https://platform.xiaomimimo.com/docs/api/chat/openai-api>
- 模型矩阵:<https://mimo.xiaomi.com/>
- LiteLLM provider:<https://docs.litellm.ai/docs/providers/xiaomi_mimo>
- Python wrapper:<https://github.com/Water008/MiMo2API>
- 错误码官方页:<https://platform.xiaomimimo.com/docs/quick-start/error-codes>

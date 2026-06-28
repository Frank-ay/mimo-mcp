/**
 * 与 FastAPI 后端通信的薄包装。开发期 Vite proxy 转发到 7801,
 * 生产期 FastAPI 同源托管 dist。
 */
import { consumeSSE } from "./sse";

const BASE = "/api";

async function request<T>(path: string, init?: RequestInit): Promise<T> {
  const resp = await fetch(`${BASE}${path}`, init);
  if (!resp.ok) {
    let msg = `${resp.status} ${resp.statusText}`;
    try {
      const body = await resp.json();
      msg = body.detail || body.message || msg;
    } catch {
      /* ignore */
    }
    throw new Error(msg);
  }
  return (await resp.json()) as T;
}

// ---- 类型 ----
export type VoiceSource = "default" | "clone" | "design";
export type VoiceStatus = "pending" | "ready" | "failed";

export interface VoiceRecord {
  voice_id: string;
  name: string;
  source: VoiceSource;
  status: VoiceStatus;
  description: string | null;
  voice_prompt: string | null;
  reference_path: string | null;
  created_at: string;
  updated_at: string;
}

export interface HealthResult {
  api_key_configured: boolean;
  base_url: string;
  base_url_reachable: boolean | null;
  auth_valid: boolean | null;
  asr_cloud_available: boolean | null;
  notes: string[];
}

export interface UsageSummary {
  since_hours: number;
  calls: number;
  errors: number;
  input_tokens: number;
  output_tokens: number;
  by_tool: Record<string, number>;
}

export interface AuditEntry {
  id: number;
  ts: string;
  channel: "mcp" | "web";
  tool: string;
  model: string | null;
  input_tokens: number | null;
  output_tokens: number | null;
  latency_ms: number | null;
  status: "ok" | "error";
  error: string | null;
}

// ---- TTS 类型 ----
export type AudioFormat = "wav" | "mp3";

export interface TTSBody {
  text: string;
  voice?: string;
  voice_id?: string;
  audio_format?: AudioFormat;
  /**
   * v2.5 自然语言风格指令(导演模式):控制语气 / 情绪 / 语速 / 方言等。
   * v2.5 唯一推荐的风格控制入口(旧的 speed 已废弃不下发;style 仅作为 instructions 的简易回退)。
   */
  instructions?: string;
}

export interface TTSResult {
  audio_path: string;
  audio_url: string;
  voice: string;
  source: "default" | "clone" | "design";
  model: string;
  bytes: number;
  audio_format: AudioFormat;
  transcript_id: string;
}

export interface BatchSegmentEvent {
  index: number;
  total: number;
  text: string;
  audio_url: string;
  voice: string;
  source: "default" | "clone" | "design";
  model: string;
  bytes: number;
}

export interface BatchPlanEvent {
  total: number;
  segments: string[];
}

export interface BatchHandlers {
  onPlan?: (e: BatchPlanEvent) => void;
  onSegment?: (e: BatchSegmentEvent) => void;
  onError?: (msg: string) => void;
  onDone?: () => void;
}

// ---- 长视频分段分析事件 ----
export interface ChunkedPlanEvent {
  kind: "plan";
  total: number;
  duration: number;
  segment_seconds: number;
  segments: { index: number; start: number; end: number; bytes: number }[];
}

export interface ChunkedSegmentEvent {
  kind: "segment";
  index: number;
  start: number;
  end: number;
  description: string;
  bytes: number;
}

export interface ChunkedSummaryEvent {
  kind: "summary";
  text: string;
  total: number;
  duration: number;
  segments: ChunkedSegmentEvent[];
}

export interface ChunkedHandlers {
  onPlan?: (e: ChunkedPlanEvent) => void;
  onSegment?: (e: ChunkedSegmentEvent) => void;
  onSummary?: (e: ChunkedSummaryEvent) => void;
  onError?: (msg: string) => void;
  onDone?: () => void;
}

// ---- ASR 类型 ----
export interface ASRResult {
  text: string;
  model: string;
  language: string | null;
}

// ---- ASR 长音频分段(SSE)----
export interface ASRChunkPlanEvent {
  kind: "plan";
  total: number;
  duration: number;
  segment_seconds: number;
  segments: { index: number; start: number; end: number; bytes: number }[];
}

export interface ASRChunkSegmentEvent {
  kind: "segment";
  index: number;
  start: number;
  end: number;
  text: string;
}

export interface ASRChunkSummaryEvent {
  kind: "summary";
  text: string;
  total: number;
  duration: number;
}

export interface ASRChunkHandlers {
  onPlan?: (e: ASRChunkPlanEvent) => void;
  onSegment?: (e: ASRChunkSegmentEvent) => void;
  onSummary?: (e: ASRChunkSummaryEvent) => void;
  onError?: (msg: string) => void;
  onDone?: () => void;
}

// ---- ASR 说话人分离(SSE)----
export interface DiarizeSegment {
  index: number;
  speaker: number;
  start: number;
  end: number;
  text: string;
}

export interface DiarizePlanEvent {
  kind: "plan";
  total: number;
  duration: number;
  num_speakers: number;
  segments: { index: number; speaker: number; start: number; end: number }[];
}

export interface DiarizeSegmentEvent extends DiarizeSegment {
  kind: "segment";
}

export interface DiarizeSummaryEvent {
  kind: "summary";
  duration: number;
  num_speakers: number;
  segments: DiarizeSegment[];
}

export interface DiarizeHandlers {
  onStatus?: (msg: string) => void;
  onPlan?: (e: DiarizePlanEvent) => void;
  onSegment?: (e: DiarizeSegmentEvent) => void;
  onSummary?: (e: DiarizeSummaryEvent) => void;
  onError?: (msg: string) => void;
  onDone?: () => void;
}

// ---- Chat 类型 ----
export interface ChatMessageInput {
  role: "system" | "user" | "assistant";
  content: string;
}

export interface ChatBody {
  messages: ChatMessageInput[];
  model?: string;
  max_tokens?: number;
  temperature?: number;
  top_p?: number;
}

export interface ChatUsage {
  prompt_tokens?: number;
  completion_tokens?: number;
  total_tokens?: number;
  completion_tokens_details?: { reasoning_tokens?: number };
}

export interface ChatResponseMessage {
  role?: string;
  content?: string | null;
  /** v2.5 thinking 模型的思维链(reasoning_content),正文在 content */
  reasoning_content?: string | null;
}

export interface ChatChoice {
  index?: number;
  finish_reason?: string | null;
  message?: ChatResponseMessage;
}

export interface ChatResponse {
  model?: string;
  choices?: ChatChoice[];
  usage?: ChatUsage;
}

// ---- 端点 ----
export const api = {
  health: () => request<HealthResult>("/usage/health"),
  usage: (sinceHours = 24) =>
    request<UsageSummary>(`/usage/summary?since_hours=${sinceHours}`),
  audit: (limit = 100) => request<AuditEntry[]>(`/usage/audit?limit=${limit}`),
  voices: (source?: VoiceSource) =>
    request<VoiceRecord[]>(`/voices${source ? `?source=${source}` : ""}`),
  deleteVoice: (id: string) =>
    request<{ deleted: boolean }>(`/voices/${id}`, { method: "DELETE" }),
  createClone: (input: { file: File; name: string; description?: string }) => {
    const form = new FormData();
    form.append("file", input.file);
    form.append("name", input.name);
    if (input.description) form.append("description", input.description);
    return request<VoiceRecord>("/voices/clone", {
      method: "POST",
      body: form,
    });
  },
  createDesign: (input: {
    voice_prompt: string;
    name: string;
    sample_text?: string;
    optimize_text_preview?: boolean;
  }) => {
    const form = new FormData();
    form.append("voice_prompt", input.voice_prompt);
    form.append("name", input.name);
    if (input.sample_text) form.append("sample_text", input.sample_text);
    if (input.optimize_text_preview)
      form.append("optimize_text_preview", "true");
    return request<VoiceRecord>("/voices/design", {
      method: "POST",
      body: form,
    });
  },
  chat: (body: ChatBody) =>
    request<ChatResponse>("/chat", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(body),
    }),
  imageUnderstand: (form: FormData) =>
    request<unknown>("/vision/image", { method: "POST", body: form }),
  videoUnderstand: (form: FormData) =>
    request<unknown>("/vision/video", { method: "POST", body: form }),
  videoUnderstandUrl: (body: {
    video_url: string;
    prompt: string;
    model?: string;
  }) =>
    request<unknown>("/vision/video/url", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(body),
    }),

  // 视频元信息探针:用 yt-dlp metadata-only 拿时长/标题等,不下载本体
  videoProbe: (body: { video_url: string }) =>
    request<{
      kind: "data_url" | "page" | "direct";
      duration: number | null;
      title?: string | null;
      uploader?: string | null;
      thumbnail?: string | null;
      extractor?: string | null;
      size?: number | null;
      content_type?: string | null;
    }>("/vision/video/probe", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(body),
    }),

  // 长视频分段分析:SSE 流式返回,绕开 50 MB 上限
  videoChunked: async (
    form: FormData,
    handlers: ChunkedHandlers,
    signal?: AbortSignal,
  ): Promise<void> => {
    const resp = await fetch(`${BASE}/vision/video/chunked`, {
      method: "POST",
      body: form,
      signal,
    });
    if (!resp.ok || !resp.body) {
      handlers.onError?.(await resp.text().catch(() => resp.statusText));
      return;
    }
    await consumeSSE(resp, (event, obj) => {
      const data = obj as Record<string, unknown>;
      if (event === "plan")
        handlers.onPlan?.(data as unknown as ChunkedPlanEvent);
      else if (event === "segment")
        handlers.onSegment?.(data as unknown as ChunkedSegmentEvent);
      else if (event === "summary")
        handlers.onSummary?.(data as unknown as ChunkedSummaryEvent);
      else if (event === "error")
        handlers.onError?.((data.message as string | undefined) ?? "未知错误");
      else if (event === "done") handlers.onDone?.();
    });
  },

  asr: (input: { file: File; language?: string }) => {
    const form = new FormData();
    form.append("file", input.file);
    form.append("language", input.language ?? "auto");
    return request<ASRResult>("/asr", { method: "POST", body: form });
  },

  // ASR 说话人分离转写(sherpa-onnx diarization + MiMo 逐段转写),SSE 流式
  asrDiarize: async (
    form: FormData,
    handlers: DiarizeHandlers,
    signal?: AbortSignal,
  ): Promise<void> => {
    const resp = await fetch(`${BASE}/asr/diarize`, {
      method: "POST",
      body: form,
      signal,
    });
    if (!resp.ok || !resp.body) {
      handlers.onError?.(await resp.text().catch(() => resp.statusText));
      return;
    }
    await consumeSSE(resp, (event, obj) => {
      const data = obj as Record<string, unknown>;
      if (event === "status")
        handlers.onStatus?.((data.message as string | undefined) ?? "");
      else if (event === "plan")
        handlers.onPlan?.(data as unknown as DiarizePlanEvent);
      else if (event === "segment")
        handlers.onSegment?.(data as unknown as DiarizeSegmentEvent);
      else if (event === "summary")
        handlers.onSummary?.(data as unknown as DiarizeSummaryEvent);
      else if (event === "error")
        handlers.onError?.((data.message as string | undefined) ?? "未知错误");
      else if (event === "done") handlers.onDone?.();
    });
  },

  // ASR 长音频分段转写,SSE 流式(切段 → 逐段转写 → 合并)
  asrChunked: async (
    form: FormData,
    handlers: ASRChunkHandlers,
    signal?: AbortSignal,
  ): Promise<void> => {
    const resp = await fetch(`${BASE}/asr/chunked`, {
      method: "POST",
      body: form,
      signal,
    });
    if (!resp.ok || !resp.body) {
      handlers.onError?.(await resp.text().catch(() => resp.statusText));
      return;
    }
    await consumeSSE(resp, (event, obj) => {
      const data = obj as Record<string, unknown>;
      if (event === "plan")
        handlers.onPlan?.(data as unknown as ASRChunkPlanEvent);
      else if (event === "segment")
        handlers.onSegment?.(data as unknown as ASRChunkSegmentEvent);
      else if (event === "summary")
        handlers.onSummary?.(data as unknown as ASRChunkSummaryEvent);
      else if (event === "error")
        handlers.onError?.((data.message as string | undefined) ?? "未知错误");
      else if (event === "done") handlers.onDone?.();
    });
  },

  // 用 v2.5-pro 改写朗读文本(口语化、补标点、数字念法等)
  ttsRefine: (body: { text: string; style?: string }) =>
    request<{
      original: string;
      refined: string;
      char_count_before: number;
      char_count_after: number;
      latency_ms: number;
      tokens: { input: number; output: number; reasoning: number };
    }>("/tts/refine", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(body),
    }),

  // TTS 单段一次性
  ttsSynthesize: (body: TTSBody) =>
    request<TTSResult>("/tts/synthesize", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(body),
    }),

  // TTS 批量,SSE 流
  ttsBatch: async (
    body: TTSBody & { segment_max_chars?: number },
    handlers: BatchHandlers,
    signal?: AbortSignal,
  ): Promise<void> => {
    const resp = await fetch(`${BASE}/tts/batch`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(body),
      signal,
    });
    if (!resp.ok || !resp.body) {
      const text = await resp.text().catch(() => resp.statusText);
      handlers.onError?.(text);
      return;
    }
    await consumeSSE(resp, (event, obj) => {
      const data = obj as Record<string, unknown>;
      if (event === "plan")
        handlers.onPlan?.(data as unknown as BatchPlanEvent);
      else if (event === "segment")
        handlers.onSegment?.(data as unknown as BatchSegmentEvent);
      else if (event === "error")
        handlers.onError?.((data.message as string | undefined) ?? "未知错误");
      else if (event === "done") handlers.onDone?.();
    });
  },
};

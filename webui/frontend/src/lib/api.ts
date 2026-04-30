/**
 * 与 FastAPI 后端通信的薄包装。开发期 Vite proxy 转发到 7801,
 * 生产期 FastAPI 同源托管 dist。
 */

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
  speed?: number;
  style?: string;
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
  createClone: (form: FormData) =>
    request<VoiceRecord>("/voices/clone", { method: "POST", body: form }),
  createDesign: (form: FormData) =>
    request<VoiceRecord>("/voices/design", { method: "POST", body: form }),
  chat: (body: unknown) =>
    request<unknown>("/chat", {
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
    const reader = resp.body.getReader();
    const decoder = new TextDecoder();
    let buf = "";
    while (true) {
      const { value, done } = await reader.read();
      if (done) break;
      buf += decoder.decode(value, { stream: true });
      let sep = buf.indexOf("\n\n");
      while (sep !== -1) {
        const raw = buf.slice(0, sep);
        buf = buf.slice(sep + 2);
        sep = buf.indexOf("\n\n");
        let event = "message";
        let data = "";
        for (const line of raw.split("\n")) {
          if (line.startsWith("event:")) event = line.slice(6).trim();
          else if (line.startsWith("data:")) data += line.slice(5).trim();
        }
        if (!data) continue;
        try {
          const obj = JSON.parse(data);
          if (event === "plan") handlers.onPlan?.(obj as ChunkedPlanEvent);
          else if (event === "segment")
            handlers.onSegment?.(obj as ChunkedSegmentEvent);
          else if (event === "summary")
            handlers.onSummary?.(obj as ChunkedSummaryEvent);
          else if (event === "error")
            handlers.onError?.(obj.message ?? "未知错误");
          else if (event === "done") handlers.onDone?.();
        } catch {
          // ignore parse error, keep reading
        }
      }
    }
  },

  asr: (form: FormData) =>
    request<unknown>("/asr", { method: "POST", body: form }),

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
    const reader = resp.body.getReader();
    const decoder = new TextDecoder();
    let buffer = "";
    while (true) {
      const { value, done } = await reader.read();
      if (done) break;
      buffer += decoder.decode(value, { stream: true });
      // SSE 事件由 \n\n 分隔
      let sep = buffer.indexOf("\n\n");
      while (sep !== -1) {
        const raw = buffer.slice(0, sep);
        buffer = buffer.slice(sep + 2);
        sep = buffer.indexOf("\n\n");
        const lines = raw.split("\n");
        let event = "message";
        let data = "";
        for (const line of lines) {
          if (line.startsWith("event:")) event = line.slice(6).trim();
          else if (line.startsWith("data:")) data += line.slice(5).trim();
        }
        if (!data) continue;
        try {
          const obj = JSON.parse(data);
          if (event === "plan") handlers.onPlan?.(obj as BatchPlanEvent);
          else if (event === "segment")
            handlers.onSegment?.(obj as BatchSegmentEvent);
          else if (event === "error")
            handlers.onError?.(obj.message ?? "未知错误");
          else if (event === "done") handlers.onDone?.();
        } catch {
          // 忽略解析错误,继续读
        }
      }
    }
  },
};

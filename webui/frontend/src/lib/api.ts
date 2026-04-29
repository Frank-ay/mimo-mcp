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

// ---- 端点 ----
export const api = {
  health: () => request<HealthResult>("/usage/health"),
  usage: (sinceHours = 24) => request<UsageSummary>(`/usage/summary?since_hours=${sinceHours}`),
  audit: (limit = 100) => request<AuditEntry[]>(`/usage/audit?limit=${limit}`),
  voices: (source?: VoiceSource) =>
    request<VoiceRecord[]>(`/voices${source ? `?source=${source}` : ""}`),
  deleteVoice: (id: string) => request<{ deleted: boolean }>(`/voices/${id}`, { method: "DELETE" }),
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
  asr: (form: FormData) => request<unknown>("/asr", { method: "POST", body: form }),
};

/** TTS 页的全局任务 store:输入控件值 + 流式批量任务(SSE)都在模块单例里,切换路由不中断。 */
import {
  api,
  type AudioFormat,
  type BatchSegmentEvent,
  type TTSResult,
  type VoiceRecord,
} from "@/lib/api";
import { createHistory } from "@/lib/history";
import { createStore } from "@/lib/taskStore";

export type Mode = "single" | "batch";

export interface HistoryItem {
  id: string;
  ts: string;
  mode: Mode;
  text: string;
  voice: string;
  source: VoiceRecord["source"];
  audio_format: AudioFormat;
  segments: { audio_url: string; bytes: number; text: string }[];
  total_bytes: number;
}

export interface BatchState {
  total: number;
  items: BatchSegmentEvent[];
}

export interface TtsState {
  // ---- 输入控件 ----
  mode: Mode;
  text: string;
  voice: string;
  format: AudioFormat;
  segMax: number;
  refineStyle: string;
  // 导演模式:v2.5 自然语言风格指令(instructions)
  instructions: string;
  // ---- 流式 / 异步任务状态 ----
  single: TTSResult | null;
  batch: BatchState | null;
  loading: boolean;
  refining: boolean;
  textBeforeRefine: string | null;
  refineNotice: string;
  error: string;
  // 单段合成完成的自增标记,组件据此触发自动播放
  playToken: number;
  // ---- 历史 ----
  history: HistoryItem[];
}

export const HISTORY_MAX = 20;
const ttsHistory = createHistory<HistoryItem>("mimo:tts:history", HISTORY_MAX);

export const SOURCE_LABEL: Record<VoiceRecord["source"], string> = {
  default: "预置",
  clone: "克隆",
  design: "设计",
};

const initial: TtsState = {
  mode: "single",
  text: "你好,这里是 mimo-mcp 的网页文字转语音控制台,选一个音色,点合成试试看。",
  voice: "mimo_default",
  format: "wav",
  segMax: 120,
  refineStyle: "",
  instructions: "",
  single: null,
  batch: null,
  loading: false,
  refining: false,
  textBeforeRefine: null,
  refineNotice: "",
  error: "",
  playToken: 0,
  history: ttsHistory.load(),
};

export const ttsStore = createStore<TtsState>(initial);

let abortCtl: AbortController | null = null;
// 任务代号:旧任务被取代后,其迟到回调/catch/finally 用守卫丢弃,避免覆盖新任务状态。
let taskSeq = 0;

// ---- setter ----
export function setMode(mode: Mode) {
  ttsStore.set({ mode });
}
export function setText(text: string) {
  ttsStore.set({ text });
}
export function setVoice(voice: string) {
  ttsStore.set({ voice });
}
export function setFormat(format: AudioFormat) {
  ttsStore.set({ format });
}
export function setSegMax(segMax: number) {
  ttsStore.set({ segMax });
}
export function setRefineStyle(refineStyle: string) {
  ttsStore.set({ refineStyle });
}
export function setInstructions(instructions: string) {
  ttsStore.set({ instructions });
}

function pushHistory(item: HistoryItem) {
  const next = [item, ...ttsStore.get().history].slice(0, HISTORY_MAX);
  ttsStore.set({ history: next });
  ttsHistory.persist(next);
}

export function clearHistory() {
  ttsStore.set({ history: [] });
  ttsHistory.persist([]);
}

export function clearText() {
  ttsStore.set({
    text: "",
    single: null,
    batch: null,
    error: "",
    refineNotice: "",
    textBeforeRefine: null,
  });
}

export function undoRefine() {
  const { textBeforeRefine } = ttsStore.get();
  if (textBeforeRefine !== null) {
    ttsStore.set({
      text: textBeforeRefine,
      textBeforeRefine: null,
      refineNotice: "",
    });
  }
}

export async function aiRefine() {
  const { text, refineStyle } = ttsStore.get();
  if (!text.trim()) {
    ttsStore.set({ error: "请先输入文本再改写" });
    return;
  }
  ttsStore.set({ refining: true, error: "", refineNotice: "" });
  const original = text;
  try {
    const r = await api.ttsRefine({
      text: original,
      style: refineStyle.trim() || undefined,
    });
    ttsStore.set({
      textBeforeRefine: original,
      text: r.refined,
      refineNotice: `已优化为更适合朗读的版本:${r.char_count_before} → ${r.char_count_after} 字 · 耗时 ${(r.latency_ms / 1000).toFixed(1)} 秒`,
    });
  } catch (e) {
    ttsStore.set({ error: `改写失败:${e}` });
  } finally {
    ttsStore.set({ refining: false });
  }
}

async function runSingle() {
  const seq = ++taskSeq;
  const alive = () => taskSeq === seq;
  abortCtl?.abort(); // 取消可能在跑的批量,避免两路结果交错
  const { text, voice, format, instructions } = ttsStore.get();
  ttsStore.set({ loading: true, error: "", single: null, batch: null });
  try {
    const r = await api.ttsSynthesize({
      text,
      voice,
      audio_format: format,
      instructions: instructions.trim() || undefined,
    });
    if (!alive()) return;
    ttsStore.set({ single: r, playToken: ttsStore.get().playToken + 1 });
    pushHistory({
      id: `${Date.now()}-${Math.random().toString(36).slice(2, 7)}`,
      ts: new Date().toISOString(),
      mode: "single",
      text,
      voice: r.voice,
      source: r.source,
      audio_format: r.audio_format,
      segments: [{ audio_url: r.audio_url, bytes: r.bytes, text }],
      total_bytes: r.bytes,
    });
  } catch (e) {
    if (alive()) ttsStore.set({ error: String(e) });
  } finally {
    if (alive()) ttsStore.set({ loading: false });
  }
}

async function runBatch() {
  const seq = ++taskSeq;
  const alive = () => taskSeq === seq;
  const { text, voice, format, segMax, instructions } = ttsStore.get();
  ttsStore.set({
    loading: true,
    error: "",
    single: null,
    batch: { total: 0, items: [] },
  });
  abortCtl?.abort();
  abortCtl = new AbortController();
  const signal = abortCtl.signal;

  const items: BatchSegmentEvent[] = [];
  let total = 0;
  let voiceUsed = voice;
  let sourceUsed: VoiceRecord["source"] = "default";

  try {
    await api.ttsBatch(
      {
        text,
        voice,
        audio_format: format,
        segment_max_chars: segMax,
        instructions: instructions.trim() || undefined,
      },
      {
        onPlan: (e) => {
          if (!alive()) return;
          total = e.total;
          ttsStore.set({ batch: { total: e.total, items: [] } });
        },
        onSegment: (e) => {
          if (!alive()) return;
          items.push(e);
          voiceUsed = e.voice;
          sourceUsed = e.source;
          ttsStore.set({ batch: { total, items: [...items] } });
        },
        onError: (msg) => {
          if (alive()) ttsStore.set({ error: msg });
        },
        onDone: () => {
          if (!alive()) return;
          const totalBytes = items.reduce((s, x) => s + x.bytes, 0);
          if (items.length > 0) {
            pushHistory({
              id: `${Date.now()}-${Math.random().toString(36).slice(2, 7)}`,
              ts: new Date().toISOString(),
              mode: "batch",
              text,
              voice: voiceUsed,
              source: sourceUsed,
              audio_format: format,
              segments: items.map((x) => ({
                audio_url: x.audio_url,
                bytes: x.bytes,
                text: x.text,
              })),
              total_bytes: totalBytes,
            });
          }
        },
      },
      signal,
    );
  } catch (e) {
    if (alive()) ttsStore.set({ error: String(e) });
  } finally {
    if (alive()) ttsStore.set({ loading: false });
  }
}

/** 提交:按当前 mode 走单段或批量。 */
export function runTts() {
  const { mode } = ttsStore.get();
  if (mode === "single") void runSingle();
  else void runBatch();
}

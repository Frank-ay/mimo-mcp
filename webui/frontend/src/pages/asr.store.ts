/** ASR 页的全局任务 store:状态 + 流式 fetch 都在模块单例里,切换路由不中断。 */
import {
  api,
  type ASRChunkSegmentEvent,
  type ASRResult,
  type DiarizeSegment,
  type DiarizeSegmentEvent,
} from "@/lib/api";
import { createStore } from "@/lib/taskStore";

export type Mode = "single" | "chunked" | "diarize";

export interface ChunkSeg {
  index: number;
  start: number;
  end: number;
  text: string;
}
export interface ChunkState {
  total: number;
  duration: number;
  segments: ChunkSeg[];
}
export interface DiarState {
  duration: number;
  numSpeakers: number;
  statusMsg: string;
  segments: DiarizeSegment[];
}

export interface AsrState {
  file: File | null;
  language: string;
  mode: Mode;
  segmentSeconds: number;
  speakerMode: "auto" | "manual";
  numSpeakers: number;
  running: boolean;
  resp: ASRResult | null;
  chunk: ChunkState | null;
  diar: DiarState | null;
  error: string;
}

const CHUNK_THRESHOLD = 7 * 1024 * 1024; // 超过约 7MB 建议分段

const initial: AsrState = {
  file: null,
  language: "auto",
  mode: "single",
  segmentSeconds: 120,
  speakerMode: "auto",
  numSpeakers: 2,
  running: false,
  resp: null,
  chunk: null,
  diar: null,
  error: "",
};

export const asrStore = createStore<AsrState>(initial);

let abortCtl: AbortController | null = null;
// 任务代号:每次新任务自增。旧任务被取代后,其迟到的回调/then/catch/finally
// 用 seq !== taskSeq 守卫丢弃,避免覆盖新任务状态(如把 AbortError 写回)。
let taskSeq = 0;

export function pickAsrFile(f: File | null) {
  const patch: Partial<AsrState> = {
    file: f,
    resp: null,
    chunk: null,
    diar: null,
    error: "",
  };
  if (f && f.size > CHUNK_THRESHOLD && asrStore.get().mode === "single") {
    patch.mode = "chunked";
  }
  asrStore.set(patch);
}

export function setAsrMode(mode: Mode) {
  asrStore.set({ mode, resp: null, chunk: null, diar: null, error: "" });
}

export function startAsr() {
  const s = asrStore.get();
  if (!s.file) {
    asrStore.set({ error: "请先选择音频" });
    return;
  }
  const seq = ++taskSeq;
  const alive = () => taskSeq === seq;
  asrStore.set({
    running: true,
    resp: null,
    chunk: null,
    diar: null,
    error: "",
  });
  abortCtl?.abort();
  abortCtl = new AbortController();
  const signal = abortCtl.signal;

  if (s.mode === "single") {
    api
      .asr({ file: s.file, language: s.language })
      .then((r) => {
        if (alive()) asrStore.set({ resp: r });
      })
      .catch((e) => {
        if (alive()) asrStore.set({ error: String(e) });
      })
      .finally(() => {
        if (alive()) asrStore.set({ running: false });
      });
    return;
  }

  if (s.mode === "chunked") {
    const form = new FormData();
    form.append("file", s.file);
    form.append("language", s.language);
    form.append("segment_seconds", String(s.segmentSeconds));
    const segs: ChunkSeg[] = [];
    let total = 0;
    let duration = 0;
    void api
      .asrChunked(
        form,
        {
          onPlan: (e) => {
            if (!alive()) return;
            total = e.total;
            duration = e.duration;
            asrStore.set({ chunk: { total, duration, segments: [] } });
          },
          onSegment: (e: ASRChunkSegmentEvent) => {
            if (!alive()) return;
            segs.push({
              index: e.index,
              start: e.start,
              end: e.end,
              text: e.text,
            });
            asrStore.set({ chunk: { total, duration, segments: [...segs] } });
          },
          onSummary: (e) => {
            if (!alive()) return;
            asrStore.set({
              resp: {
                text: e.text,
                model: "mimo-v2.5-asr",
                language: s.language,
              },
            });
          },
          onError: (msg) => {
            if (alive()) asrStore.set({ error: msg });
          },
          onDone: () => {
            if (alive()) asrStore.set({ running: false });
          },
        },
        signal,
      )
      .catch((e) => {
        if (alive()) asrStore.set({ error: String(e), running: false });
      });
    return;
  }

  // diarize
  const form = new FormData();
  form.append("file", s.file);
  form.append("language", s.language);
  form.append(
    "num_speakers",
    s.speakerMode === "manual" ? String(s.numSpeakers) : "-1",
  );
  const segs: DiarizeSegment[] = [];
  let duration = 0;
  let numSp = 0;
  let statusMsg = "";
  asrStore.set({
    diar: { duration: 0, numSpeakers: 0, statusMsg: "", segments: [] },
  });
  void api
    .asrDiarize(
      form,
      {
        onStatus: (msg) => {
          if (!alive()) return;
          statusMsg = msg;
          asrStore.set({
            diar: { duration, numSpeakers: numSp, statusMsg, segments: [...segs] },
          });
        },
        onPlan: (e) => {
          if (!alive()) return;
          duration = e.duration;
          numSp = e.num_speakers;
          statusMsg = `检测到 ${e.num_speakers} 个说话人,共 ${e.total} 段,识别中…`;
          asrStore.set({
            diar: { duration, numSpeakers: numSp, statusMsg, segments: [...segs] },
          });
        },
        onSegment: (e: DiarizeSegmentEvent) => {
          if (!alive()) return;
          segs.push({
            index: e.index,
            speaker: e.speaker,
            start: e.start,
            end: e.end,
            text: e.text,
          });
          asrStore.set({
            diar: { duration, numSpeakers: numSp, statusMsg, segments: [...segs] },
          });
        },
        onSummary: (e) => {
          if (!alive()) return;
          asrStore.set({
            diar: {
              duration: e.duration,
              numSpeakers: e.num_speakers,
              statusMsg: "",
              segments: e.segments,
            },
          });
        },
        onError: (msg) => {
          if (alive()) asrStore.set({ error: msg });
        },
        onDone: () => {
          if (alive()) asrStore.set({ running: false });
        },
      },
      signal,
    )
    .catch((e) => {
      if (alive()) asrStore.set({ error: String(e), running: false });
    });
}

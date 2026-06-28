/** Vision 页的全局任务 store:状态 + 长视频分段 SSE 都在模块单例里,切换路由不中断。 */
import {
  api,
  type ChunkedPlanEvent,
  type ChunkedSegmentEvent,
  type ChunkedSummaryEvent,
} from "@/lib/api";
import { createHistory } from "@/lib/history";
import { createStore } from "@/lib/taskStore";

export type Mode = "image" | "video";
export type VideoSource = "file" | "url";

// ---- localStorage 历史 ----
export const HISTORY_MAX = 30;
const visionHistory = createHistory<VisionHistoryItem>(
  "mimo:vision:history",
  HISTORY_MAX,
);

export interface VisionHistoryItem {
  id: string;
  ts: string; // ISO 时间
  kind: "image" | "video" | "video_url" | "video_chunked" | "video_chunked_url";
  inputLabel: string; // 文件名 / URL / 标题
  prompt: string;
  result?: string; // 单段:完整 content;分段:综合 summary
  segments?: { start: number; end: number; description: string }[];
  duration?: number;
}

export interface UrlMeta {
  duration: number | null;
  title?: string | null;
  uploader?: string | null;
  thumbnail?: string | null;
  extractor?: string | null;
  size?: number | null;
}

export interface ChunkedState {
  total: number;
  duration: number;
  segments: ChunkedSegmentEvent[];
  summary: string;
}

export interface VisionState {
  // ---- 输入 ----
  mode: Mode;
  videoSource: VideoSource;
  imageFile: File | null;
  videoFile: File | null;
  videoDuration: number | null;
  videoUrl: string;
  prompt: string;
  model: string; // 留空走后端默认 mimo-v2.5
  chunkedMode: boolean;
  segmentSeconds: number;
  // ---- URL 元信息探针 ----
  urlProbing: boolean;
  urlProbeError: string;
  urlMeta: UrlMeta | null;
  // ---- 输出 ----
  loading: boolean;
  output: string;
  error: string;
  chunked: ChunkedState | null;
  // ---- 历史 ----
  history: VisionHistoryItem[];
}

const initial: VisionState = {
  mode: "image",
  videoSource: "file",
  imageFile: null,
  videoFile: null,
  videoDuration: null,
  videoUrl: "",
  prompt: "请详细描述这段内容。",
  model: "",
  chunkedMode: false,
  segmentSeconds: 50,
  urlProbing: false,
  urlProbeError: "",
  urlMeta: null,
  loading: false,
  output: "",
  error: "",
  chunked: null,
  history: visionHistory.load(),
};

export const visionStore = createStore<VisionState>(initial);

// 流式任务的 AbortController(模块级,只在新任务开始时 abort 旧的)
let abortCtl: AbortController | null = null;
// 任务代号:旧任务被取代后,其迟到回调/catch/finally 用守卫丢弃,避免覆盖新任务状态。
let taskSeq = 0;
// URL probe 的防抖定时器(模块级,切走不中断)
let probeTimer: ReturnType<typeof setTimeout> | null = null;

function makeId(): string {
  return `${Date.now()}-${Math.random().toString(36).slice(2, 7)}`;
}

// ---- 历史操作(写 store 同步落 localStorage)----
function pushHistory(item: VisionHistoryItem) {
  const next = [item, ...visionStore.get().history].slice(0, HISTORY_MAX);
  visionHistory.persist(next);
  visionStore.set({ history: next });
}

export function deleteHistory(id: string) {
  const next = visionStore.get().history.filter((h) => h.id !== id);
  visionHistory.persist(next);
  visionStore.set({ history: next });
}

export function clearHistory() {
  const { history } = visionStore.get();
  if (history.length > 0 && !confirm(`确定清空全部 ${history.length} 条历史?`))
    return;
  visionHistory.persist([]);
  visionStore.set({ history: [] });
}

// ---- 输入 setter ----
export function setMode(mode: Mode) {
  visionStore.set({ mode });
  maybeProbeOnContextChange();
}

export function setVideoSource(videoSource: VideoSource) {
  visionStore.set({ videoSource });
  maybeProbeOnContextChange();
}

/**
 * 切到「视频 + URL」上下文时,用当前已填的 URL 重新触发探针。
 * 对齐旧组件 useEffect([videoUrl, videoSource, mode]) 的行为。
 */
function maybeProbeOnContextChange() {
  const s = visionStore.get();
  if (s.mode === "video" && s.videoSource === "url" && s.videoUrl.trim()) {
    setVideoUrl(s.videoUrl);
  }
}

export function setImageFile(f: File | null) {
  visionStore.set({ imageFile: f });
}

export function setPrompt(prompt: string) {
  visionStore.set({ prompt });
}

export function setModel(model: string) {
  visionStore.set({ model });
}

export function setChunkedMode(chunkedMode: boolean) {
  visionStore.set({ chunkedMode });
}

export function setSegmentSeconds(segmentSeconds: number) {
  visionStore.set({ segmentSeconds });
}

/** 选择本地视频文件,并读取时长元信息(异步回调更新 store)。 */
export function handleVideoFileSelect(f: File | null) {
  visionStore.set({ videoFile: f, videoDuration: null });
  if (!f) return;
  const v = document.createElement("video");
  v.preload = "metadata";
  v.src = URL.createObjectURL(f);
  v.onloadedmetadata = () => {
    visionStore.set({
      videoDuration: Number.isFinite(v.duration) ? v.duration : null,
    });
    URL.revokeObjectURL(v.src);
  };
  v.onerror = () => {
    URL.revokeObjectURL(v.src);
  };
}

/**
 * 设置视频 URL,并在 600ms 防抖后自动调 yt-dlp probe 拿元信息。
 * 防抖定时器在模块级,切换路由不会中断 probe。
 */
export function setVideoUrl(raw: string) {
  visionStore.set({ videoUrl: raw, urlMeta: null, urlProbeError: "" });

  if (probeTimer) {
    clearTimeout(probeTimer);
    probeTimer = null;
  }

  const url = raw.trim();
  const s = visionStore.get();
  // 仅视频 + URL 模式才探针
  if (s.mode !== "video" || s.videoSource !== "url" || !url) return;

  probeTimer = setTimeout(async () => {
    probeTimer = null;
    visionStore.set({ urlProbing: true });
    try {
      const meta = await api.videoProbe({ video_url: url });
      // 避免竞态:URL 已被改掉就丢弃这次结果
      if (visionStore.get().videoUrl.trim() !== url) return;
      visionStore.set({
        urlMeta: {
          duration: meta.duration,
          title: meta.title,
          uploader: meta.uploader,
          thumbnail: meta.thumbnail,
          extractor: meta.extractor,
          size: meta.size,
        },
      });
      // 时长 > 90 秒,自动勾选分段(覆盖之前的状态,避免用户漏勾)
      if (meta.duration !== null && meta.duration > 90) {
        visionStore.set({ chunkedMode: true });
      }
    } catch (e) {
      if (visionStore.get().videoUrl.trim() !== url) return;
      visionStore.set({ urlProbeError: String(e) });
    } finally {
      if (visionStore.get().videoUrl.trim() === url) {
        visionStore.set({ urlProbing: false });
      }
    }
  }, 600);
}

/** 发起分析:单段(image/video/url)或长视频分段(SSE 流式)。 */
export function send() {
  const s = visionStore.get();
  const seq = ++taskSeq;
  const alive = () => taskSeq === seq;
  visionStore.set({ loading: true, error: "", output: "", chunked: null });

  // 长视频分段模式 — 仅视频且勾选时启用(SSE 流式)
  if (s.mode === "video" && s.chunkedMode) {
    if (s.videoSource === "file" && !s.videoFile) {
      visionStore.set({
        error: String(new Error("请先选择视频文件")),
        loading: false,
      });
      return;
    }
    if (s.videoSource === "url" && !s.videoUrl.trim()) {
      visionStore.set({
        error: String(new Error("请输入视频 URL")),
        loading: false,
      });
      return;
    }

    const form = new FormData();
    form.append("prompt", s.prompt);
    form.append("segment_seconds", String(s.segmentSeconds));
    if (s.videoSource === "file" && s.videoFile)
      form.append("file", s.videoFile);
    if (s.videoSource === "url") form.append("video_url", s.videoUrl.trim());

    const state: ChunkedState = {
      total: 0,
      duration: 0,
      segments: [],
      summary: "",
    };
    visionStore.set({ chunked: { ...state } });

    abortCtl?.abort();
    abortCtl = new AbortController();

    void api
      .videoChunked(
        form,
        {
          onPlan: (e: ChunkedPlanEvent) => {
            if (!alive()) return;
            state.total = e.total;
            state.duration = e.duration;
            visionStore.set({ chunked: { ...state } });
          },
          onSegment: (e: ChunkedSegmentEvent) => {
            if (!alive()) return;
            state.segments = [...state.segments, e];
            visionStore.set({ chunked: { ...state } });
          },
          onSummary: (e: ChunkedSummaryEvent) => {
            if (!alive()) return;
            state.summary = e.text;
            visionStore.set({ chunked: { ...state } });
            // 综合到达即视为成功完成,落历史
            pushHistory({
              id: makeId(),
              ts: new Date().toISOString(),
              kind:
                s.videoSource === "url" ? "video_chunked_url" : "video_chunked",
              inputLabel:
                s.videoSource === "url"
                  ? s.videoUrl.trim()
                  : (s.videoFile?.name ?? "(未知文件)"),
              prompt: s.prompt,
              result: e.text,
              segments: state.segments.map((seg) => ({
                start: seg.start,
                end: seg.end,
                description: seg.description,
              })),
              duration: state.duration,
            });
          },
          onError: (msg) => {
            if (alive()) visionStore.set({ error: msg });
          },
        },
        abortCtl.signal,
      )
      .catch((e) => {
        if (alive()) visionStore.set({ error: String(e) });
      })
      .finally(() => {
        if (alive()) visionStore.set({ loading: false });
      });
    return;
  }

  // 单段模式(原逻辑)
  void runSingle(s, alive);
}

async function runSingle(s: VisionState, alive: () => boolean) {
  abortCtl?.abort(); // 取消可能在跑的分段任务
  try {
    let resp: { choices?: { message?: { content?: string } }[] };
    if (s.mode === "image") {
      if (!s.imageFile) throw new Error("请先选择图片");
      const form = new FormData();
      form.append("prompt", s.prompt);
      form.append("file", s.imageFile);
      if (s.model) form.append("model", s.model);
      resp = (await api.imageUnderstand(form)) as never;
    } else if (s.videoSource === "file") {
      if (!s.videoFile) throw new Error("请先选择视频文件");
      const form = new FormData();
      form.append("prompt", s.prompt);
      form.append("file", s.videoFile);
      if (s.model) form.append("model", s.model);
      resp = (await api.videoUnderstand(form)) as never;
    } else {
      if (!s.videoUrl.trim()) throw new Error("请输入视频 URL");
      resp = (await api.videoUnderstandUrl({
        video_url: s.videoUrl.trim(),
        prompt: s.prompt,
        model: s.model || undefined,
      })) as never;
    }
    if (!alive()) return;
    const text =
      resp.choices?.[0]?.message?.content ?? JSON.stringify(resp, null, 2);
    visionStore.set({ output: text });
    // 落历史
    pushHistory({
      id: makeId(),
      ts: new Date().toISOString(),
      kind:
        s.mode === "image"
          ? "image"
          : s.videoSource === "url"
            ? "video_url"
            : "video",
      inputLabel:
        s.mode === "image"
          ? (s.imageFile?.name ?? "(未知图片)")
          : s.videoSource === "url"
            ? s.videoUrl.trim()
            : (s.videoFile?.name ?? "(未知视频)"),
      prompt: s.prompt,
      result: text,
    });
  } catch (e) {
    if (alive()) visionStore.set({ error: String(e) });
  } finally {
    if (alive()) visionStore.set({ loading: false });
  }
}

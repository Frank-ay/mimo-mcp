import { useEffect, useRef, useState } from "react";
import {
  Check,
  Copy,
  FileVideo,
  Link2,
  Loader2,
  Scissors,
  Upload,
} from "lucide-react";
import {
  api,
  type ChunkedPlanEvent,
  type ChunkedSegmentEvent,
  type ChunkedSummaryEvent,
} from "@/lib/api";
import { Button } from "@/components/ui/button";
import { Badge } from "@/components/ui/badge";
import { Card, CardDesc, CardHeader, CardTitle } from "@/components/ui/card";

type Mode = "image" | "video";
type VideoSource = "file" | "url";

const URL_HINTS = [
  "https://example.com/clip.mp4",
  "https://www.bilibili.com/video/BV1xx411c7mD/",
  "https://www.youtube.com/watch?v=dQw4w9WgXcQ",
];

interface ChunkedState {
  total: number;
  duration: number;
  segments: ChunkedSegmentEvent[];
  summary: string;
}

function fmtTime(sec: number) {
  const m = Math.floor(sec / 60);
  const s = Math.floor(sec % 60);
  return `${m}:${s.toString().padStart(2, "0")}`;
}

/** 一键复制到剪贴板,带「已复制 ✓」短暂回显。 */
function CopyButton({
  text,
  label = "复制",
}: {
  text: string;
  label?: string;
}) {
  const [copied, setCopied] = useState(false);

  async function handle() {
    if (!text) return;
    try {
      await navigator.clipboard.writeText(text);
      setCopied(true);
      setTimeout(() => setCopied(false), 2000);
    } catch {
      // 兼容老浏览器:用临时 textarea + execCommand
      const ta = document.createElement("textarea");
      ta.value = text;
      ta.style.position = "fixed";
      ta.style.opacity = "0";
      document.body.appendChild(ta);
      ta.select();
      try {
        document.execCommand("copy");
        setCopied(true);
        setTimeout(() => setCopied(false), 2000);
      } finally {
        document.body.removeChild(ta);
      }
    }
  }

  return (
    <Button
      variant="ghost"
      size="sm"
      onClick={handle}
      disabled={!text}
      title={copied ? "已复制到剪贴板" : "复制全部文本到剪贴板"}
    >
      {copied ? (
        <Check size={14} className="text-emerald-400" />
      ) : (
        <Copy size={14} />
      )}
      {copied ? "已复制" : label}
    </Button>
  );
}

export default function Vision() {
  const [mode, setMode] = useState<Mode>("image");
  const [videoSource, setVideoSource] = useState<VideoSource>("file");
  const [imageFile, setImageFile] = useState<File | null>(null);
  const [videoFile, setVideoFile] = useState<File | null>(null);
  const [videoDuration, setVideoDuration] = useState<number | null>(null);

  function handleVideoFileSelect(f: File | null) {
    setVideoFile(f);
    setVideoDuration(null);
    if (!f) return;
    const v = document.createElement("video");
    v.preload = "metadata";
    v.src = URL.createObjectURL(f);
    v.onloadedmetadata = () => {
      setVideoDuration(Number.isFinite(v.duration) ? v.duration : null);
      URL.revokeObjectURL(v.src);
    };
    v.onerror = () => {
      URL.revokeObjectURL(v.src);
    };
  }
  const [videoUrl, setVideoUrl] = useState("");
  const [urlProbing, setUrlProbing] = useState(false);
  const [urlProbeError, setUrlProbeError] = useState<string>("");
  const [urlMeta, setUrlMeta] = useState<{
    duration: number | null;
    title?: string | null;
    uploader?: string | null;
    thumbnail?: string | null;
    extractor?: string | null;
    size?: number | null;
  } | null>(null);
  const [prompt, setPrompt] = useState("请详细描述这段内容。");
  const [chunkedMode, setChunkedMode] = useState(false);
  const [segmentSeconds, setSegmentSeconds] = useState(50);

  // URL 输入 debounce 500ms 后,自动调 yt-dlp probe 拿元信息
  useEffect(() => {
    if (mode !== "video" || videoSource !== "url") return;
    const url = videoUrl.trim();
    setUrlMeta(null);
    setUrlProbeError("");
    if (!url) return;

    const handle = setTimeout(async () => {
      setUrlProbing(true);
      try {
        const meta = await api.videoProbe({ video_url: url });
        setUrlMeta({
          duration: meta.duration,
          title: meta.title,
          uploader: meta.uploader,
          thumbnail: meta.thumbnail,
          extractor: meta.extractor,
          size: meta.size,
        });
        // 时长 > 90 秒,自动勾选分段(覆盖之前的状态,避免用户漏勾)
        if (meta.duration !== null && meta.duration > 90) {
          setChunkedMode(true);
        }
      } catch (e) {
        setUrlProbeError(String(e));
      } finally {
        setUrlProbing(false);
      }
    }, 600);
    return () => clearTimeout(handle);
  }, [videoUrl, videoSource, mode]);
  const [loading, setLoading] = useState(false);
  const [output, setOutput] = useState<string>("");
  const [error, setError] = useState<string>("");
  const [chunked, setChunked] = useState<ChunkedState | null>(null);
  const abortRef = useRef<AbortController | null>(null);

  async function send() {
    setLoading(true);
    setError("");
    setOutput("");
    setChunked(null);

    try {
      // 长视频分段模式 — 仅视频且勾选时启用
      if (mode === "video" && chunkedMode) {
        if (videoSource === "file" && !videoFile)
          throw new Error("请先选择视频文件");
        if (videoSource === "url" && !videoUrl.trim())
          throw new Error("请输入视频 URL");

        const form = new FormData();
        form.append("prompt", prompt);
        form.append("segment_seconds", String(segmentSeconds));
        if (videoSource === "file" && videoFile) form.append("file", videoFile);
        if (videoSource === "url") form.append("video_url", videoUrl.trim());

        const state: ChunkedState = {
          total: 0,
          duration: 0,
          segments: [],
          summary: "",
        };
        setChunked({ ...state });
        abortRef.current?.abort();
        abortRef.current = new AbortController();

        await api.videoChunked(
          form,
          {
            onPlan: (e: ChunkedPlanEvent) => {
              state.total = e.total;
              state.duration = e.duration;
              setChunked({ ...state });
            },
            onSegment: (e: ChunkedSegmentEvent) => {
              state.segments = [...state.segments, e];
              setChunked({ ...state });
            },
            onSummary: (e: ChunkedSummaryEvent) => {
              state.summary = e.text;
              setChunked({ ...state });
            },
            onError: (msg) => setError(msg),
          },
          abortRef.current.signal,
        );
        return;
      }

      // 单段模式(原逻辑)
      let resp: { choices?: { message?: { content?: string } }[] };
      if (mode === "image") {
        if (!imageFile) throw new Error("请先选择图片");
        const form = new FormData();
        form.append("prompt", prompt);
        form.append("file", imageFile);
        resp = (await api.imageUnderstand(form)) as never;
      } else if (videoSource === "file") {
        if (!videoFile) throw new Error("请先选择视频文件");
        const form = new FormData();
        form.append("prompt", prompt);
        form.append("file", videoFile);
        resp = (await api.videoUnderstand(form)) as never;
      } else {
        if (!videoUrl.trim()) throw new Error("请输入视频 URL");
        resp = (await api.videoUnderstandUrl({
          video_url: videoUrl.trim(),
          prompt,
        })) as never;
      }
      setOutput(
        resp.choices?.[0]?.message?.content ?? JSON.stringify(resp, null, 2),
      );
    } catch (e) {
      setError(String(e));
    } finally {
      setLoading(false);
    }
  }

  return (
    <div className="space-y-6">
      <div>
        <h1 className="text-2xl font-bold">图像 / 视频理解</h1>
        <p className="text-sm text-[var(--color-fg-muted)]">
          基于 mimo-v2.5 全模态。视频支持本地上传 + B 站/YouTube/抖音
          等视频站(yt-dlp 自动下载)。**长视频分段模式**可突破 MiMo 单次 50 MB
          上限。
        </p>
      </div>

      <Card>
        <CardHeader>
          <div>
            <CardTitle>输入</CardTitle>
            <CardDesc>切换图片 / 视频模式</CardDesc>
          </div>
          <div className="flex gap-2">
            <Button
              variant={mode === "image" ? "default" : "outline"}
              size="sm"
              onClick={() => setMode("image")}
            >
              图片
            </Button>
            <Button
              variant={mode === "video" ? "default" : "outline"}
              size="sm"
              onClick={() => setMode("video")}
            >
              视频
            </Button>
          </div>
        </CardHeader>

        {mode === "image" ? (
          <label className="mb-3 flex cursor-pointer items-center gap-3 rounded-md border border-dashed border-[var(--color-border)] bg-[var(--color-panel-2)] px-4 py-6 text-sm">
            <Upload size={18} />
            <span>
              {imageFile ? imageFile.name : "点击选择图片(jpg / png / webp)"}
            </span>
            <input
              type="file"
              accept="image/*"
              className="hidden"
              onChange={(e) => setImageFile(e.target.files?.[0] ?? null)}
            />
          </label>
        ) : (
          <div className="mb-3 space-y-3">
            <div className="flex gap-2">
              <Button
                variant={videoSource === "file" ? "default" : "outline"}
                size="sm"
                onClick={() => setVideoSource("file")}
              >
                <Upload size={14} /> 本地视频
              </Button>
              <Button
                variant={videoSource === "url" ? "default" : "outline"}
                size="sm"
                onClick={() => setVideoSource("url")}
              >
                <Link2 size={14} /> 视频 URL
              </Button>
            </div>

            {videoSource === "file" ? (
              <>
                <label className="flex cursor-pointer items-center gap-3 rounded-md border border-dashed border-[var(--color-border)] bg-[var(--color-panel-2)] px-4 py-6 text-sm">
                  <FileVideo size={18} />
                  <span>
                    {videoFile
                      ? `${videoFile.name} (${(videoFile.size / 1024 / 1024).toFixed(2)} MB${
                          videoDuration
                            ? ` · ${Math.floor(videoDuration / 60)}:${Math.floor(
                                videoDuration % 60,
                              )
                                .toString()
                                .padStart(2, "0")}`
                            : ""
                        })`
                      : "点击选择视频(mp4 / mov / webm)"}
                  </span>
                  <input
                    type="file"
                    accept="video/*"
                    className="hidden"
                    onChange={(e) =>
                      handleVideoFileSelect(e.target.files?.[0] ?? null)
                    }
                  />
                </label>
                {videoDuration !== null &&
                  videoDuration > 90 &&
                  !chunkedMode && (
                    <div className="rounded-md border border-amber-500/40 bg-amber-500/10 px-3 py-2 text-xs text-amber-300">
                      ⚠️ 该视频时长 {Math.floor(videoDuration)}{" "}
                      秒,超过单段分析上限(90 秒)。
                      要分析完整内容请勾选下方「长视频分段分析」,否则后端会拒绝并报错。
                    </div>
                  )}
              </>
            ) : (
              <div className="space-y-2">
                <input
                  value={videoUrl}
                  onChange={(e) => setVideoUrl(e.target.value)}
                  placeholder="直链 mp4 / B 站 / YouTube / 抖音 / 小红书 都行"
                  className="w-full rounded-md border border-[var(--color-border)] bg-[var(--color-panel-2)] px-3 py-2 text-sm"
                />
                <div className="flex flex-wrap gap-2 text-xs text-[var(--color-fg-muted)]">
                  示例:
                  {URL_HINTS.map((u) => (
                    <button
                      key={u}
                      type="button"
                      onClick={() => setVideoUrl(u)}
                      className="rounded border border-[var(--color-border)] px-2 py-0.5 hover:text-[var(--color-fg)]"
                    >
                      {new URL(u).hostname.replace("www.", "")}
                    </button>
                  ))}
                </div>
                {/* URL probe 状态:加载/失败/已拿到元信息 */}
                {urlProbing && (
                  <div className="flex items-center gap-2 rounded-md border border-[var(--color-border)] bg-[var(--color-panel-2)] px-3 py-2 text-xs text-[var(--color-fg-muted)]">
                    <Loader2 className="animate-spin" size={12} />
                    正在读取视频元信息(yt-dlp metadata)…
                  </div>
                )}
                {urlProbeError && !urlProbing && (
                  <div className="rounded-md border border-red-500/40 bg-red-500/10 px-3 py-2 text-xs text-red-300">
                    读取元信息失败:{urlProbeError}
                  </div>
                )}
                {urlMeta && !urlProbing && (
                  <div
                    className={
                      urlMeta.duration !== null && urlMeta.duration > 90
                        ? "rounded-md border border-emerald-500/40 bg-emerald-500/10 px-3 py-2 text-xs text-emerald-300"
                        : "rounded-md border border-[var(--color-border)] bg-[var(--color-panel-2)] px-3 py-2 text-xs"
                    }
                  >
                    <div className="flex items-start gap-3">
                      {urlMeta.thumbnail && (
                        // eslint-disable-next-line @next/next/no-img-element
                        <img
                          src={urlMeta.thumbnail}
                          alt=""
                          className="h-12 w-20 rounded object-cover"
                        />
                      )}
                      <div className="flex-1 space-y-0.5">
                        {urlMeta.title && (
                          <div className="font-medium text-[var(--color-fg)]">
                            📺 {urlMeta.title}
                          </div>
                        )}
                        <div className="text-[var(--color-fg-muted)]">
                          {urlMeta.duration !== null
                            ? `时长 ${fmtTime(urlMeta.duration)}`
                            : urlMeta.size
                              ? `体积 ${(urlMeta.size / 1024 / 1024).toFixed(1)} MB · 时长未知(直链)`
                              : "时长 / 体积未知"}
                          {urlMeta.uploader && ` · ${urlMeta.uploader}`}
                          {urlMeta.extractor && ` · ${urlMeta.extractor}`}
                        </div>
                        {urlMeta.duration !== null && urlMeta.duration > 90 && (
                          <div className="font-medium">
                            ✓ 已自动勾选「长视频分段分析」(超 90 秒单段无法处理)
                          </div>
                        )}
                        {urlMeta.duration !== null &&
                          urlMeta.duration <= 90 && (
                            <div className="text-[var(--color-fg-muted)]">
                              视频较短,默认走单段模式即可。
                            </div>
                          )}
                      </div>
                    </div>
                  </div>
                )}
                {videoUrl.trim() &&
                  !urlMeta &&
                  !urlProbing &&
                  !urlProbeError &&
                  !chunkedMode && (
                    <div className="rounded-md border border-amber-500/40 bg-amber-500/10 px-3 py-2 text-xs text-amber-300">
                      💡 直链 / 未知站点 URL 时长无法预探测。如果是长视频(&gt;
                      90 秒)请勾选下方「长视频分段分析」。
                    </div>
                  )}
              </div>
            )}

            {/* 长视频分段开关 */}
            <div className="rounded-md border border-[var(--color-border)] bg-[var(--color-panel-2)] px-3 py-2.5">
              <label className="flex items-start gap-2 cursor-pointer">
                <input
                  type="checkbox"
                  checked={chunkedMode}
                  onChange={(e) => setChunkedMode(e.target.checked)}
                  className="mt-1 accent-[var(--color-accent)]"
                />
                <div className="flex-1">
                  <div className="flex items-center gap-2">
                    <Scissors
                      size={14}
                      className="text-[var(--color-accent)]"
                    />
                    <span className="text-sm font-medium">
                      长视频分段分析(突破 50 MB 上限)
                    </span>
                  </div>
                  <div className="mt-1 text-xs text-[var(--color-fg-muted)]">
                    视频会被切成 N 段(每段约 {segmentSeconds}{" "}
                    秒),逐段独立分析后由 v2.5-pro 综合成完整内容。**适合 1
                    分钟以上 / 体积大的视频**;短视频不必勾(多耗 token)。
                  </div>
                  {chunkedMode && (
                    <div className="mt-2 flex items-center gap-2">
                      <span className="text-xs text-[var(--color-fg-muted)]">
                        每段时长(秒):
                      </span>
                      <input
                        type="range"
                        min={20}
                        max={90}
                        step={5}
                        value={segmentSeconds}
                        onChange={(e) =>
                          setSegmentSeconds(Number(e.target.value))
                        }
                        className="flex-1 accent-[var(--color-accent)]"
                      />
                      <span className="text-xs font-mono text-[var(--color-fg)]">
                        {segmentSeconds}s
                      </span>
                    </div>
                  )}
                </div>
              </label>
            </div>
          </div>
        )}

        <textarea
          value={prompt}
          onChange={(e) => setPrompt(e.target.value)}
          rows={3}
          className="w-full resize-y rounded-md border border-[var(--color-border)] bg-[var(--color-panel-2)] p-3 text-sm"
        />
        <div className="mt-3 flex justify-end">
          <Button onClick={send} disabled={loading}>
            {loading ? <Loader2 className="animate-spin" size={16} /> : null}
            {loading
              ? mode === "video" && chunkedMode
                ? "切段分析中…"
                : mode === "video" && videoSource === "url"
                  ? "下载并分析中…"
                  : "分析中…"
              : "分析"}
          </Button>
        </div>
      </Card>

      {error && (
        <Card>
          <pre className="overflow-auto rounded-md bg-red-500/10 p-3 text-sm text-red-300">
            {error}
          </pre>
        </Card>
      )}

      {/* 单段结果 */}
      {output && (
        <Card>
          <CardHeader>
            <CardTitle>分析结果</CardTitle>
            <CopyButton text={output} />
          </CardHeader>
          <pre className="whitespace-pre-wrap text-sm">{output}</pre>
        </Card>
      )}

      {/* 分段进度 + 综合结果 */}
      {chunked && (
        <>
          <Card>
            <CardHeader>
              <div>
                <CardTitle>分段进度</CardTitle>
                <CardDesc>
                  {chunked.total > 0
                    ? `共 ${chunked.total} 段 · 总时长 ${fmtTime(chunked.duration)} · 已完成 ${chunked.segments.length}/${chunked.total}`
                    : "正在切段…"}
                </CardDesc>
              </div>
              <div className="flex items-center gap-2">
                {chunked.segments.length > 0 && (
                  <CopyButton
                    text={chunked.segments
                      .map(
                        (seg) =>
                          `[${fmtTime(seg.start)}-${fmtTime(seg.end)}] 段 ${seg.index + 1}\n${seg.description}`,
                      )
                      .join("\n\n")}
                    label="复制全部段"
                  />
                )}
                {loading && chunked.segments.length < chunked.total && (
                  <Loader2
                    className="animate-spin text-[var(--color-fg-muted)]"
                    size={16}
                  />
                )}
              </div>
            </CardHeader>
            {chunked.total > 0 && (
              <div className="mb-3 h-2 overflow-hidden rounded bg-[var(--color-panel-2)]">
                <div
                  className="h-full bg-[var(--color-accent)] transition-all"
                  style={{
                    width: `${(chunked.segments.length / chunked.total) * 100}%`,
                  }}
                />
              </div>
            )}
            <div className="space-y-2">
              {chunked.segments.map((seg) => (
                <details
                  key={seg.index}
                  className="rounded-md border border-[var(--color-border)] bg-[var(--color-panel-2)] p-3"
                >
                  <summary className="flex cursor-pointer items-center gap-2 text-sm">
                    <Badge>段 {seg.index + 1}</Badge>
                    <span className="text-[var(--color-fg-muted)]">
                      {fmtTime(seg.start)} - {fmtTime(seg.end)} ·{" "}
                      {(seg.bytes / 1024 / 1024).toFixed(2)} MB
                    </span>
                  </summary>
                  <pre className="mt-2 whitespace-pre-wrap text-sm">
                    {seg.description}
                  </pre>
                </details>
              ))}
            </div>
          </Card>

          {chunked.summary && (
            <Card>
              <CardHeader>
                <div>
                  <CardTitle>综合分析</CardTitle>
                  <CardDesc>
                    v2.5-pro 把 {chunked.total} 段描述融合成连贯叙事
                  </CardDesc>
                </div>
                <CopyButton text={chunked.summary} />
              </CardHeader>
              <pre className="whitespace-pre-wrap text-sm leading-relaxed">
                {chunked.summary}
              </pre>
            </Card>
          )}
        </>
      )}
    </div>
  );
}

import { useState } from "react";
import {
  ChevronDown,
  ChevronRight,
  FileVideo,
  History,
  Link2,
  Loader2,
  Scissors,
  Trash2,
  Upload,
} from "lucide-react";
import { CopyButton } from "@/components/CopyButton";
import { Button } from "@/components/ui/button";
import { Badge } from "@/components/ui/badge";
import { Card, CardDesc, CardHeader, CardTitle } from "@/components/ui/card";
import { formatClock } from "@/lib/utils";
import {
  clearHistory,
  deleteHistory,
  handleVideoFileSelect,
  HISTORY_MAX,
  send,
  setChunkedMode,
  setImageFile,
  setMode,
  setModel,
  setPrompt,
  setSegmentSeconds,
  setVideoSource,
  setVideoUrl,
  type VisionHistoryItem,
  visionStore,
} from "./vision.store";

// ---- localStorage 历史 ----

function fmtRelTime(iso: string): string {
  try {
    const d = new Date(iso);
    return d.toLocaleString("zh-CN", { hour12: false });
  } catch {
    return iso;
  }
}

const URL_HINTS = [
  "https://example.com/clip.mp4",
  "https://www.bilibili.com/video/BV1xx411c7mD/",
  "https://www.youtube.com/watch?v=dQw4w9WgXcQ",
];

const VISION_MODELS = [
  "mimo-v2.5",
  "mimo-v2.5-pro",
  "mimo-v2-pro",
  "mimo-v2-flash",
];

export default function Vision() {
  const st = visionStore.use();
  const {
    mode,
    videoSource,
    imageFile,
    videoFile,
    videoDuration,
    videoUrl,
    urlProbing,
    urlProbeError,
    urlMeta,
    prompt,
    model,
    chunkedMode,
    segmentSeconds,
    loading,
    output,
    error,
    chunked,
    history,
  } = st;

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
                            ? `时长 ${formatClock(urlMeta.duration)}`
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
                        min={10}
                        max={120}
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

        <div className="mb-3">
          <label className="mb-1 block text-xs text-[var(--color-fg-muted)]">
            模型(选填)
          </label>
          <select
            value={model}
            onChange={(e) => setModel(e.target.value)}
            disabled={mode === "video" && chunkedMode}
            className="w-full rounded-md border border-[var(--color-border)] bg-[var(--color-panel-2)] px-2 py-1.5 text-sm disabled:opacity-50"
          >
            <option value="">默认(mimo-v2.5)</option>
            {VISION_MODELS.map((m) => (
              <option key={m} value={m}>
                {m}
              </option>
            ))}
          </select>
          {mode === "video" && chunkedMode && (
            <div className="mt-1 text-xs text-[var(--color-fg-muted)]">
              分段分析固定用 vision 模型逐段分析 + v2.5-pro 综合,不支持自选
            </div>
          )}
        </div>

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
                    ? `共 ${chunked.total} 段 · 总时长 ${formatClock(chunked.duration)} · 已完成 ${chunked.segments.length}/${chunked.total}`
                    : "正在切段…"}
                </CardDesc>
              </div>
              <div className="flex items-center gap-2">
                {chunked.segments.length > 0 && (
                  <CopyButton
                    text={chunked.segments
                      .map(
                        (seg) =>
                          `[${formatClock(seg.start)}-${formatClock(seg.end)}] 段 ${seg.index + 1}\n${seg.description}`,
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
                      {formatClock(seg.start)} - {formatClock(seg.end)} ·{" "}
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

      {/* 分析历史(localStorage 持久化) */}
      <Card>
        <CardHeader>
          <div>
            <CardTitle className="flex items-center gap-2">
              <History size={16} /> 分析历史
            </CardTitle>
            <CardDesc>
              最多 {HISTORY_MAX} 条 · 浏览器关掉再开还在 · localStorage 持久化
            </CardDesc>
          </div>
          {history.length > 0 && (
            <Button variant="ghost" size="sm" onClick={clearHistory}>
              <Trash2 size={14} /> 清空全部
            </Button>
          )}
        </CardHeader>
        {history.length === 0 ? (
          <div className="py-6 text-center text-sm text-[var(--color-fg-muted)]">
            还没有分析记录,做一次分析就会自动存档在这里。
          </div>
        ) : (
          <div className="space-y-2">
            {history.map((h) => (
              <HistoryRow
                key={h.id}
                item={h}
                onDelete={() => deleteHistory(h.id)}
              />
            ))}
          </div>
        )}
      </Card>
    </div>
  );
}

const HISTORY_KIND_LABEL: Record<VisionHistoryItem["kind"], string> = {
  image: "图片",
  video: "视频(单段)",
  video_url: "视频 URL(单段)",
  video_chunked: "视频(分段)",
  video_chunked_url: "视频 URL(分段)",
};

function HistoryRow({
  item,
  onDelete,
}: {
  item: VisionHistoryItem;
  onDelete: () => void;
}) {
  const [open, setOpen] = useState(false);
  const previewText = (item.result ?? "").trim().slice(0, 60);

  return (
    <div className="rounded-md border border-[var(--color-border)] bg-[var(--color-panel-2)]">
      <div className="flex items-center justify-between gap-2 px-3 py-2">
        <button
          type="button"
          onClick={() => setOpen((v) => !v)}
          className="flex flex-1 items-start gap-2 text-left"
        >
          {open ? (
            <ChevronDown
              size={14}
              className="mt-1 text-[var(--color-fg-muted)]"
            />
          ) : (
            <ChevronRight
              size={14}
              className="mt-1 text-[var(--color-fg-muted)]"
            />
          )}
          <div className="flex-1 min-w-0">
            <div className="flex items-center gap-2 text-xs">
              <Badge variant="muted">{HISTORY_KIND_LABEL[item.kind]}</Badge>
              <span className="text-[var(--color-fg-muted)]">
                {fmtRelTime(item.ts)}
              </span>
              {item.duration !== undefined && item.duration > 0 && (
                <span className="text-[var(--color-fg-muted)]">
                  · 时长 {Math.floor(item.duration)}s
                </span>
              )}
              {item.segments && item.segments.length > 0 && (
                <span className="text-[var(--color-fg-muted)]">
                  · {item.segments.length} 段
                </span>
              )}
            </div>
            <div className="mt-0.5 truncate text-xs text-[var(--color-fg-muted)]">
              {item.inputLabel}
            </div>
            <div className="mt-0.5 truncate text-sm">
              {previewText || "(无结果文本)"}
              {(item.result?.length ?? 0) > 60 && "…"}
            </div>
          </div>
        </button>
        <div className="flex items-center gap-1">
          {item.result && <CopyButton text={item.result} />}
          <Button
            variant="ghost"
            size="icon"
            onClick={onDelete}
            title="删除这条历史"
          >
            <Trash2 size={14} className="text-red-400" />
          </Button>
        </div>
      </div>
      {open && (
        <div className="space-y-2 border-t border-[var(--color-border)] p-3">
          <div className="text-xs text-[var(--color-fg-muted)]">
            提问:<span className="text-[var(--color-fg)]">{item.prompt}</span>
          </div>
          {item.result && (
            <div>
              <div className="mb-1 text-xs text-[var(--color-fg-muted)]">
                {item.segments ? "综合分析" : "结果"}:
              </div>
              <pre className="whitespace-pre-wrap rounded border border-[var(--color-border)] bg-[var(--color-panel)] p-2 text-sm leading-relaxed">
                {item.result}
              </pre>
            </div>
          )}
          {item.segments && item.segments.length > 0 && (
            <div>
              <div className="mb-1 text-xs text-[var(--color-fg-muted)]">
                各段描述({item.segments.length} 段):
              </div>
              <div className="space-y-1.5">
                {item.segments.map((seg, i) => (
                  <details
                    key={i}
                    className="rounded border border-[var(--color-border)] bg-[var(--color-panel)] p-2"
                  >
                    <summary className="cursor-pointer text-xs">
                      <Badge>段 {i + 1}</Badge>{" "}
                      <span className="text-[var(--color-fg-muted)]">
                        {Math.floor(seg.start)}s – {Math.floor(seg.end)}s
                      </span>
                    </summary>
                    <pre className="mt-2 whitespace-pre-wrap text-sm">
                      {seg.description}
                    </pre>
                  </details>
                ))}
              </div>
            </div>
          )}
        </div>
      )}
    </div>
  );
}

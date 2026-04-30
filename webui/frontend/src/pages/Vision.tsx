import { useState } from "react";
import { Loader2, Upload, Link2 } from "lucide-react";
import { api } from "@/lib/api";
import { Button } from "@/components/ui/button";
import { Card, CardDesc, CardHeader, CardTitle } from "@/components/ui/card";

type Mode = "image" | "video";
type VideoSource = "file" | "url";

const URL_HINTS = [
  "https://example.com/clip.mp4",
  "https://www.bilibili.com/video/BV1xx411c7mD/",
  "https://www.youtube.com/watch?v=dQw4w9WgXcQ",
];

export default function Vision() {
  const [mode, setMode] = useState<Mode>("image");
  const [videoSource, setVideoSource] = useState<VideoSource>("file");
  const [imageFile, setImageFile] = useState<File | null>(null);
  const [videoFile, setVideoFile] = useState<File | null>(null);
  const [videoUrl, setVideoUrl] = useState("");
  const [prompt, setPrompt] = useState("请详细描述这段内容。");
  const [loading, setLoading] = useState(false);
  const [output, setOutput] = useState<string>("");
  const [error, setError] = useState<string>("");

  async function send() {
    setLoading(true);
    setError("");
    setOutput("");
    try {
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
        // URL 模式走 JSON,后端会自动判断直链 / B 站等并下载转 DataURL
        resp = (await api.videoUnderstandUrl({
          video_url: videoUrl.trim(),
          prompt,
        })) as never;
      }

      setOutput(resp.choices?.[0]?.message?.content ?? JSON.stringify(resp, null, 2));
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
          基于 mimo-v2.5 全模态。视频支持本地上传 + B 站/YouTube/抖音 等视频站(yt-dlp 自动下载)。
        </p>
      </div>

      <Card>
        <CardHeader>
          <div>
            <CardTitle>输入</CardTitle>
            <CardDesc>切换图片 / 视频模式</CardDesc>
          </div>
          <div className="flex gap-2">
            <Button variant={mode === "image" ? "default" : "outline"} size="sm" onClick={() => setMode("image")}>
              图片
            </Button>
            <Button variant={mode === "video" ? "default" : "outline"} size="sm" onClick={() => setMode("video")}>
              视频
            </Button>
          </div>
        </CardHeader>

        {mode === "image" ? (
          <label className="mb-3 flex cursor-pointer items-center gap-3 rounded-md border border-dashed border-[var(--color-border)] bg-[var(--color-panel-2)] px-4 py-6 text-sm">
            <Upload size={18} />
            <span>{imageFile ? imageFile.name : "点击选择图片(jpg / png / webp)"}</span>
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
              <label className="flex cursor-pointer items-center gap-3 rounded-md border border-dashed border-[var(--color-border)] bg-[var(--color-panel-2)] px-4 py-6 text-sm">
                <Upload size={18} />
                <span>{videoFile ? `${videoFile.name} (${(videoFile.size / 1024 / 1024).toFixed(2)} MB)` : "点击选择视频(mp4 / mov / webm,≤ 50 MB)"}</span>
                <input
                  type="file"
                  accept="video/*"
                  className="hidden"
                  onChange={(e) => setVideoFile(e.target.files?.[0] ?? null)}
                />
              </label>
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
              </div>
            )}
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
              ? mode === "video" && videoSource === "url"
                ? "下载并分析中…"
                : "分析中…"
              : "分析"}
          </Button>
        </div>
      </Card>

      {(output || error) && (
        <Card>
          <CardHeader>
            <CardTitle>结果</CardTitle>
          </CardHeader>
          {error ? (
            <pre className="overflow-auto rounded-md bg-red-500/10 p-3 text-sm text-red-300">{error}</pre>
          ) : (
            <pre className="whitespace-pre-wrap text-sm">{output}</pre>
          )}
        </Card>
      )}
    </div>
  );
}

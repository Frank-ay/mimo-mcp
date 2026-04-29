import { useState } from "react";
import { Loader2, Upload } from "lucide-react";
import { api } from "@/lib/api";
import { Button } from "@/components/ui/button";
import { Card, CardDesc, CardHeader, CardTitle } from "@/components/ui/card";

type Mode = "image" | "video";

export default function Vision() {
  const [mode, setMode] = useState<Mode>("image");
  const [file, setFile] = useState<File | null>(null);
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
      const form = new FormData();
      form.append("prompt", prompt);
      let resp: { choices?: { message?: { content?: string } }[] };
      if (mode === "image") {
        if (!file) throw new Error("请先选择图片");
        form.append("file", file);
        resp = (await api.imageUnderstand(form)) as never;
      } else {
        if (!videoUrl) throw new Error("请输入视频 URL");
        form.append("video_url", videoUrl);
        resp = (await api.videoUnderstand(form)) as never;
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
          基于 mimo-v2.5 全模态。视频 M0 阶段仅 URL 模式,M1 实测后再开放本地上传。
        </p>
      </div>

      <Card>
        <CardHeader>
          <div>
            <CardTitle>输入</CardTitle>
            <CardDesc>切换图片 / 视频模式</CardDesc>
          </div>
          <div className="flex gap-2">
            <Button variant={mode === "image" ? "default" : "outline"} size="sm" onClick={() => setMode("image")}>图片</Button>
            <Button variant={mode === "video" ? "default" : "outline"} size="sm" onClick={() => setMode("video")}>视频</Button>
          </div>
        </CardHeader>

        {mode === "image" ? (
          <label className="mb-3 flex cursor-pointer items-center gap-3 rounded-md border border-dashed border-[var(--color-border)] bg-[var(--color-panel-2)] px-4 py-6 text-sm">
            <Upload size={18} />
            <span>{file ? file.name : "点击选择图片(jpg / png / webp)"}</span>
            <input
              type="file"
              accept="image/*"
              className="hidden"
              onChange={(e) => setFile(e.target.files?.[0] ?? null)}
            />
          </label>
        ) : (
          <input
            value={videoUrl}
            onChange={(e) => setVideoUrl(e.target.value)}
            placeholder="https://example.com/video.mp4"
            className="mb-3 w-full rounded-md border border-[var(--color-border)] bg-[var(--color-panel-2)] px-3 py-2 text-sm"
          />
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
            分析
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

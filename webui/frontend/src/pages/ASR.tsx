import { useState } from "react";
import { Loader2, Upload } from "lucide-react";
import { api } from "@/lib/api";
import { Button } from "@/components/ui/button";
import { Card, CardDesc, CardHeader, CardTitle } from "@/components/ui/card";
import { Badge } from "@/components/ui/badge";

export default function ASR() {
  const [file, setFile] = useState<File | null>(null);
  const [language, setLanguage] = useState("auto");
  const [withTs, setWithTs] = useState(false);
  const [loading, setLoading] = useState(false);
  const [resp, setResp] = useState<unknown>(null);
  const [error, setError] = useState("");

  async function submit() {
    if (!file) {
      setError("请先选择音频");
      return;
    }
    setLoading(true);
    setError("");
    setResp(null);
    try {
      const form = new FormData();
      form.append("file", file);
      form.append("language", language);
      form.append("with_timestamps", String(withTs));
      const r = await api.asr(form);
      setResp(r);
    } catch (e) {
      setError(String(e));
    } finally {
      setLoading(false);
    }
  }

  const isUnavailable =
    resp !== null &&
    typeof resp === "object" &&
    (resp as { status?: string }).status === "unavailable";

  return (
    <div className="space-y-6">
      <div>
        <h1 className="text-2xl font-bold">语音转写</h1>
        <p className="text-sm text-[var(--color-fg-muted)]">
          F7 ASR — PRD §15-Q6 决策:仅 MiMo 云端,云端缺失时显式 unavailable
        </p>
      </div>

      <Card>
        <CardHeader>
          <CardTitle>上传音频</CardTitle>
          <CardDesc>WAV / MP3</CardDesc>
        </CardHeader>

        <label className="mb-3 flex cursor-pointer items-center gap-3 rounded-md border border-dashed border-[var(--color-border)] bg-[var(--color-panel-2)] px-4 py-6 text-sm">
          <Upload size={18} />
          <span>{file ? file.name : "点击选择音频"}</span>
          <input
            type="file"
            accept="audio/*"
            className="hidden"
            onChange={(e) => setFile(e.target.files?.[0] ?? null)}
          />
        </label>

        <div className="grid grid-cols-1 gap-3 md:grid-cols-2">
          <select
            value={language}
            onChange={(e) => setLanguage(e.target.value)}
            className="rounded-md border border-[var(--color-border)] bg-[var(--color-panel-2)] px-3 py-2 text-sm"
          >
            <option value="auto">自动识别(中/英/方言)</option>
            <option value="zh">中文</option>
            <option value="en">英文</option>
            <option value="yue">粤语</option>
            <option value="wuu">吴语</option>
          </select>
          <label className="flex items-center gap-2 text-sm">
            <input type="checkbox" checked={withTs} onChange={(e) => setWithTs(e.target.checked)} />
            返回词级时间戳
          </label>
        </div>

        <div className="mt-4 flex justify-end">
          <Button onClick={submit} disabled={loading || !file}>
            {loading ? <Loader2 className="animate-spin" size={16} /> : null}
            转写
          </Button>
        </div>
      </Card>

      {error && (
        <Card>
          <pre className="rounded-md bg-red-500/10 p-3 text-sm text-red-300">{error}</pre>
        </Card>
      )}

      {resp !== null && (
        <Card>
          <CardHeader>
            <CardTitle>响应</CardTitle>
            {isUnavailable && <Badge variant="warning">unavailable</Badge>}
          </CardHeader>
          <pre className="whitespace-pre-wrap text-sm">{JSON.stringify(resp, null, 2)}</pre>
        </Card>
      )}
    </div>
  );
}

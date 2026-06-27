import { useState } from "react";
import { useNavigate } from "react-router-dom";
import { Upload, Loader2 } from "lucide-react";
import { api } from "@/lib/api";
import { Button } from "@/components/ui/button";
import { Card, CardDesc, CardHeader, CardTitle } from "@/components/ui/card";

export default function VoiceClone() {
  const nav = useNavigate();
  const [file, setFile] = useState<File | null>(null);
  const [name, setName] = useState("");
  const [description, setDescription] = useState("");
  const [submitting, setSubmitting] = useState(false);
  const [error, setError] = useState("");

  async function submit() {
    if (!file || !name.trim()) {
      setError("请选择参考音频并填写名称");
      return;
    }
    setSubmitting(true);
    setError("");
    try {
      await api.createClone({
        file,
        name,
        description: description.trim() || undefined,
      });
      nav("/voices");
    } catch (e) {
      setError(String(e));
    } finally {
      setSubmitting(false);
    }
  }

  return (
    <div className="space-y-6">
      <div>
        <h1 className="text-2xl font-bold">声音克隆</h1>
        <p className="text-sm text-[var(--color-fg-muted)]">
          上传 10-15 秒清晰参考音频,提交后会立即跑一次试听并生成 voice_id,可在
          mimo.tts / mimo.chat 中引用
        </p>
      </div>

      <Card>
        <CardHeader>
          <div>
            <CardTitle>新建克隆</CardTitle>
            <CardDesc>WAV / MP3,建议单声道、采样率 ≥ 16k</CardDesc>
          </div>
        </CardHeader>

        <label className="mb-3 flex cursor-pointer items-center gap-3 rounded-md border border-dashed border-[var(--color-border)] bg-[var(--color-panel-2)] px-4 py-6 text-sm">
          <Upload size={18} />
          <span>{file ? file.name : "点击选择参考音频"}</span>
          <input
            type="file"
            accept="audio/*"
            className="hidden"
            onChange={(e) => setFile(e.target.files?.[0] ?? null)}
          />
        </label>

        <div className="grid grid-cols-1 gap-3 md:grid-cols-2">
          <input
            value={name}
            onChange={(e) => setName(e.target.value)}
            placeholder="音色名称(必填)"
            className="rounded-md border border-[var(--color-border)] bg-[var(--color-panel-2)] px-3 py-2 text-sm"
          />
          <input
            value={description}
            onChange={(e) => setDescription(e.target.value)}
            placeholder="备注(选填)"
            className="rounded-md border border-[var(--color-border)] bg-[var(--color-panel-2)] px-3 py-2 text-sm"
          />
        </div>

        {file && (
          <div className="mt-3">
            <audio
              controls
              src={URL.createObjectURL(file)}
              className="w-full"
            />
          </div>
        )}

        {error && (
          <div className="mt-3 rounded-md bg-red-500/10 p-2 text-sm text-red-300">
            {error}
          </div>
        )}

        <div className="mt-4 flex justify-end gap-2">
          <Button variant="outline" onClick={() => nav("/voices")}>
            取消
          </Button>
          <Button onClick={submit} disabled={submitting}>
            {submitting ? <Loader2 className="animate-spin" size={16} /> : null}
            提交
          </Button>
        </div>
      </Card>
    </div>
  );
}

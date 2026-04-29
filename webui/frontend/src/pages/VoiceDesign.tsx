import { useState } from "react";
import { useNavigate } from "react-router-dom";
import { Loader2, Wand2 } from "lucide-react";
import { api } from "@/lib/api";
import { Button } from "@/components/ui/button";
import { Card, CardDesc, CardHeader, CardTitle } from "@/components/ui/card";

const SAMPLES = [
  "30 岁知识渊博的女性声音,轻微南方口音,适合财经新闻播报",
  "温暖、略带沙哑的男性播音员,40 岁左右",
  "活泼可爱的少女音色,语速偏快,适合游戏 NPC",
];

export default function VoiceDesign() {
  const nav = useNavigate();
  const [voicePrompt, setVoicePrompt] = useState("");
  const [name, setName] = useState("");
  const [submitting, setSubmitting] = useState(false);
  const [error, setError] = useState("");

  async function submit() {
    if (!voicePrompt.trim() || !name.trim()) {
      setError("请填写音色 prompt 与名称");
      return;
    }
    setSubmitting(true);
    setError("");
    try {
      const form = new FormData();
      form.append("voice_prompt", voicePrompt);
      form.append("name", name);
      await api.createDesign(form);
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
        <h1 className="text-2xl font-bold">声音设计</h1>
        <p className="text-sm text-[var(--color-fg-muted)]">
          用文字描述生成自定义音色,无需参考音频
        </p>
      </div>

      <Card>
        <CardHeader>
          <div>
            <CardTitle>新建设计</CardTitle>
            <CardDesc>越具体越好(年龄 / 性别 / 口音 / 情绪 / 应用场景)</CardDesc>
          </div>
          <Wand2 size={20} className="text-[var(--color-fg-muted)]" />
        </CardHeader>

        <input
          value={name}
          onChange={(e) => setName(e.target.value)}
          placeholder="音色名称(必填)"
          className="mb-3 w-full rounded-md border border-[var(--color-border)] bg-[var(--color-panel-2)] px-3 py-2 text-sm"
        />

        <textarea
          value={voicePrompt}
          onChange={(e) => setVoicePrompt(e.target.value)}
          rows={5}
          placeholder="例如:沉稳的中年男声,带轻微北京口音,适合纪录片旁白"
          className="w-full resize-y rounded-md border border-[var(--color-border)] bg-[var(--color-panel-2)] p-3 text-sm"
        />

        <div className="mt-2 flex flex-wrap gap-2">
          {SAMPLES.map((s, i) => (
            <button
              key={i}
              type="button"
              onClick={() => setVoicePrompt(s)}
              className="rounded-md border border-[var(--color-border)] bg-[var(--color-panel-2)] px-2 py-1 text-xs text-[var(--color-fg-muted)] hover:text-[var(--color-fg)]"
            >
              {s}
            </button>
          ))}
        </div>

        {error && <div className="mt-3 rounded-md bg-red-500/10 p-2 text-sm text-red-300">{error}</div>}

        <div className="mt-4 flex justify-end gap-2">
          <Button variant="outline" onClick={() => nav("/voices")}>取消</Button>
          <Button onClick={submit} disabled={submitting}>
            {submitting ? <Loader2 className="animate-spin" size={16} /> : null}
            生成
          </Button>
        </div>
      </Card>
    </div>
  );
}

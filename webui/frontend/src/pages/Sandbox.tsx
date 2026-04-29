import { useState } from "react";
import { Loader2, Send } from "lucide-react";
import { api } from "@/lib/api";
import { Button } from "@/components/ui/button";
import { Card, CardDesc, CardHeader, CardTitle } from "@/components/ui/card";

const MODELS = [
  "mimo-v2.5-pro",
  "mimo-v2.5",
  "mimo-v2-pro",
  "mimo-v2-flash",
];

export default function Sandbox() {
  const [model, setModel] = useState(MODELS[0]);
  const [prompt, setPrompt] = useState("用 80 个字介绍小米 MiMo 模型。");
  const [loading, setLoading] = useState(false);
  const [output, setOutput] = useState<string>("");
  const [error, setError] = useState<string>("");

  async function send() {
    setLoading(true);
    setError("");
    setOutput("");
    try {
      const resp = (await api.chat({
        messages: [{ role: "user", content: prompt }],
        model,
      })) as { choices?: { message?: { content?: string } }[] };
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
        <h1 className="text-2xl font-bold">聊天沙盒</h1>
        <p className="text-sm text-[var(--color-fg-muted)]">
          快速验证 MiMo Chat。多模态消息可在「图像 / 视频」页面单独测试。
        </p>
      </div>

      <Card>
        <CardHeader>
          <div>
            <CardTitle>请求</CardTitle>
            <CardDesc>选择模型并输入文本</CardDesc>
          </div>
          <select
            value={model}
            onChange={(e) => setModel(e.target.value)}
            className="rounded-md border border-[var(--color-border)] bg-[var(--color-panel-2)] px-2 py-1 text-sm"
          >
            {MODELS.map((m) => (
              <option key={m} value={m}>{m}</option>
            ))}
          </select>
        </CardHeader>
        <textarea
          value={prompt}
          onChange={(e) => setPrompt(e.target.value)}
          rows={5}
          className="w-full resize-y rounded-md border border-[var(--color-border)] bg-[var(--color-panel-2)] p-3 text-sm focus:outline-none focus:ring-1 focus:ring-[var(--color-accent)]"
          placeholder="输入对话内容…"
        />
        <div className="mt-3 flex justify-end">
          <Button onClick={send} disabled={loading || !prompt.trim()}>
            {loading ? <Loader2 className="animate-spin" size={16} /> : <Send size={16} />}
            发送
          </Button>
        </div>
      </Card>

      {(output || error) && (
        <Card>
          <CardHeader>
            <CardTitle>响应</CardTitle>
          </CardHeader>
          {error ? (
            <pre className="overflow-auto rounded-md bg-red-500/10 p-3 text-sm text-red-300">
              {error}
            </pre>
          ) : (
            <pre className="whitespace-pre-wrap text-sm">{output}</pre>
          )}
        </Card>
      )}
    </div>
  );
}

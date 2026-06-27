import { useState } from "react";
import { ChevronDown, ChevronRight, Loader2, Send } from "lucide-react";
import { api, type ChatResponse } from "@/lib/api";
import { Button } from "@/components/ui/button";
import { Card, CardDesc, CardHeader, CardTitle } from "@/components/ui/card";

const MODELS = ["mimo-v2.5-pro", "mimo-v2.5", "mimo-v2-pro", "mimo-v2-flash"];

export default function Sandbox() {
  const [model, setModel] = useState(MODELS[0]);
  const [prompt, setPrompt] = useState("用 80 个字介绍小米 MiMo 模型。");
  const [maxTokens, setMaxTokens] = useState(4096);
  const [showAdvanced, setShowAdvanced] = useState(false);
  const [temperature, setTemperature] = useState("");
  const [topP, setTopP] = useState("");
  const [loading, setLoading] = useState(false);
  const [resp, setResp] = useState<ChatResponse | null>(null);
  const [showReasoning, setShowReasoning] = useState(false);
  const [error, setError] = useState("");

  async function send() {
    setLoading(true);
    setError("");
    setResp(null);
    try {
      const r = await api.chat({
        messages: [{ role: "user", content: prompt }],
        model,
        max_tokens: maxTokens,
        temperature: temperature.trim() ? Number(temperature) : undefined,
        top_p: topP.trim() ? Number(topP) : undefined,
      });
      setResp(r);
    } catch (e) {
      setError(String(e));
    } finally {
      setLoading(false);
    }
  }

  const message = resp?.choices?.[0]?.message;
  const content = message?.content ?? "";
  const reasoning = message?.reasoning_content ?? "";
  const finishReason = resp?.choices?.[0]?.finish_reason;
  const usage = resp?.usage;
  // thinking 模型把 token 耗在思考上、正文为空的典型场景
  const emptyButThought =
    !content && (!!reasoning || finishReason === "length");

  return (
    <div className="space-y-6">
      <div>
        <h1 className="text-2xl font-bold">聊天沙盒</h1>
        <p className="text-sm text-[var(--color-fg-muted)]">
          快速验证 MiMo Chat。默认 v2.5 是 thinking 模型,回复可能包含思考过程;
          token 预算(max_tokens)不足时正文可能为空。多模态可在「图像 / 视频」页测试。
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
              <option key={m} value={m}>
                {m}
              </option>
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

        {/* 参数:max_tokens + 折叠的高级采样参数 */}
        <div className="mt-3 flex flex-wrap items-center gap-3">
          <label className="flex items-center gap-2 text-sm">
            <span className="text-[var(--color-fg-muted)]">max_tokens</span>
            <input
              type="number"
              min={256}
              max={32768}
              step={256}
              value={maxTokens}
              onChange={(e) => setMaxTokens(Number(e.target.value))}
              className="w-24 rounded-md border border-[var(--color-border)] bg-[var(--color-panel-2)] px-2 py-1 text-sm"
            />
          </label>
          <span className="text-xs text-[var(--color-fg-muted)]">
            thinking 模型建议 ≥ 2048,长回复调到 8192+
          </span>
          <button
            type="button"
            onClick={() => setShowAdvanced((v) => !v)}
            className="ml-auto flex items-center gap-1 text-xs text-[var(--color-fg-muted)] hover:text-[var(--color-fg)]"
          >
            {showAdvanced ? (
              <ChevronDown size={14} />
            ) : (
              <ChevronRight size={14} />
            )}
            高级参数
          </button>
        </div>
        {showAdvanced && (
          <div className="mt-2 flex flex-wrap gap-4">
            <label className="flex items-center gap-2 text-xs">
              <span className="text-[var(--color-fg-muted)]">temperature</span>
              <input
                type="number"
                step={0.1}
                min={0}
                max={2}
                value={temperature}
                onChange={(e) => setTemperature(e.target.value)}
                placeholder="默认"
                className="w-20 rounded border border-[var(--color-border)] bg-[var(--color-panel-2)] px-2 py-1"
              />
            </label>
            <label className="flex items-center gap-2 text-xs">
              <span className="text-[var(--color-fg-muted)]">top_p</span>
              <input
                type="number"
                step={0.05}
                min={0}
                max={1}
                value={topP}
                onChange={(e) => setTopP(e.target.value)}
                placeholder="默认"
                className="w-20 rounded border border-[var(--color-border)] bg-[var(--color-panel-2)] px-2 py-1"
              />
            </label>
          </div>
        )}

        <div className="mt-3 flex justify-end">
          <Button onClick={send} disabled={loading || !prompt.trim()}>
            {loading ? (
              <Loader2 className="animate-spin" size={16} />
            ) : (
              <Send size={16} />
            )}
            发送
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

      {resp && (
        <Card>
          <CardHeader>
            <CardTitle>响应</CardTitle>
            {usage && (
              <span className="text-xs text-[var(--color-fg-muted)]">
                token:{usage.prompt_tokens ?? "?"} 入 /{" "}
                {usage.completion_tokens ?? "?"} 出
                {usage.completion_tokens_details?.reasoning_tokens != null &&
                  ` · 思考 ${usage.completion_tokens_details.reasoning_tokens}`}
              </span>
            )}
          </CardHeader>

          {/* 思考过程(thinking 模型的 reasoning_content) */}
          {reasoning && (
            <div className="mb-3">
              <button
                type="button"
                onClick={() => setShowReasoning((v) => !v)}
                className="flex items-center gap-1 text-xs text-[var(--color-fg-muted)] hover:text-[var(--color-fg)]"
              >
                {showReasoning ? (
                  <ChevronDown size={14} />
                ) : (
                  <ChevronRight size={14} />
                )}
                思考过程({reasoning.length} 字)
              </button>
              {showReasoning && (
                <pre className="mt-2 max-h-64 overflow-auto whitespace-pre-wrap rounded-md border border-[var(--color-border)] bg-[var(--color-panel-2)] p-3 text-xs text-[var(--color-fg-muted)]">
                  {reasoning}
                </pre>
              )}
            </div>
          )}

          {/* 正文 */}
          {content ? (
            <pre className="whitespace-pre-wrap text-sm">{content}</pre>
          ) : emptyButThought ? (
            <div className="rounded-md bg-amber-500/10 p-3 text-sm text-amber-300">
              模型把 token 预算几乎都用在了思考上,正文为空
              {finishReason ? `(finish_reason=${finishReason})` : ""}。
              请调大上面的 max_tokens 后重试。
            </div>
          ) : (
            <pre className="whitespace-pre-wrap text-sm text-[var(--color-fg-muted)]">
              (无正文)
              {"\n"}
              {JSON.stringify(resp, null, 2)}
            </pre>
          )}
        </Card>
      )}
    </div>
  );
}

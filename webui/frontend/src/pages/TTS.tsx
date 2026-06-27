import { useEffect, useMemo, useRef, useState } from "react";
import { useQuery } from "@tanstack/react-query";
import {
  Clapperboard,
  Download,
  Eraser,
  Loader2,
  Play,
  RotateCcw,
  Sparkles,
  Trash2,
  Volume2,
} from "lucide-react";
import { api, type AudioFormat } from "@/lib/api";
import { Button } from "@/components/ui/button";
import { Card, CardDesc, CardHeader, CardTitle } from "@/components/ui/card";
import { Badge } from "@/components/ui/badge";
import { cn, formatDateTime, truncate } from "@/lib/utils";
import {
  aiRefine,
  clearHistory,
  clearText,
  type HistoryItem,
  runTts,
  setFormat,
  setInstructions,
  setMode,
  setRefineStyle,
  setSegMax,
  setText,
  setVoice,
  SOURCE_LABEL,
  ttsStore,
  undoRefine,
} from "./tts.store";

export default function TTS() {
  const st = ttsStore.use();
  const {
    mode,
    text,
    voice,
    format,
    segMax,
    refineStyle,
    instructions,
    single,
    batch,
    loading,
    refining,
    textBeforeRefine,
    refineNotice,
    error,
    playToken,
    history,
  } = st;

  const audioRef = useRef<HTMLAudioElement>(null);

  const voicesQ = useQuery({
    queryKey: ["voices"],
    queryFn: () => api.voices(),
  });
  const grouped = useMemo(() => {
    const all = voicesQ.data ?? [];
    return {
      default: all.filter((v) => v.source === "default"),
      clone: all.filter((v) => v.source === "clone"),
      design: all.filter((v) => v.source === "design"),
    };
  }, [voicesQ.data]);

  // 单段合成完成后自动播放:只在 playToken 真正增长时触发,
  // 切回页面组件重新挂载时(token 未变)不会误重播。
  const playedRef = useRef(playToken);
  useEffect(() => {
    if (playToken > playedRef.current) {
      playedRef.current = playToken;
      requestAnimationFrame(() =>
        audioRef.current?.play().catch(() => undefined),
      );
    }
  }, [playToken]);

  function fmtBytes(n: number) {
    if (n < 1024) return `${n} B`;
    if (n < 1024 * 1024) return `${(n / 1024).toFixed(1)} KB`;
    return `${(n / 1024 / 1024).toFixed(2)} MB`;
  }

  return (
    <div className="space-y-6">
      <div className="flex items-center justify-between">
        <div>
          <h1 className="text-2xl font-bold">文字转语音</h1>
          <p className="text-sm text-[var(--color-fg-muted)]">
            选一个音色,输入文本就能朗读。批量模式会按句号自动切段、依次合成。
          </p>
        </div>
        <div className="flex gap-2">
          <Button
            variant={mode === "single" ? "default" : "outline"}
            size="sm"
            onClick={() => setMode("single")}
          >
            单段
          </Button>
          <Button
            variant={mode === "batch" ? "default" : "outline"}
            size="sm"
            onClick={() => setMode("batch")}
          >
            批量切段
          </Button>
        </div>
      </div>

      <div className="grid grid-cols-1 gap-4 lg:grid-cols-[1fr_280px]">
        {/* 主输入区 */}
        <Card>
          <CardHeader>
            <div>
              <CardTitle>朗读文本</CardTitle>
              <CardDesc>
                {text.length} 字
                {mode === "batch" &&
                  ` · 预览约 ${Math.max(1, Math.ceil(text.length / segMax))} 段`}
              </CardDesc>
            </div>
            <div className="flex items-center gap-1">
              <Button
                variant="ghost"
                size="sm"
                onClick={() => {
                  if (text.length > 80 && !confirm("确定清空当前文本?")) return;
                  clearText();
                }}
                disabled={loading || refining || text.length === 0}
                title="一键清空文本"
              >
                <Eraser size={14} /> 清空
              </Button>
              <Volume2
                size={18}
                className="ml-1 text-[var(--color-fg-muted)]"
              />
            </div>
          </CardHeader>
          <textarea
            value={text}
            onChange={(e) => setText(e.target.value)}
            rows={mode === "batch" ? 12 : 6}
            className="w-full resize-y rounded-md border border-[var(--color-border)] bg-[var(--color-panel-2)] p-3 text-sm leading-relaxed focus:outline-none focus:ring-1 focus:ring-[var(--color-accent)]"
            placeholder="在这里输入要朗读的文本..."
          />

          {/* 朗读优化工具条 — 让 AI 把文字改得更适合朗读 */}
          <div className="mt-3 rounded-md border border-[var(--color-border)] bg-[var(--color-panel-2)] px-3 py-2.5">
            <div className="mb-2 flex items-center gap-2">
              <Sparkles size={14} className="text-[var(--color-accent)]" />
              <span className="text-sm font-medium text-[var(--color-fg)]">
                让朗读更自然(可选)
              </span>
              <span className="text-xs text-[var(--color-fg-muted)]">
                · 改写文字本身 · 数字念中文 · 英文缩写展开 · 自动补标点
              </span>
            </div>
            <div className="flex flex-wrap items-center gap-2">
              <input
                value={refineStyle}
                onChange={(e) => setRefineStyle(e.target.value)}
                placeholder="朗读场景(选填):新闻播报 / 儿童故事 / 纪录片旁白 …"
                className="flex-1 min-w-[200px] rounded border border-[var(--color-border)] bg-[var(--color-panel)] px-2 py-1.5 text-xs"
              />
              <Button
                variant="outline"
                size="sm"
                onClick={aiRefine}
                disabled={refining || loading || !text.trim()}
                title="用 mimo-v2.5-pro 模型把当前文本改得更适合 TTS 朗读"
              >
                {refining ? (
                  <Loader2 className="animate-spin" size={14} />
                ) : (
                  <Sparkles size={14} />
                )}
                {refining ? "AI 优化中…" : "AI 优化文本"}
              </Button>
              {textBeforeRefine !== null && (
                <Button
                  variant="ghost"
                  size="sm"
                  onClick={undoRefine}
                  title="还原成优化前的原文"
                >
                  <RotateCcw size={14} /> 还原原文
                </Button>
              )}
            </div>
            {!refineNotice && textBeforeRefine === null && (
              <div className="mt-1.5 text-xs text-[var(--color-fg-muted)]">
                适合:含数字/英文缩写、书面语重、长文。不需要时直接合成即可。
              </div>
            )}
          </div>
          {refineNotice && (
            <div className="mt-2 text-xs text-emerald-400">
              ✓ {refineNotice}
            </div>
          )}

          {/* 导演模式 — v2.5 自然语言风格指令,只调声音不改文字 */}
          <div className="mt-3 rounded-md border border-[var(--color-border)] bg-[var(--color-panel-2)] px-3 py-2.5">
            <div className="mb-2 flex items-center gap-2">
              <Clapperboard size={14} className="text-[var(--color-accent)]" />
              <span className="text-sm font-medium text-[var(--color-fg)]">
                导演模式(可选)
              </span>
              <span className="text-xs text-[var(--color-fg-muted)]">
                · v2.5 自然语言指令 · 不改文字,只调声音的语气 / 情绪 / 语速 /
                方言
              </span>
            </div>
            <textarea
              value={instructions}
              onChange={(e) => setInstructions(e.target.value)}
              rows={2}
              placeholder="例如:用沉稳的纪录片旁白语气,语速稍慢,句间留一点停顿;或:活泼一点,像在跟朋友聊天"
              className="w-full resize-y rounded border border-[var(--color-border)] bg-[var(--color-panel)] px-2 py-1.5 text-xs"
            />
          </div>

          <div className="mt-3 flex items-center justify-between">
            <div className="text-xs text-[var(--color-fg-muted)]">
              {mode === "batch"
                ? "提示:按句号 / 问号 / 感叹号 / 换行切段,顺序合成"
                : "提示:单段模式适合短文本(≤ 200 字),长文请切到批量"}
            </div>
            <Button
              onClick={runTts}
              disabled={loading || refining || !text.trim()}
            >
              {loading ? (
                <Loader2 className="animate-spin" size={16} />
              ) : (
                <Play size={16} />
              )}
              {loading ? "合成中" : "合成"}
            </Button>
          </div>
        </Card>

        {/* 侧栏:音色 + 格式 */}
        <Card>
          <CardHeader>
            <CardTitle>音色与格式</CardTitle>
          </CardHeader>
          <div className="space-y-3">
            <div>
              <label className="mb-1 block text-xs text-[var(--color-fg-muted)]">
                音色
              </label>
              <select
                value={voice}
                onChange={(e) => setVoice(e.target.value)}
                className="w-full rounded-md border border-[var(--color-border)] bg-[var(--color-panel-2)] px-2 py-1.5 text-sm"
              >
                {grouped.default.length > 0 && (
                  <optgroup label="预置">
                    {grouped.default.map((v) => (
                      <option key={v.voice_id} value={v.voice_id}>
                        {v.name} — {truncate(v.description ?? "", 14)}
                      </option>
                    ))}
                  </optgroup>
                )}
                {grouped.clone.length > 0 && (
                  <optgroup label="克隆">
                    {grouped.clone.map((v) => (
                      <option key={v.voice_id} value={v.voice_id}>
                        {v.name}
                      </option>
                    ))}
                  </optgroup>
                )}
                {grouped.design.length > 0 && (
                  <optgroup label="设计">
                    {grouped.design.map((v) => (
                      <option key={v.voice_id} value={v.voice_id}>
                        {v.name}
                      </option>
                    ))}
                  </optgroup>
                )}
              </select>
            </div>

            <div>
              <label className="mb-1 block text-xs text-[var(--color-fg-muted)]">
                音频格式
              </label>
              <select
                value={format}
                onChange={(e) => setFormat(e.target.value as AudioFormat)}
                className="w-full rounded-md border border-[var(--color-border)] bg-[var(--color-panel-2)] px-2 py-1.5 text-sm"
              >
                <option value="wav">wav · 无损,体积大</option>
                <option value="mp3">mp3 · 体积约为 wav 的 1/5</option>
              </select>
            </div>

            {mode === "batch" && (
              <div>
                <label className="mb-1 block text-xs text-[var(--color-fg-muted)]">
                  分段字数上限({segMax})
                </label>
                <input
                  type="range"
                  min={20}
                  max={300}
                  value={segMax}
                  onChange={(e) => setSegMax(Number(e.target.value))}
                  className="w-full accent-[var(--color-accent)]"
                />
                <div className="mt-1 flex justify-between text-xs text-[var(--color-fg-muted)]">
                  <span>20</span>
                  <span>120</span>
                  <span>300</span>
                </div>
              </div>
            )}

            <div className="rounded-md border border-[var(--color-border)] bg-[var(--color-panel-2)] p-2 text-xs text-[var(--color-fg-muted)]">
              <div className="mb-1 font-medium text-[var(--color-fg)]">
                说明
              </div>
              v2.5 用「导演模式」(自然语言 instructions)控制语气 / 情绪 / 语速 /
              方言;旧的 speed 已废弃不下发,style 仅作简易回退。详见
              docs/api-research.md。
            </div>
          </div>
        </Card>
      </div>

      {/* 错误 */}
      {error && (
        <Card>
          <pre className="overflow-auto rounded-md bg-red-500/10 p-3 text-sm text-red-300">
            {error}
          </pre>
        </Card>
      )}

      {/* 单段结果 */}
      {single && (
        <Card>
          <CardHeader>
            <div>
              <CardTitle>合成结果</CardTitle>
              <CardDesc>
                {SOURCE_LABEL[single.source]} · {single.voice} · {single.model}{" "}
                · {fmtBytes(single.bytes)}
              </CardDesc>
            </div>
            <a
              href={single.audio_url}
              download
              className="inline-flex items-center gap-1 text-xs text-[var(--color-fg-muted)] hover:text-[var(--color-fg)]"
            >
              <Download size={14} /> 下载
            </a>
          </CardHeader>
          <audio
            ref={audioRef}
            controls
            src={single.audio_url}
            className="w-full"
          />
        </Card>
      )}

      {/* 批量结果 */}
      {batch && (
        <Card>
          <CardHeader>
            <div>
              <CardTitle>批量合成</CardTitle>
              <CardDesc>
                {batch.items.length} / {batch.total} 段已就绪
              </CardDesc>
            </div>
            {loading && (
              <Loader2
                className="animate-spin text-[var(--color-fg-muted)]"
                size={16}
              />
            )}
          </CardHeader>
          <div className="space-y-2">
            {batch.items.map((seg) => (
              <div
                key={seg.index}
                className="rounded-md border border-[var(--color-border)] bg-[var(--color-panel-2)] p-3"
              >
                <div className="mb-2 flex items-center justify-between text-xs text-[var(--color-fg-muted)]">
                  <span>
                    段 {seg.index + 1}/{seg.total} · {fmtBytes(seg.bytes)}
                  </span>
                  <a
                    href={seg.audio_url}
                    download
                    className="hover:text-[var(--color-fg)]"
                  >
                    <Download size={14} />
                  </a>
                </div>
                <div className="mb-2 text-sm">{seg.text}</div>
                <audio controls src={seg.audio_url} className="w-full" />
              </div>
            ))}
            {batch.total > 0 && batch.items.length < batch.total && (
              <div className="flex items-center justify-center gap-2 rounded-md border border-dashed border-[var(--color-border)] py-4 text-sm text-[var(--color-fg-muted)]">
                <Loader2 className="animate-spin" size={14} />
                合成下一段…
              </div>
            )}
          </div>
        </Card>
      )}

      {/* 历史 */}
      <Card>
        <CardHeader>
          <div>
            <CardTitle>本会话历史</CardTitle>
            <CardDesc>最多 20 条 · localStorage 持久化</CardDesc>
          </div>
          {history.length > 0 && (
            <Button variant="ghost" size="sm" onClick={clearHistory}>
              <Trash2 size={14} /> 清空
            </Button>
          )}
        </CardHeader>
        {history.length === 0 ? (
          <div className="py-6 text-center text-sm text-[var(--color-fg-muted)]">
            还没有合成记录,点上面的"合成"开始第一次。
          </div>
        ) : (
          <div className="space-y-2">
            {history.map((h) => (
              <HistoryRow key={h.id} item={h} fmtBytes={fmtBytes} />
            ))}
          </div>
        )}
      </Card>
    </div>
  );
}

function HistoryRow({
  item,
  fmtBytes,
}: {
  item: HistoryItem;
  fmtBytes: (n: number) => string;
}) {
  const [open, setOpen] = useState(false);
  const segCount = item.segments.length;
  return (
    <div className="rounded-md border border-[var(--color-border)] bg-[var(--color-panel-2)]">
      <button
        type="button"
        onClick={() => setOpen((v) => !v)}
        className={cn(
          "flex w-full items-center justify-between px-3 py-2 text-left text-sm",
          "hover:bg-[var(--color-panel)]",
        )}
      >
        <div className="flex items-center gap-2">
          <Badge variant="muted">
            {item.mode === "single" ? "单段" : `批量 ${segCount} 段`}
          </Badge>
          <Badge>
            {SOURCE_LABEL[item.source]} · {item.voice}
          </Badge>
          <span className="text-[var(--color-fg-muted)]">
            {truncate(item.text, 40)}
          </span>
        </div>
        <div className="text-xs text-[var(--color-fg-muted)]">
          {formatDateTime(item.ts)} · {fmtBytes(item.total_bytes)}
        </div>
      </button>
      {open && (
        <div className="space-y-2 border-t border-[var(--color-border)] p-3">
          {item.segments.map((s, i) => (
            <div
              key={i}
              className="rounded border border-[var(--color-border)] p-2"
            >
              <div className="mb-1 text-xs text-[var(--color-fg-muted)]">
                段 {i + 1} · {fmtBytes(s.bytes)}
              </div>
              <div className="mb-2 text-sm">{s.text}</div>
              <audio controls src={s.audio_url} className="w-full" />
            </div>
          ))}
        </div>
      )}
    </div>
  );
}

import { Download, Loader2, Scissors, Upload, Users } from "lucide-react";
import { type DiarizeSegment } from "@/lib/api";
import { CopyButton } from "@/components/CopyButton";
import { Button } from "@/components/ui/button";
import { Card, CardDesc, CardHeader, CardTitle } from "@/components/ui/card";
import { formatClock } from "@/lib/utils";
import { asrStore, pickAsrFile, setAsrMode, startAsr } from "./asr.store";

const SPEAKER_COLORS = [
  "#60a5fa",
  "#f472b6",
  "#34d399",
  "#fbbf24",
  "#a78bfa",
  "#fb923c",
  "#22d3ee",
  "#f87171",
];

function speakerColor(spk: number): string {
  return SPEAKER_COLORS[spk % SPEAKER_COLORS.length];
}
function speakerLabel(spk: number): string {
  return `发言人 ${spk + 1}`;
}

// ---- 导出格式 ----
function toTxt(segs: DiarizeSegment[]): string {
  return segs
    .map(
      (s) =>
        `[${speakerLabel(s.speaker)} ${formatClock(s.start)}-${formatClock(s.end)}] ${s.text}`,
    )
    .join("\n\n");
}
function srtTime(sec: number): string {
  const ms = Math.floor((sec % 1) * 1000);
  const s = Math.floor(sec);
  const hh = String(Math.floor(s / 3600)).padStart(2, "0");
  const mm = String(Math.floor((s % 3600) / 60)).padStart(2, "0");
  const ss = String(s % 60).padStart(2, "0");
  return `${hh}:${mm}:${ss},${String(ms).padStart(3, "0")}`;
}
function toSrt(segs: DiarizeSegment[]): string {
  return (
    segs
      .map(
        (s, i) =>
          `${i + 1}\n${srtTime(s.start)} --> ${srtTime(s.end)}\n[${speakerLabel(s.speaker)}] ${s.text}`,
      )
      .join("\n\n") + "\n"
  );
}
function download(content: string, filename: string, mime: string) {
  const blob = new Blob([content], { type: mime });
  const url = URL.createObjectURL(blob);
  const a = document.createElement("a");
  a.href = url;
  a.download = filename;
  document.body.appendChild(a);
  a.click();
  a.remove();
  URL.revokeObjectURL(url);
}

export default function ASR() {
  const st = asrStore.use();

  function saveText(text: string) {
    const stamp = new Date().toISOString().slice(0, 19).replace(/[:T]/g, "-");
    const base = st.file?.name?.replace(/\.[^.]+$/, "") || "转写";
    download(text, `${base}_${stamp}.txt`, "text/plain;charset=utf-8");
  }

  const fileBase = st.file?.name?.replace(/\.[^.]+$/, "") || "转写";

  return (
    <div className="space-y-6">
      <div className="flex items-start justify-between">
        <div>
          <h1 className="text-2xl font-bold">语音转写</h1>
          <p className="text-sm text-[var(--color-fg-muted)]">
            mimo-v2.5-asr 转写;长音频可分段,多人对话可分离说话人(本地
            sherpa-onnx)
          </p>
        </div>
        <div className="flex shrink-0 gap-2">
          <Button
            variant={st.mode === "single" ? "default" : "outline"}
            size="sm"
            onClick={() => setAsrMode("single")}
          >
            单段
          </Button>
          <Button
            variant={st.mode === "chunked" ? "default" : "outline"}
            size="sm"
            onClick={() => setAsrMode("chunked")}
          >
            长音频分段
          </Button>
          <Button
            variant={st.mode === "diarize" ? "default" : "outline"}
            size="sm"
            onClick={() => setAsrMode("diarize")}
          >
            说话人分离
          </Button>
        </div>
      </div>

      <Card>
        <CardHeader>
          <CardTitle>上传音频</CardTitle>
          <CardDesc>WAV / MP3。单段 ≤ 10 MB;更长用分段或说话人分离</CardDesc>
        </CardHeader>

        <label className="mb-3 flex cursor-pointer items-center gap-3 rounded-md border border-dashed border-[var(--color-border)] bg-[var(--color-panel-2)] px-4 py-6 text-sm">
          <Upload size={18} />
          <span>
            {st.file
              ? `${st.file.name} · ${(st.file.size / 1024 / 1024).toFixed(1)} MB`
              : "点击选择音频"}
          </span>
          <input
            type="file"
            accept="audio/wav,audio/mpeg,audio/mp3,.wav,.mp3"
            className="hidden"
            onChange={(e) => pickAsrFile(e.target.files?.[0] ?? null)}
          />
        </label>

        <div>
          <label className="mb-1 block text-xs text-[var(--color-fg-muted)]">
            语种(指定可提升准确率)
          </label>
          <select
            value={st.language}
            onChange={(e) => asrStore.set({ language: e.target.value })}
            className="w-full rounded-md border border-[var(--color-border)] bg-[var(--color-panel-2)] px-3 py-2 text-sm md:w-1/2"
          >
            <option value="auto">自动检测(含方言)</option>
            <option value="zh">中文</option>
            <option value="en">英文</option>
          </select>
        </div>

        {/* 分段选项 */}
        {st.mode === "chunked" && (
          <div className="mt-3 rounded-md border border-[var(--color-border)] bg-[var(--color-panel-2)] px-3 py-2.5">
            <div className="mb-1 flex items-center gap-2">
              <Scissors size={14} className="text-[var(--color-accent)]" />
              <span className="text-sm font-medium">长音频分段转写</span>
            </div>
            <div className="mb-2 text-xs text-[var(--color-fg-muted)]">
              按时间切段、逐段识别再合并,适合会议、播客等长录音。
            </div>
            <div className="flex items-center gap-2">
              <span className="text-xs text-[var(--color-fg-muted)]">
                每段时长(秒):
              </span>
              <input
                type="range"
                min={30}
                max={240}
                step={10}
                value={st.segmentSeconds}
                onChange={(e) =>
                  asrStore.set({ segmentSeconds: Number(e.target.value) })
                }
                className="flex-1 accent-[var(--color-accent)]"
              />
              <span className="font-mono text-xs">{st.segmentSeconds}s</span>
            </div>
          </div>
        )}

        {/* 说话人分离选项 */}
        {st.mode === "diarize" && (
          <div className="mt-3 rounded-md border border-[var(--color-border)] bg-[var(--color-panel-2)] px-3 py-2.5">
            <div className="mb-1 flex items-center gap-2">
              <Users size={14} className="text-[var(--color-accent)]" />
              <span className="text-sm font-medium">说话人分离</span>
            </div>
            <div className="mb-2 text-xs text-[var(--color-fg-muted)]">
              本地 sherpa-onnx 区分"谁在何时说",再逐段用 MiMo
              转写;同时得到说话人标注与时间戳。
              声音差异越大越准,已知人数时建议手动指定。
            </div>
            <div className="flex flex-wrap items-center gap-3">
              <label className="flex items-center gap-1.5 text-xs">
                <input
                  type="radio"
                  checked={st.speakerMode === "auto"}
                  onChange={() => asrStore.set({ speakerMode: "auto" })}
                />
                自动检测人数
              </label>
              <label className="flex items-center gap-1.5 text-xs">
                <input
                  type="radio"
                  checked={st.speakerMode === "manual"}
                  onChange={() => asrStore.set({ speakerMode: "manual" })}
                />
                指定人数
              </label>
              {st.speakerMode === "manual" && (
                <input
                  type="number"
                  min={1}
                  max={10}
                  value={st.numSpeakers}
                  onChange={(e) =>
                    asrStore.set({ numSpeakers: Number(e.target.value) })
                  }
                  className="w-16 rounded border border-[var(--color-border)] bg-[var(--color-panel)] px-2 py-1 text-xs"
                />
              )}
            </div>
          </div>
        )}

        <div className="mt-4 flex justify-end">
          <Button onClick={startAsr} disabled={st.running || !st.file}>
            {st.running ? <Loader2 className="animate-spin" size={16} /> : null}
            {st.running
              ? "处理中…"
              : st.mode === "single"
                ? "转写"
                : st.mode === "chunked"
                  ? "分段转写"
                  : "分离并转写"}
          </Button>
        </div>
      </Card>

      {st.error && (
        <Card>
          <pre className="rounded-md bg-red-500/10 p-3 text-sm text-red-300">
            {st.error}
          </pre>
        </Card>
      )}

      {/* 分段进度 */}
      {st.chunk && (
        <Card>
          <CardHeader>
            <CardTitle>分段进度</CardTitle>
            <CardDesc>
              {st.chunk.total > 0
                ? `${st.chunk.total} 段 · 总时长 ${formatClock(st.chunk.duration)} · 已完成 ${st.chunk.segments.length}/${st.chunk.total}`
                : "正在切段…"}
            </CardDesc>
          </CardHeader>
          <div className="space-y-1">
            {st.chunk.segments.map((s) => (
              <div
                key={s.index}
                className="flex gap-3 rounded-md border border-[var(--color-border)] bg-[var(--color-panel-2)] px-3 py-1.5 text-sm"
              >
                <span className="shrink-0 font-mono text-xs text-[var(--color-fg-muted)]">
                  {formatClock(s.start)}-{formatClock(s.end)}
                </span>
                <span className="flex-1">{s.text || "(本段无内容)"}</span>
              </div>
            ))}
            {st.running && st.chunk.segments.length < st.chunk.total && (
              <div className="flex items-center gap-2 px-1 pt-1 text-xs text-[var(--color-fg-muted)]">
                <Loader2 className="animate-spin" size={12} /> 识别中…
              </div>
            )}
          </div>
        </Card>
      )}

      {/* 说话人分离结果 */}
      {st.diar && (
        <Card>
          <CardHeader>
            <div>
              <CardTitle>说话人分离结果</CardTitle>
              <CardDesc>
                {st.diar.statusMsg ||
                  `${st.diar.numSpeakers} 个说话人 · ${st.diar.segments.length} 段 · 总时长 ${formatClock(st.diar.duration)}`}
              </CardDesc>
            </div>
            {st.diar.segments.length > 0 && !st.running && (
              <div className="flex flex-wrap gap-2">
                <Button
                  variant="outline"
                  size="sm"
                  onClick={() =>
                    download(
                      toTxt(st.diar!.segments),
                      `${fileBase}_diarized.txt`,
                      "text/plain;charset=utf-8",
                    )
                  }
                >
                  <Download size={14} /> .txt
                </Button>
                <Button
                  variant="outline"
                  size="sm"
                  onClick={() =>
                    download(
                      toSrt(st.diar!.segments),
                      `${fileBase}.srt`,
                      "text/plain;charset=utf-8",
                    )
                  }
                >
                  <Download size={14} /> .srt
                </Button>
                <Button
                  variant="outline"
                  size="sm"
                  onClick={() =>
                    download(
                      JSON.stringify(
                        {
                          num_speakers: st.diar!.numSpeakers,
                          duration: st.diar!.duration,
                          segments: st.diar!.segments,
                        },
                        null,
                        2,
                      ),
                      `${fileBase}_diarized.json`,
                      "application/json",
                    )
                  }
                >
                  <Download size={14} /> .json
                </Button>
              </div>
            )}
          </CardHeader>

          {st.running && st.diar.segments.length === 0 && (
            <div className="flex items-center gap-2 text-sm text-[var(--color-fg-muted)]">
              <Loader2 className="animate-spin" size={14} />
              {st.diar.statusMsg || "处理中…"}
            </div>
          )}

          <div className="space-y-1.5">
            {st.diar.segments.map((s) => (
              <div
                key={s.index}
                className="flex gap-3 rounded-md border border-[var(--color-border)] bg-[var(--color-panel-2)] px-3 py-2 text-sm"
              >
                <span
                  className="shrink-0 rounded px-1.5 py-0.5 text-xs font-medium text-black"
                  style={{ backgroundColor: speakerColor(s.speaker) }}
                >
                  {speakerLabel(s.speaker)}
                </span>
                <span className="shrink-0 self-center font-mono text-xs text-[var(--color-fg-muted)]">
                  {formatClock(s.start)}-{formatClock(s.end)}
                </span>
                <span className="flex-1 self-center">
                  {s.text || "(本段无内容)"}
                </span>
              </div>
            ))}
          </div>
        </Card>
      )}

      {/* 转写结果(单段 / 分段合并) */}
      {st.resp && (
        <Card>
          <CardHeader>
            <div>
              <CardTitle>{st.chunk ? "合并结果" : "转写结果"}</CardTitle>
              <CardDesc>
                {st.resp.model}
                {st.resp.language ? ` · ${st.resp.language}` : ""}
                {st.resp.text ? ` · ${st.resp.text.length} 字` : ""}
              </CardDesc>
            </div>
            <div className="flex gap-2">
              <CopyButton
                text={st.resp.text}
                label="复制"
                variant="outline"
                duration={1500}
                onError={() =>
                  asrStore.set({ error: "复制失败,请手动选择文本复制" })
                }
              />
              <Button
                variant="outline"
                size="sm"
                onClick={() => saveText(st.resp!.text)}
                disabled={!st.resp.text}
                title="保存为 .txt 文件"
              >
                <Download size={14} /> 保存
              </Button>
            </div>
          </CardHeader>
          <div className="whitespace-pre-wrap rounded-md bg-[var(--color-panel-2)] p-3 text-sm leading-relaxed">
            {st.resp.text || "(未识别到内容)"}
          </div>
        </Card>
      )}
    </div>
  );
}

import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { Trash2 } from "lucide-react";
import { Link } from "react-router-dom";
import { api, type VoiceRecord } from "@/lib/api";
import { Button } from "@/components/ui/button";
import { Card, CardDesc, CardHeader, CardTitle } from "@/components/ui/card";
import { Badge } from "@/components/ui/badge";
import { formatDateTime, truncate } from "@/lib/utils";

const SOURCE_LABEL: Record<VoiceRecord["source"], string> = {
  default: "默认",
  clone: "克隆",
  design: "设计",
};

const STATUS_VARIANT = {
  ready: "success",
  pending: "warning",
  failed: "danger",
} as const;

/**
 * 音色试听音频 URL。后端 GET /api/tts/audio/<name> 会在 tts/ 与 voice_refs/ 下 rglob 查找。
 * - design:reference_path 即试听音频(voice_refs/<voice_id>.wav),取其文件名直接播放。
 * - clone:试听样本由后端约定命名 <voice_id>_sample.wav,落在 tts/<日期>/(见 api/voice_clone.py)。
 * - default(预置):无独立试听样本,返回 null。
 */
function previewUrl(v: VoiceRecord): string | null {
  if (v.source === "design" && v.reference_path) {
    const name = v.reference_path.split("/").pop();
    return name ? `/api/tts/audio/${name}` : null;
  }
  // clone 的试听样本仅在创建成功(ready)时才写盘,pending/failed 不渲染避免 404
  if (v.source === "clone" && v.status === "ready") {
    return `/api/tts/audio/${v.voice_id}_sample.wav`;
  }
  return null;
}

export default function Voices() {
  const qc = useQueryClient();
  const list = useQuery({ queryKey: ["voices"], queryFn: () => api.voices() });
  const del = useMutation({
    mutationFn: (id: string) => api.deleteVoice(id),
    onSuccess: () => qc.invalidateQueries({ queryKey: ["voices"] }),
  });

  return (
    <div className="space-y-6">
      <div className="flex items-center justify-between">
        <div>
          <h1 className="text-2xl font-bold">音色库</h1>
          <p className="text-sm text-[var(--color-fg-muted)]">
            本地 SQLite 持久化,可用 voice_id 在 mimo.tts / mimo.chat 中引用
          </p>
        </div>
        <div className="flex gap-2">
          <Button asChild variant="outline" size="sm">
            <Link to="/voices/clone">+ 克隆</Link>
          </Button>
          <Button asChild size="sm">
            <Link to="/voices/design">+ 设计</Link>
          </Button>
        </div>
      </div>

      <Card>
        <CardHeader>
          <div>
            <CardTitle>已注册音色</CardTitle>
            <CardDesc>{list.data?.length ?? 0} 条记录</CardDesc>
          </div>
        </CardHeader>
        {list.isLoading && (
          <div className="text-sm text-[var(--color-fg-muted)]">加载中…</div>
        )}
        {list.data?.length === 0 && (
          <div className="rounded-md border border-dashed border-[var(--color-border)] p-8 text-center text-sm text-[var(--color-fg-muted)]">
            还没有任何音色,从右上角创建第一个克隆或设计音色。
          </div>
        )}
        <div className="space-y-2">
          {list.data?.map((v) => {
            const preview = previewUrl(v);
            // design 音色的描述存在 voice_prompt;description 为空时回退展示它
            const desc =
              v.description ?? (v.source === "design" ? v.voice_prompt : null);
            return (
              <div
                key={v.voice_id}
                className="rounded-md border border-[var(--color-border)] bg-[var(--color-panel-2)] px-3 py-2"
              >
                <div className="flex items-center justify-between">
                  <div>
                    <div className="flex items-center gap-2">
                      <span className="font-medium">{v.name}</span>
                      <Badge>{SOURCE_LABEL[v.source]}</Badge>
                      <Badge variant={STATUS_VARIANT[v.status]}>
                        {v.status}
                      </Badge>
                    </div>
                    <div className="mt-0.5 text-xs text-[var(--color-fg-muted)]">
                      <code className="mr-2">{v.voice_id}</code>·{" "}
                      {formatDateTime(v.created_at)}
                      {desc && ` · ${truncate(desc, 40)}`}
                    </div>
                  </div>
                  <Button
                    variant="ghost"
                    size="icon"
                    onClick={() => del.mutate(v.voice_id)}
                    disabled={del.isPending}
                    title="删除"
                  >
                    <Trash2 size={16} className="text-red-400" />
                  </Button>
                </div>
                {preview && (
                  <audio
                    controls
                    preload="none"
                    src={preview}
                    className="mt-2 h-8 w-full"
                  />
                )}
              </div>
            );
          })}
        </div>
      </Card>
    </div>
  );
}

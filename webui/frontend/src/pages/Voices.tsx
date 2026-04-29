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
          <Button asChild variant="outline" size="sm"><Link to="/voices/clone">+ 克隆</Link></Button>
          <Button asChild size="sm"><Link to="/voices/design">+ 设计</Link></Button>
        </div>
      </div>

      <Card>
        <CardHeader>
          <div>
            <CardTitle>已注册音色</CardTitle>
            <CardDesc>{list.data?.length ?? 0} 条记录</CardDesc>
          </div>
        </CardHeader>
        {list.isLoading && <div className="text-sm text-[var(--color-fg-muted)]">加载中…</div>}
        {list.data?.length === 0 && (
          <div className="rounded-md border border-dashed border-[var(--color-border)] p-8 text-center text-sm text-[var(--color-fg-muted)]">
            还没有任何音色,从右上角创建第一个克隆或设计音色。
          </div>
        )}
        <div className="space-y-2">
          {list.data?.map((v) => (
            <div
              key={v.voice_id}
              className="flex items-center justify-between rounded-md border border-[var(--color-border)] bg-[var(--color-panel-2)] px-3 py-2"
            >
              <div>
                <div className="flex items-center gap-2">
                  <span className="font-medium">{v.name}</span>
                  <Badge>{SOURCE_LABEL[v.source]}</Badge>
                  <Badge variant={STATUS_VARIANT[v.status]}>{v.status}</Badge>
                </div>
                <div className="mt-0.5 text-xs text-[var(--color-fg-muted)]">
                  <code className="mr-2">{v.voice_id}</code>· {formatDateTime(v.created_at)}
                  {v.description && ` · ${truncate(v.description, 40)}`}
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
          ))}
        </div>
      </Card>
    </div>
  );
}

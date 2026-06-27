import { useQuery } from "@tanstack/react-query";
import {
  CheckCircle2,
  AlertTriangle,
  XCircle,
  Activity,
  Cpu,
  Network,
  Mic2,
} from "lucide-react";
import { api } from "@/lib/api";
import { Card, CardDesc, CardHeader, CardTitle } from "@/components/ui/card";
import { Badge } from "@/components/ui/badge";

function StatusIcon({ ok }: { ok: boolean | null }) {
  if (ok === true)
    return <CheckCircle2 className="text-emerald-400" size={18} />;
  if (ok === false) return <XCircle className="text-red-400" size={18} />;
  return <AlertTriangle className="text-amber-400" size={18} />;
}

export default function Dashboard() {
  const health = useQuery({
    queryKey: ["health"],
    queryFn: api.health,
    refetchInterval: 30_000,
  });
  const usage = useQuery({
    queryKey: ["usage", 24],
    queryFn: () => api.usage(24),
  });

  return (
    <div className="space-y-6">
      <div>
        <h1 className="text-2xl font-bold">概览</h1>
        <p className="text-sm text-[var(--color-fg-muted)]">
          mimo-mcp 健康状态与最近 24 小时本地调用聚合
        </p>
      </div>

      <div className="grid grid-cols-1 gap-4 md:grid-cols-3">
        <Card>
          <CardHeader>
            <div>
              <CardTitle>API Key</CardTitle>
              <CardDesc>
                {health.data?.api_key_configured
                  ? "已配置"
                  : "未配置(检查 .env)"}
              </CardDesc>
            </div>
            <Cpu size={20} className="text-[var(--color-fg-muted)]" />
          </CardHeader>
          <div className="flex items-center gap-2">
            <StatusIcon ok={health.data?.api_key_configured ?? null} />
            <span className="text-sm text-[var(--color-fg-muted)]">
              {health.data?.base_url}
            </span>
          </div>
        </Card>

        <Card>
          <CardHeader>
            <div>
              <CardTitle>网络 / 鉴权</CardTitle>
              <CardDesc>base_url 可达且 key 合法</CardDesc>
            </div>
            <Network size={20} className="text-[var(--color-fg-muted)]" />
          </CardHeader>
          <div className="flex items-center gap-3 text-sm">
            <span className="flex items-center gap-1">
              <StatusIcon ok={health.data?.base_url_reachable ?? null} />
              <span>可达</span>
            </span>
            <span className="flex items-center gap-1">
              <StatusIcon ok={health.data?.auth_valid ?? null} />
              <span>鉴权</span>
            </span>
          </div>
        </Card>

        <Card>
          <CardHeader>
            <div>
              <CardTitle>云端 ASR</CardTitle>
              <CardDesc>mimo-v2.5-asr 云端可用性</CardDesc>
            </div>
            <Mic2 size={20} className="text-[var(--color-fg-muted)]" />
          </CardHeader>
          <div className="flex items-center gap-2">
            <StatusIcon ok={health.data?.asr_cloud_available ?? null} />
            <span className="text-sm">
              {health.data?.asr_cloud_available
                ? "可用"
                : "不可用(检查套餐 / MIMO_BASE_URL)"}
            </span>
          </div>
        </Card>
      </div>

      <Card>
        <CardHeader>
          <div>
            <CardTitle>最近 24 小时调用</CardTitle>
            <CardDesc>来自本地 audit_log,MCP + Web 合计</CardDesc>
          </div>
          <Activity size={20} className="text-[var(--color-fg-muted)]" />
        </CardHeader>
        <div className="grid grid-cols-2 gap-4 md:grid-cols-4">
          <Stat label="总调用" value={usage.data?.calls ?? 0} />
          <Stat
            label="错误"
            value={usage.data?.errors ?? 0}
            accent={(usage.data?.errors ?? 0) > 0 ? "danger" : "default"}
          />
          <Stat label="输入 token" value={usage.data?.input_tokens ?? 0} />
          <Stat label="输出 token" value={usage.data?.output_tokens ?? 0} />
        </div>
        {usage.data && Object.keys(usage.data.by_tool).length > 0 && (
          <div className="mt-4 flex flex-wrap gap-2">
            {Object.entries(usage.data.by_tool).map(([tool, n]) => (
              <Badge key={tool}>
                {tool} · {n}
              </Badge>
            ))}
          </div>
        )}
      </Card>

      {(health.data?.notes?.length ?? 0) > 0 && (
        <Card>
          <CardHeader>
            <CardTitle>提示</CardTitle>
          </CardHeader>
          <ul className="space-y-1 text-sm text-[var(--color-fg-muted)]">
            {health.data?.notes.map((n, i) => <li key={i}>· {n}</li>)}
          </ul>
        </Card>
      )}
    </div>
  );
}

function Stat({
  label,
  value,
  accent = "default",
}: {
  label: string;
  value: number;
  accent?: "default" | "danger";
}) {
  return (
    <div className="rounded-md border border-[var(--color-border)] bg-[var(--color-panel-2)] p-3">
      <div className="text-xs text-[var(--color-fg-muted)]">{label}</div>
      <div
        className={
          accent === "danger"
            ? "mt-1 text-2xl font-semibold text-red-400"
            : "mt-1 text-2xl font-semibold"
        }
      >
        {value.toLocaleString()}
      </div>
    </div>
  );
}

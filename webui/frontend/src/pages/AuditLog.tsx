import { useQuery } from "@tanstack/react-query";
import { api } from "@/lib/api";
import { Card, CardDesc, CardHeader, CardTitle } from "@/components/ui/card";
import { Badge } from "@/components/ui/badge";
import { formatDateTime, truncate } from "@/lib/utils";

export default function AuditLog() {
  const q = useQuery({
    queryKey: ["audit"],
    queryFn: () => api.audit(200),
    refetchInterval: 5_000,
  });

  return (
    <div className="space-y-6">
      <div>
        <h1 className="text-2xl font-bold">审计日志</h1>
        <p className="text-sm text-[var(--color-fg-muted)]">
          MCP + Web 全部调用,5 秒自动刷新,最多显示最近 200 条
        </p>
      </div>

      <Card>
        <CardHeader>
          <div>
            <CardTitle>最近调用</CardTitle>
            <CardDesc>{q.data?.length ?? 0} 条</CardDesc>
          </div>
        </CardHeader>
        <div className="overflow-x-auto">
          <table className="w-full text-sm">
            <thead>
              <tr className="text-left text-xs text-[var(--color-fg-muted)]">
                <th className="px-2 py-1.5">时间</th>
                <th className="px-2 py-1.5">通道</th>
                <th className="px-2 py-1.5">工具</th>
                <th className="px-2 py-1.5">模型</th>
                <th className="px-2 py-1.5">状态</th>
                <th className="px-2 py-1.5">耗时</th>
                <th className="px-2 py-1.5">错误</th>
              </tr>
            </thead>
            <tbody>
              {q.data?.map((row) => (
                <tr key={row.id} className="border-t border-[var(--color-border)]">
                  <td className="px-2 py-1.5 text-xs text-[var(--color-fg-muted)]">{formatDateTime(row.ts)}</td>
                  <td className="px-2 py-1.5"><Badge variant="muted">{row.channel}</Badge></td>
                  <td className="px-2 py-1.5"><code>{row.tool}</code></td>
                  <td className="px-2 py-1.5 text-xs">{row.model ?? "-"}</td>
                  <td className="px-2 py-1.5">
                    <Badge variant={row.status === "ok" ? "success" : "danger"}>
                      {row.status}
                    </Badge>
                  </td>
                  <td className="px-2 py-1.5 text-xs">
                    {row.latency_ms ? `${row.latency_ms} ms` : "-"}
                  </td>
                  <td className="px-2 py-1.5 text-xs text-red-300">
                    {row.error ? truncate(row.error, 60) : ""}
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
          {(q.data?.length ?? 0) === 0 && (
            <div className="py-8 text-center text-sm text-[var(--color-fg-muted)]">
              暂无调用记录,先去聊天沙盒或音色页发起一次请求。
            </div>
          )}
        </div>
      </Card>
    </div>
  );
}

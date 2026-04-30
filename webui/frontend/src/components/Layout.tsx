import { NavLink, Outlet } from "react-router-dom";
import {
  Activity,
  AudioLines,
  FileText,
  ImagePlay,
  LayoutDashboard,
  Mic,
  Sparkles,
  Volume2,
  Wand2,
} from "lucide-react";
import { cn } from "@/lib/utils";

const NAV = [
  { to: "/", icon: LayoutDashboard, label: "概览" },
  { to: "/sandbox", icon: Sparkles, label: "聊天沙盒" },
  { to: "/tts", icon: Volume2, label: "文字转语音" },
  { to: "/vision", icon: ImagePlay, label: "图像 / 视频" },
  { to: "/voices", icon: AudioLines, label: "音色库" },
  { to: "/voices/clone", icon: Mic, label: "声音克隆" },
  { to: "/voices/design", icon: Wand2, label: "声音设计" },
  { to: "/asr", icon: FileText, label: "语音转写" },
  { to: "/audit", icon: Activity, label: "审计日志" },
];

export default function Layout() {
  return (
    <div className="flex h-full">
      <aside className="w-56 shrink-0 border-r border-[var(--color-border)] bg-[var(--color-panel)] p-3">
        <div className="mb-6 px-2 py-3">
          <div className="text-lg font-bold tracking-tight">mimo-mcp</div>
          <div className="text-xs text-[var(--color-fg-muted)]">
            本地控制台 · v0.1
          </div>
        </div>
        <nav className="flex flex-col gap-1">
          {NAV.map(({ to, icon: Icon, label }) => (
            <NavLink
              key={to}
              to={to}
              end={to === "/"}
              className={({ isActive }) =>
                cn(
                  "flex items-center gap-2 rounded-md px-3 py-2 text-sm transition-colors",
                  isActive
                    ? "bg-[var(--color-panel-2)] text-[var(--color-fg)]"
                    : "text-[var(--color-fg-muted)] hover:bg-[var(--color-panel-2)] hover:text-[var(--color-fg)]",
                )
              }
            >
              <Icon size={16} />
              <span>{label}</span>
            </NavLink>
          ))}
        </nav>
      </aside>
      <main className="flex-1 overflow-y-auto scrollbar-thin">
        <div className="mx-auto max-w-6xl p-6">
          <Outlet />
        </div>
      </main>
    </div>
  );
}

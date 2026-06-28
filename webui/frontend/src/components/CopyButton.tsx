import { type ComponentProps, useState } from "react";
import { Check, Copy } from "lucide-react";
import { Button } from "@/components/ui/button";

/**
 * 通用复制按钮。点击后写入剪贴板,短暂回显「已复制」状态。
 * 兼容老浏览器:clipboard API 失败时用 textarea + execCommand 兜底;
 * 两条路径都失败时调用可选的 onError(供页面做错误提示)。
 *
 * variant / duration 默认沿用最初引入处(Vision)的取值;ASR 等页面可显式覆盖
 * 以保持各自原有的外观与回显时长。
 */
export function CopyButton({
  text,
  label = "复制",
  variant = "ghost",
  duration = 2000,
  onError,
}: {
  text: string;
  label?: string;
  variant?: ComponentProps<typeof Button>["variant"];
  duration?: number;
  onError?: () => void;
}) {
  const [copied, setCopied] = useState(false);

  function flash() {
    setCopied(true);
    setTimeout(() => setCopied(false), duration);
  }

  async function handle() {
    if (!text) return;
    try {
      await navigator.clipboard.writeText(text);
      flash();
    } catch {
      // 兼容老浏览器:用临时 textarea + execCommand
      const ta = document.createElement("textarea");
      ta.value = text;
      ta.style.position = "fixed";
      ta.style.opacity = "0";
      document.body.appendChild(ta);
      ta.select();
      try {
        document.execCommand("copy");
        flash();
      } catch {
        onError?.();
      } finally {
        document.body.removeChild(ta);
      }
    }
  }

  return (
    <Button
      variant={variant}
      size="sm"
      onClick={handle}
      disabled={!text}
      title={copied ? "已复制到剪贴板" : "复制全部文本到剪贴板"}
    >
      {copied ? (
        <Check size={14} className="text-emerald-400" />
      ) : (
        <Copy size={14} />
      )}
      {copied ? "已复制" : label}
    </Button>
  );
}

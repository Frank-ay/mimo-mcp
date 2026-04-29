import * as React from "react";
import { cn } from "@/lib/utils";

type Variant = "default" | "success" | "warning" | "danger" | "muted";

const variantClass: Record<Variant, string> = {
  default: "bg-[var(--color-panel-2)] text-[var(--color-fg)]",
  success: "bg-emerald-600/15 text-emerald-400",
  warning: "bg-amber-500/15 text-amber-400",
  danger: "bg-red-500/15 text-red-400",
  muted: "bg-[var(--color-panel-2)] text-[var(--color-fg-muted)]",
};

export function Badge({
  className,
  variant = "default",
  ...props
}: React.HTMLAttributes<HTMLSpanElement> & { variant?: Variant }) {
  return (
    <span
      className={cn(
        "inline-flex items-center rounded-md border border-[var(--color-border)] px-2 py-0.5 text-xs font-medium",
        variantClass[variant],
        className,
      )}
      {...props}
    />
  );
}

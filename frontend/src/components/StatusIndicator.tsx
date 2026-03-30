// src/components/StatusIndicator.tsx
// Status dot component: "ok" (green), "degraded" (amber), "unavailable" (red).
// Zero hardcoded colors — all via Tailwind design tokens.

import { Badge } from "@/components/ui/badge";
import { cn } from "@/lib/utils";

interface StatusIndicatorProps {
  status: "ok" | "degraded" | "unavailable";
  label?: string;
}

const dotColor: Record<StatusIndicatorProps["status"], string> = {
  ok: "bg-success",
  degraded: "bg-warning",
  unavailable: "bg-destructive",
};

export function StatusIndicator({ status, label }: StatusIndicatorProps) {
  return (
    <Badge variant="outline" className="gap-1.5">
      <span
        className={cn("size-2 rounded-full", dotColor[status])}
        aria-hidden="true"
      />
      {label ?? status}
      <span className="sr-only">{status}</span>
    </Badge>
  );
}

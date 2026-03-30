// src/components/ConfidenceBadge.tsx
// Visual badge for classification confidence level.
// "high" → green border + text, "low" → amber border + text.
// Zero hardcoded colors — all via Tailwind design tokens.

import { Badge } from "@/components/ui/badge";
import { cn } from "@/lib/utils";

interface ConfidenceBadgeProps {
  confidence: "high" | "low";
}

export function ConfidenceBadge({ confidence }: ConfidenceBadgeProps) {
  const isHigh = confidence === "high";

  return (
    <Badge
      variant="outline"
      className={cn(
        "gap-1.5",
        isHigh
          ? "border-success text-success"
          : "border-warning text-warning",
      )}
    >
      <span
        className={cn(
          "size-1.5 rounded-full",
          isHigh ? "bg-success" : "bg-warning",
        )}
        aria-hidden="true"
      />
      {confidence}
    </Badge>
  );
}

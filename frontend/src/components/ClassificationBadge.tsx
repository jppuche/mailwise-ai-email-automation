// src/components/ClassificationBadge.tsx
// Displays action + type classification slugs as pill badges.
// Zero hardcoded colors — all via Tailwind design tokens.
import type { ClassificationSummary } from "@/types/generated/api";
import { Badge } from "@/components/ui/badge";

interface ClassificationBadgeProps {
  classification: ClassificationSummary | null;
}

export function ClassificationBadge({ classification }: ClassificationBadgeProps) {
  if (!classification) {
    return (
      <Badge variant="outline" className="text-muted-foreground">
        Unclassified
      </Badge>
    );
  }

  return (
    <span className="inline-flex items-center gap-1.5 flex-wrap">
      <Badge variant="default">{classification.action}</Badge>
      <span className="text-muted-foreground text-xs" aria-hidden="true">
        /
      </span>
      <Badge variant="secondary">{classification.type}</Badge>
      {classification.is_fallback && (
        <span
          className="text-xs text-muted-foreground"
          title="Fallback classification"
        >
          fb
        </span>
      )}
    </span>
  );
}

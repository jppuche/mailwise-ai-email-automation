// src/components/ClassificationBadge.tsx
// Displays action + type classification slugs as pill badges.
// Zero hardcoded colors — all via CSS custom properties.
import type { ClassificationSummary } from "@/types/generated/api";

interface ClassificationBadgeProps {
  classification: ClassificationSummary | null;
}

export function ClassificationBadge({ classification }: ClassificationBadgeProps) {
  if (!classification) {
    return <span className="classification-badge classification-badge--empty">—</span>;
  }

  return (
    <span className="classification-badge">
      <span className="classification-badge__action">{classification.action}</span>
      <span className="classification-badge__separator">/</span>
      <span className="classification-badge__type">{classification.type}</span>
      {classification.is_fallback && (
        <span className="classification-badge__fallback" title="Fallback classification">
          fb
        </span>
      )}
    </span>
  );
}

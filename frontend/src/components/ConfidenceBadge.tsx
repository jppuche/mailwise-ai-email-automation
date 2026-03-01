// src/components/ConfidenceBadge.tsx
// Visual badge for classification confidence level.
// "high" → var(--color-success) green, "low" → var(--color-warning) amber.
// Zero hardcoded colors — all via CSS custom properties (variables.css).

interface ConfidenceBadgeProps {
  confidence: "high" | "low";
}

export function ConfidenceBadge({ confidence }: ConfidenceBadgeProps) {
  const modifier = confidence === "high" ? "confidence-badge--high" : "confidence-badge--low";

  return (
    <span className={`confidence-badge ${modifier}`}>
      {confidence === "high" ? "high" : "low"}
    </span>
  );
}

// src/components/StatCard.tsx
// Metric card with label, value, optional delta indicator.
// Zero hardcoded colors — all via CSS custom properties.

interface StatCardProps {
  label: string;
  value: number | string;
  delta?: number;
  isLoading?: boolean;
}

export function StatCard({ label, value, delta, isLoading }: StatCardProps) {
  if (isLoading) {
    return (
      <div className="stat-card stat-card--loading" aria-busy="true">
        <div className="stat-card__skeleton stat-card__skeleton--label" />
        <div className="stat-card__skeleton stat-card__skeleton--value" />
      </div>
    );
  }

  const hasDelta = typeof delta === "number";
  const deltaPositive = hasDelta && delta > 0;
  const deltaNegative = hasDelta && delta < 0;

  return (
    <div className="stat-card">
      <span className="stat-card__label">{label}</span>
      <span className="stat-card__value">{value}</span>
      {hasDelta && (
        <span
          className={`stat-card__delta${deltaPositive ? " stat-card__delta--positive" : ""}${deltaNegative ? " stat-card__delta--negative" : ""}`}
          aria-label={`Change: ${delta > 0 ? "+" : ""}${delta}`}
        >
          {deltaPositive && (
            <span className="stat-card__delta-arrow" aria-hidden="true">
              &#9650;
            </span>
          )}
          {deltaNegative && (
            <span className="stat-card__delta-arrow" aria-hidden="true">
              &#9660;
            </span>
          )}
          {delta > 0 ? "+" : ""}{delta}
        </span>
      )}
    </div>
  );
}

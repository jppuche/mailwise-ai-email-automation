// src/components/StatusIndicator.tsx
// Status dot component: "ok" (green), "degraded" (yellow), "unavailable" (red).
// Zero hardcoded colors — all via CSS custom properties.

interface StatusIndicatorProps {
  status: "ok" | "degraded" | "unavailable";
  label?: string;
}

export function StatusIndicator({ status, label }: StatusIndicatorProps) {
  return (
    <span className="status-indicator">
      <span
        className={`status-indicator__dot status-indicator__dot--${status}`}
        aria-hidden="true"
      />
      {label && (
        <span className="status-indicator__label">{label}</span>
      )}
      <span className="sr-only">{status}</span>
    </span>
  );
}

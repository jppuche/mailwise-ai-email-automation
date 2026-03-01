// src/components/LogRow.tsx
// Expandable log entry row.
// No stack_trace field — LogEntry has context: Record<string, string> (handoff delta #6).
import { useState } from "react";
import type { LogEntry } from "@/types/generated/api";

interface LogRowProps {
  entry: LogEntry;
}

const TRUNCATE_LENGTH = 120;

function formatTimestamp(iso: string): string {
  try {
    return new Intl.DateTimeFormat(undefined, {
      month: "short",
      day: "numeric",
      hour: "2-digit",
      minute: "2-digit",
      second: "2-digit",
    }).format(new Date(iso));
  } catch {
    return iso;
  }
}

function levelModifier(level: string): string {
  const l = level.toUpperCase();
  if (l === "ERROR") return "error";
  if (l === "WARNING") return "warning";
  return "info";
}

export function LogRow({ entry }: LogRowProps) {
  const [expanded, setExpanded] = useState(false);

  const modifier = levelModifier(entry.level);
  const truncated =
    entry.message.length > TRUNCATE_LENGTH
      ? entry.message.slice(0, TRUNCATE_LENGTH) + "…"
      : entry.message;
  const contextEntries = Object.entries(entry.context);

  return (
    <li
      className={`log-row${expanded ? " log-row--expanded" : ""}`}
      aria-expanded={expanded}
    >
      <button
        type="button"
        className="log-row__summary"
        onClick={() => setExpanded((v) => !v)}
        aria-label={`${expanded ? "Collapse" : "Expand"} log entry`}
      >
        <time className="log-row__timestamp" dateTime={entry.timestamp}>
          {formatTimestamp(entry.timestamp)}
        </time>
        <span
          className={`log-row__level log-row__level--${modifier}`}
          aria-label={`Level: ${entry.level}`}
        >
          {entry.level}
        </span>
        <span className="log-row__source">{entry.source}</span>
        <span className="log-row__message">
          {expanded ? entry.message : truncated}
        </span>
        <span className="log-row__expand-icon" aria-hidden="true">
          {expanded ? "▲" : "▼"}
        </span>
      </button>

      {expanded && (
        <div className="log-row__detail">
          {entry.email_id && (
            <p className="log-row__email-id">
              <span className="log-row__detail-key">email_id:</span>{" "}
              <span className="log-row__detail-value log-row__detail-value--mono">
                {entry.email_id}
              </span>
            </p>
          )}
          {contextEntries.length > 0 && (
            <dl className="log-row__context">
              {contextEntries.map(([key, val]) => (
                <div key={key} className="log-row__context-row">
                  <dt className="log-row__detail-key">{key}</dt>
                  <dd className="log-row__detail-value log-row__detail-value--mono">{val}</dd>
                </div>
              ))}
            </dl>
          )}
          {contextEntries.length === 0 && !entry.email_id && (
            <p className="log-row__no-context">No additional context.</p>
          )}
        </div>
      )}
    </li>
  );
}

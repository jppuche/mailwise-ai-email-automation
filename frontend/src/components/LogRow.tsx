// src/components/LogRow.tsx
// Expandable log entry row.
// No stack_trace field — LogEntry has context: Record<string, string> (handoff delta #6).
import { useState } from "react";
import { ChevronDown, ChevronUp } from "lucide-react";
import type { LogEntry } from "@/types/generated/api";
import { Badge } from "@/components/ui/badge";
import { cn } from "@/lib/utils";

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

function levelVariant(
  level: string,
): "destructive" | "outline" | "secondary" {
  const l = level.toUpperCase();
  if (l === "ERROR") return "destructive";
  if (l === "WARNING") return "outline";
  return "secondary";
}

function levelClass(level: string): string {
  const l = level.toUpperCase();
  if (l === "WARNING") return "border-warning text-warning";
  return "";
}

export function LogRow({ entry }: LogRowProps) {
  const [expanded, setExpanded] = useState(false);

  const truncated =
    entry.message.length > TRUNCATE_LENGTH
      ? entry.message.slice(0, TRUNCATE_LENGTH) + "…"
      : entry.message;
  const contextEntries = Object.entries(entry.context);

  return (
    <li
      className={cn(
        "border-b border-border last:border-0",
        expanded && "bg-muted/40",
      )}
      aria-expanded={expanded}
    >
      <button
        type="button"
        className="w-full flex items-center gap-3 px-3 py-2.5 text-left hover:bg-muted/50 transition-colors"
        onClick={() => setExpanded((v) => !v)}
        aria-label={`${expanded ? "Collapse" : "Expand"} log entry`}
      >
        <time
          className="text-xs text-muted-foreground tabular-nums shrink-0 w-32"
          dateTime={entry.timestamp}
        >
          {formatTimestamp(entry.timestamp)}
        </time>

        <Badge
          variant={levelVariant(entry.level)}
          className={cn("shrink-0 uppercase text-xs", levelClass(entry.level))}
          aria-label={`Level: ${entry.level}`}
        >
          {entry.level}
        </Badge>

        <span className="text-xs font-mono text-muted-foreground shrink-0 w-28 truncate">
          {entry.source}
        </span>

        <span className="text-sm text-foreground flex-1 truncate">
          {expanded ? entry.message : truncated}
        </span>

        <span aria-hidden="true" className="shrink-0 text-muted-foreground">
          {expanded ? (
            <ChevronUp className="size-4" />
          ) : (
            <ChevronDown className="size-4" />
          )}
        </span>
      </button>

      {expanded && (
        <div className="px-4 pb-3 pt-1 space-y-2 border-t border-border/50">
          {entry.email_id && (
            <p className="text-xs">
              <span className="text-muted-foreground font-medium">
                email_id:
              </span>{" "}
              <span className="font-mono text-sm text-foreground">
                {entry.email_id}
              </span>
            </p>
          )}

          {contextEntries.length > 0 && (
            <dl className="space-y-1">
              {contextEntries.map(([key, val]) => (
                <div key={key} className="flex gap-2 text-xs">
                  <dt className="text-muted-foreground font-medium shrink-0">
                    {key}
                  </dt>
                  <dd className="font-mono text-sm text-foreground break-all">
                    {val}
                  </dd>
                </div>
              ))}
            </dl>
          )}

          {contextEntries.length === 0 && !entry.email_id && (
            <p className="text-xs text-muted-foreground">
              No additional context.
            </p>
          )}
        </div>
      )}
    </li>
  );
}

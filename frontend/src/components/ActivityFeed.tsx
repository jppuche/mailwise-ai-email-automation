// src/components/ActivityFeed.tsx
// Recent events list for the Overview page.
// ActivityEvent is a local frontend type — no backend model for it (handoff delta #7).

import type { ComponentProps } from "react";
import { Badge } from "@/components/ui/badge";
import { Skeleton } from "@/components/ui/skeleton";

/** Map email state to a semantic badge variant. */
function stateBadgeVariant(
  state: string,
): ComponentProps<typeof Badge>["variant"] {
  if (state.startsWith("failed_")) return "destructive";
  if (state === "archived") return "secondary";
  if (state === "draft_sent" || state === "routed") return "default";
  return "outline";
}

export interface ActivityEvent {
  type: string;
  timestamp: string;
  description: string;
  email_id?: string;
}

interface ActivityFeedProps {
  events: ActivityEvent[];
  isLoading?: boolean;
}

function formatTimestamp(iso: string): string {
  try {
    return new Intl.DateTimeFormat(undefined, {
      month: "short",
      day: "numeric",
      hour: "2-digit",
      minute: "2-digit",
    }).format(new Date(iso));
  } catch {
    return iso;
  }
}

export function ActivityFeed({ events, isLoading }: ActivityFeedProps) {
  if (isLoading) {
    return (
      <div className="space-y-3" aria-busy="true">
        {Array.from({ length: 5 }).map((_, i) => (
          <div key={i} className="flex items-start gap-3 pl-4 border-l-2 border-border">
            <Skeleton className="h-5 w-16 shrink-0" />
            <Skeleton className="h-4 flex-1" />
            <Skeleton className="h-4 w-20 shrink-0" />
          </div>
        ))}
      </div>
    );
  }

  if (events.length === 0) {
    return (
      <p className="text-sm text-muted-foreground py-4 text-center">
        No recent activity.
      </p>
    );
  }

  return (
    <ul className="space-y-3">
      {events.map((event, index) => (
        <li
          key={event.email_id ? `${event.email_id}-${index}` : index}
          className="flex flex-wrap items-start gap-x-3 gap-y-1 pl-4 border-l-2 border-primary/30 py-1"
        >
          <Badge variant={stateBadgeVariant(event.type)} className="shrink-0 text-xs">
            {event.type.replace(/_/g, " ")}
          </Badge>
          <span className="text-sm text-foreground flex-1 min-w-0 leading-snug">
            {event.description}
          </span>
          <time
            className="text-xs text-muted-foreground shrink-0 tabular-nums sm:ml-0 ml-auto"
            dateTime={event.timestamp}
          >
            {formatTimestamp(event.timestamp)}
          </time>
        </li>
      ))}
    </ul>
  );
}

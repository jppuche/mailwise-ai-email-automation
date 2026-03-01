// src/components/ActivityFeed.tsx
// Recent events list for the Overview page.
// ActivityEvent is a local frontend type — no backend model for it (handoff delta #7).

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
      <div className="activity-feed activity-feed--loading" aria-busy="true">
        {Array.from({ length: 5 }).map((_, i) => (
          <div key={i} className="activity-feed__skeleton" />
        ))}
      </div>
    );
  }

  if (events.length === 0) {
    return (
      <div className="activity-feed activity-feed--empty">
        <p className="activity-feed__empty-text">No recent activity.</p>
      </div>
    );
  }

  return (
    <ul className="activity-feed">
      {events.map((event, index) => (
        <li
          key={event.email_id ? `${event.email_id}-${index}` : index}
          className="activity-feed__item"
        >
          <span className="activity-feed__badge">{event.type}</span>
          <span className="activity-feed__description">{event.description}</span>
          <time
            className="activity-feed__timestamp"
            dateTime={event.timestamp}
          >
            {formatTimestamp(event.timestamp)}
          </time>
        </li>
      ))}
    </ul>
  );
}

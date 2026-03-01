/** Health endpoint polling interval (ms) — used by useHealth hook */
export const HEALTH_POLL_INTERVAL_MS = 30_000;

/** Max items shown in the Overview activity feed */
export const ACTIVITY_FEED_LIMIT = 20;

/** Default date preset for analytics / overview date ranges */
export const DEFAULT_DATE_PRESET = "30d" as const;

/** Default page size for system logs (offset/limit pagination) */
export const LOGS_DEFAULT_LIMIT = 50;

/** Maximum log entries per request (server-enforced) */
export const LOGS_MAX_LIMIT = 200;

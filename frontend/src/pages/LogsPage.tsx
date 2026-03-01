// src/pages/LogsPage.tsx
// Route: /logs (admin only)
// System log viewer with filters and offset/limit pagination.
import { useState } from "react";
import { useLogs } from "@/hooks/useLogs";
import { LogRow } from "@/components/LogRow";
import { LOGS_DEFAULT_LIMIT } from "@/utils/constants";

const LOG_LEVELS = ["", "INFO", "WARNING", "ERROR"] as const;

export default function LogsPage() {
  const [level, setLevel] = useState("");
  const [source, setSource] = useState("");
  const [since, setSince] = useState("");
  const [until, setUntil] = useState("");
  const [offset, setOffset] = useState(0);

  const limit = LOGS_DEFAULT_LIMIT;

  const { data, isLoading, error } = useLogs({
    level: level || undefined,
    source: source || undefined,
    since: since || undefined,
    until: until || undefined,
    limit,
    offset,
  });

  const total = data?.total ?? 0;
  const totalPages = Math.ceil(total / limit);
  const currentPage = Math.floor(offset / limit) + 1;

  function handleLevelChange(e: React.ChangeEvent<HTMLSelectElement>) {
    setLevel(e.target.value);
    setOffset(0);
  }

  function handleSourceChange(e: React.ChangeEvent<HTMLInputElement>) {
    setSource(e.target.value);
    setOffset(0);
  }

  function handleSinceChange(e: React.ChangeEvent<HTMLInputElement>) {
    setSince(e.target.value);
    setOffset(0);
  }

  function handleUntilChange(e: React.ChangeEvent<HTMLInputElement>) {
    setUntil(e.target.value);
    setOffset(0);
  }

  function handlePrev() {
    setOffset((prev) => Math.max(0, prev - limit));
  }

  function handleNext() {
    setOffset((prev) => prev + limit);
  }

  return (
    <div className="logs-page">
      <h1 className="logs-page__title">System Logs</h1>

      {/* ── Filters ── */}
      <div className="logs-page__filters">
        <div className="form-group">
          <label className="form-label" htmlFor="logs-level">Level</label>
          <select
            id="logs-level"
            className="form-input logs-page__select"
            value={level}
            onChange={handleLevelChange}
          >
            {LOG_LEVELS.map((l) => (
              <option key={l} value={l}>
                {l || "All levels"}
              </option>
            ))}
          </select>
        </div>

        <div className="form-group">
          <label className="form-label" htmlFor="logs-source">Source</label>
          <input
            id="logs-source"
            type="text"
            className="form-input"
            value={source}
            onChange={handleSourceChange}
            placeholder="Filter by source module"
          />
        </div>

        <div className="form-group">
          <label className="form-label" htmlFor="logs-since">Since</label>
          <input
            id="logs-since"
            type="datetime-local"
            className="form-input"
            value={since}
            onChange={handleSinceChange}
          />
        </div>

        <div className="form-group">
          <label className="form-label" htmlFor="logs-until">Until</label>
          <input
            id="logs-until"
            type="datetime-local"
            className="form-input"
            value={until}
            onChange={handleUntilChange}
          />
        </div>
      </div>

      {error && (
        <div className="logs-page__error" role="alert">
          Failed to load logs: {error.message}
        </div>
      )}

      {isLoading && (
        <div className="logs-page__loading" aria-busy="true">
          Loading logs...
        </div>
      )}

      {!isLoading && data && (
        <>
          <p className="logs-page__count">
            {total === 0
              ? "No log entries found."
              : `${total} log ${total === 1 ? "entry" : "entries"} found`}
          </p>

          {data.items.length > 0 && (
            <ul className="logs-page__list">
              {data.items.map((entry) => (
                <LogRow key={entry.id} entry={entry} />
              ))}
            </ul>
          )}

          {/* ── Pagination ── */}
          {totalPages > 1 && (
            <div className="logs-page__pagination">
              <button
                type="button"
                className="btn btn--secondary"
                onClick={handlePrev}
                disabled={offset === 0}
              >
                Previous
              </button>
              <span className="logs-page__page-indicator">
                Page {currentPage} of {totalPages}
              </span>
              <button
                type="button"
                className="btn btn--secondary"
                onClick={handleNext}
                disabled={offset + limit >= total}
              >
                Next
              </button>
            </div>
          )}
        </>
      )}
    </div>
  );
}

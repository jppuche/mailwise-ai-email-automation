// src/pages/LogsPage.tsx
// Route: /logs (admin only)
// System log viewer with filters and offset/limit pagination.
import { useState } from "react";
import { useLogs } from "@/hooks/useLogs";
import { LogRow } from "@/components/LogRow";
import { LOGS_DEFAULT_LIMIT } from "@/utils/constants";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { Card, CardContent } from "@/components/ui/card";
import { Alert, AlertDescription } from "@/components/ui/alert";
import { Skeleton } from "@/components/ui/skeleton";
import { cn } from "@/lib/utils";

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
    <div className="space-y-6 animate-in fade-in slide-in-from-bottom-2 duration-300 fill-mode-both">
      <h1 className="text-2xl font-semibold tracking-tight">System Logs</h1>

      {/* ── Filters ── */}
      <Card className="p-4">
        <div className="flex flex-wrap items-end gap-4">
          <div className="flex flex-col gap-1.5">
            <Label htmlFor="logs-level">Level</Label>
            <select
              id="logs-level"
              value={level}
              onChange={handleLevelChange}
              className={cn(
                "flex h-9 w-44 rounded-md border border-input bg-transparent px-3 py-1 text-sm shadow-sm",
                "focus:outline-none focus:ring-1 focus:ring-ring",
              )}
            >
              {LOG_LEVELS.map((l) => (
                <option key={l} value={l}>
                  {l || "All levels"}
                </option>
              ))}
            </select>
          </div>

          <div className="flex flex-col gap-1.5">
            <Label htmlFor="logs-source">Source</Label>
            <Input
              id="logs-source"
              type="text"
              value={source}
              onChange={handleSourceChange}
              placeholder="Filter by source module"
              className="w-56"
            />
          </div>

          <div className="flex flex-col gap-1.5">
            <Label htmlFor="logs-since">Since</Label>
            <Input
              id="logs-since"
              type="datetime-local"
              value={since}
              onChange={handleSinceChange}
              className="w-52"
            />
          </div>

          <div className="flex flex-col gap-1.5">
            <Label htmlFor="logs-until">Until</Label>
            <Input
              id="logs-until"
              type="datetime-local"
              value={until}
              onChange={handleUntilChange}
              className="w-52"
            />
          </div>
        </div>
      </Card>

      {error && (
        <Alert variant="destructive" role="alert">
          <AlertDescription>Failed to load logs: {error.message}</AlertDescription>
        </Alert>
      )}

      {isLoading && (
        <div className="space-y-2" aria-busy="true">
          <Skeleton className="h-12 w-full" />
          <Skeleton className="h-12 w-full" />
          <Skeleton className="h-12 w-full" />
          <Skeleton className="h-12 w-full" />
          <Skeleton className="h-12 w-full" />
        </div>
      )}

      {!isLoading && data && (
        <>
          <p className="text-sm text-muted-foreground">
            {total === 0
              ? "No log entries found."
              : `${total} log ${total === 1 ? "entry" : "entries"} found`}
          </p>

          {data.items.length > 0 && (
            <Card>
              <CardContent className="p-0">
                <ul className="divide-y divide-border list-none p-0 m-0">
                  {data.items.map((entry) => (
                    <LogRow key={entry.id} entry={entry} />
                  ))}
                </ul>
              </CardContent>
            </Card>
          )}

          {/* ── Pagination ── */}
          {totalPages > 1 && (
            <div className="flex items-center justify-between">
              <Button
                type="button"
                variant="outline"
                size="sm"
                onClick={handlePrev}
                disabled={offset === 0}
              >
                Previous
              </Button>
              <span className="text-sm text-muted-foreground">
                Page {currentPage} of {totalPages}
              </span>
              <Button
                type="button"
                variant="outline"
                size="sm"
                onClick={handleNext}
                disabled={offset + limit >= total}
              >
                Next
              </Button>
            </div>
          )}
        </>
      )}
    </div>
  );
}

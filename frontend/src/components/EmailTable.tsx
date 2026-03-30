// src/components/EmailTable.tsx
// Paginated table for displaying a list of EmailListItem records.
// Supports row selection (multi-select via checkbox), click-through to detail, pagination.
// Zero hardcoded colors — all via CSS custom properties.
import type { EmailListItem } from "@/types/generated/api";
import { ClassificationBadge } from "./ClassificationBadge";
import { ConfidenceBadge } from "./ConfidenceBadge";
import { Button } from "@/components/ui/button";
import { Badge } from "@/components/ui/badge";
import { Skeleton } from "@/components/ui/skeleton";
import {
  Table,
  TableHeader,
  TableBody,
  TableHead,
  TableRow,
  TableCell,
} from "@/components/ui/table";
import { cn } from "@/lib/utils";

interface EmailTableProps {
  emails: EmailListItem[];
  total: number;
  page: number;
  pageSize: number;
  pages: number;
  isLoading: boolean;
  selectedIds: Set<string>;
  onSelectIds: (ids: Set<string>) => void;
  onPageChange: (page: number) => void;
  onRowClick: (emailId: string) => void;
}

/** Format an ISO datetime string to a locale-aware short representation. */
function formatDate(iso: string): string {
  try {
    return new Date(iso).toLocaleString(undefined, {
      year: "numeric",
      month: "short",
      day: "numeric",
      hour: "2-digit",
      minute: "2-digit",
    });
  } catch {
    return iso;
  }
}

/** Map an EmailState value to a Badge variant. */
function stateBadgeVariant(
  state: string
): "default" | "secondary" | "destructive" | "outline" {
  if (state.startsWith("failed_")) return "destructive";
  if (state === "archived") return "secondary";
  if (state === "draft_sent" || state === "routed") return "default";
  return "outline";
}

export function EmailTable(props: EmailTableProps) {
  const {
    emails,
    total,
    page,
    pages,
    isLoading,
    selectedIds,
    onSelectIds,
    onPageChange,
    onRowClick,
  } = props;
  const allVisibleSelected =
    emails.length > 0 && emails.every((e) => selectedIds.has(e.id));
  const someSelected = emails.some((e) => selectedIds.has(e.id));

  function handleSelectAll(e: React.ChangeEvent<HTMLInputElement>) {
    if (e.target.checked) {
      onSelectIds(new Set(emails.map((email) => email.id)));
    } else {
      onSelectIds(new Set());
    }
  }

  function handleRowSelect(
    e: React.ChangeEvent<HTMLInputElement>,
    emailId: string
  ) {
    e.stopPropagation();
    const next = new Set(selectedIds);
    if (e.target.checked) {
      next.add(emailId);
    } else {
      next.delete(emailId);
    }
    onSelectIds(next);
  }

  if (isLoading) {
    return (
      <div
        className="space-y-2 p-4"
        role="status"
        aria-live="polite"
        aria-label="Loading emails"
      >
        {Array.from({ length: 5 }).map((_, i) => (
          <Skeleton key={i} className="h-10 w-full rounded-md" />
        ))}
      </div>
    );
  }

  if (emails.length === 0) {
    return (
      <div className="flex items-center justify-center py-16 text-sm text-muted-foreground">
        <p>No emails found matching the current filters.</p>
      </div>
    );
  }

  return (
    <div className="flex flex-col gap-3">
      <Table role="grid">
        <TableHeader>
          <TableRow>
            <TableHead className="w-10">
              <input
                type="checkbox"
                aria-label="Select all visible emails"
                checked={allVisibleSelected}
                ref={(el) => {
                  if (el) el.indeterminate = someSelected && !allVisibleSelected;
                }}
                onChange={handleSelectAll}
                className="size-4 cursor-pointer accent-primary"
              />
            </TableHead>
            <TableHead className="hidden sm:table-cell">Received</TableHead>
            <TableHead>Sender</TableHead>
            <TableHead>Subject</TableHead>
            <TableHead className="hidden md:table-cell">Classification</TableHead>
            <TableHead>State</TableHead>
          </TableRow>
        </TableHeader>
        <TableBody>
          {emails.map((email) => (
            <TableRow
              key={email.id}
              className={cn(
                "cursor-pointer transition-colors",
                selectedIds.has(email.id) && "bg-primary/5"
              )}
              onClick={() => onRowClick(email.id)}
            >
              <TableCell onClick={(e) => e.stopPropagation()}>
                <input
                  type="checkbox"
                  aria-label={`Select email: ${email.subject}`}
                  checked={selectedIds.has(email.id)}
                  onChange={(e) => handleRowSelect(e, email.id)}
                  className="size-4 cursor-pointer accent-primary"
                />
              </TableCell>
              <TableCell className="hidden sm:table-cell text-muted-foreground text-xs tabular-nums">
                {formatDate(email.received_at)}
              </TableCell>
              <TableCell>
                <div className="flex flex-col gap-0.5">
                  <span className="text-sm font-medium leading-tight">
                    {email.sender_name ?? ""}
                  </span>
                  <span className="text-xs text-muted-foreground">
                    {email.sender_email}
                  </span>
                </div>
              </TableCell>
              <TableCell className="max-w-xs">
                <div className="flex flex-col gap-0.5">
                  <span className="truncate text-sm font-medium">
                    {email.subject}
                  </span>
                  {email.snippet && (
                    <span className="truncate text-xs text-muted-foreground">
                      {email.snippet}
                    </span>
                  )}
                </div>
              </TableCell>
              <TableCell className="hidden md:table-cell">
                {email.classification ? (
                  <span className="flex items-center gap-1.5">
                    <ClassificationBadge
                      classification={email.classification}
                    />
                    <ConfidenceBadge
                      confidence={email.classification.confidence}
                    />
                  </span>
                ) : (
                  <span className="text-muted-foreground">—</span>
                )}
              </TableCell>
              <TableCell>
                <Badge variant={stateBadgeVariant(email.state)}>
                  {email.state.replace(/_/g, " ")}
                </Badge>
              </TableCell>
            </TableRow>
          ))}
        </TableBody>
      </Table>

      {/* Pagination */}
      <div className="flex items-center justify-between px-1 py-2">
        <Button
          variant="outline"
          size="sm"
          disabled={page <= 1}
          onClick={() => onPageChange(page - 1)}
          aria-label="Previous page"
        >
          Previous
        </Button>
        <span className="text-sm text-muted-foreground">
          Page {page} of {pages}, {total} total
        </span>
        <Button
          variant="outline"
          size="sm"
          disabled={page >= pages}
          onClick={() => onPageChange(page + 1)}
          aria-label="Next page"
        >
          Next
        </Button>
      </div>
    </div>
  );
}

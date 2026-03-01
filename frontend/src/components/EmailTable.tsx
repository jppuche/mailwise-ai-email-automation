// src/components/EmailTable.tsx
// Paginated table for displaying a list of EmailListItem records.
// Supports row selection (multi-select via checkbox), click-through to detail, pagination.
// Zero hardcoded colors — all via CSS custom properties.
import type { EmailListItem } from "@/types/generated/api";
import { ClassificationBadge } from "./ClassificationBadge";
import { ConfidenceBadge } from "./ConfidenceBadge";

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

export function EmailTable(props: EmailTableProps) {
  const { emails, total, page, pages, isLoading, selectedIds, onSelectIds, onPageChange, onRowClick } = props;
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

  function handleRowSelect(e: React.ChangeEvent<HTMLInputElement>, emailId: string) {
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
      <div className="loading-spinner" role="status" aria-live="polite" aria-label="Loading emails" />
    );
  }

  if (emails.length === 0) {
    return (
      <div className="email-table__empty">
        <p>No emails found matching the current filters.</p>
      </div>
    );
  }

  return (
    <div className="email-table-wrapper">
      <table className="email-table" role="grid">
        <thead className="email-table__header">
          <tr>
            <th className="email-table__header-cell email-table__header-cell--checkbox">
              <input
                type="checkbox"
                aria-label="Select all visible emails"
                checked={allVisibleSelected}
                ref={(el) => {
                  if (el) el.indeterminate = someSelected && !allVisibleSelected;
                }}
                onChange={handleSelectAll}
              />
            </th>
            <th className="email-table__header-cell">Received</th>
            <th className="email-table__header-cell">Sender</th>
            <th className="email-table__header-cell">Subject</th>
            <th className="email-table__header-cell">Classification</th>
            <th className="email-table__header-cell">State</th>
          </tr>
        </thead>
        <tbody>
          {emails.map((email) => (
            <tr
              key={email.id}
              className={`email-table__row${selectedIds.has(email.id) ? " email-table__row--selected" : ""}`}
              onClick={() => onRowClick(email.id)}
              style={{ cursor: "pointer" }}
            >
              <td
                className="email-table__cell email-table__cell--checkbox"
                onClick={(e) => e.stopPropagation()}
              >
                <input
                  type="checkbox"
                  aria-label={`Select email: ${email.subject}`}
                  checked={selectedIds.has(email.id)}
                  onChange={(e) => handleRowSelect(e, email.id)}
                />
              </td>
              <td className="email-table__cell email-table__cell--date">
                {formatDate(email.received_at)}
              </td>
              <td className="email-table__cell email-table__cell--sender">
                <div className="email-table__sender">
                  <span className="email-table__sender-name">{email.sender_name ?? ""}</span>
                  <span className="email-table__sender-email">{email.sender_email}</span>
                </div>
              </td>
              <td className="email-table__cell email-table__cell--subject">
                <div className="email-table__subject-col">
                  <span className="email-table__subject">{email.subject}</span>
                  {email.snippet && (
                    <span className="email-table__snippet">{email.snippet}</span>
                  )}
                </div>
              </td>
              <td className="email-table__cell email-table__cell--classification">
                {email.classification ? (
                  <span className="email-table__classification">
                    <ClassificationBadge classification={email.classification} />
                    <ConfidenceBadge confidence={email.classification.confidence} />
                  </span>
                ) : (
                  <span className="email-table__no-classification">—</span>
                )}
              </td>
              <td className="email-table__cell email-table__cell--state">
                <span className={`state-badge state-badge--${email.state.replace(/_/g, "-")}`}>
                  {email.state.replace(/_/g, " ")}
                </span>
              </td>
            </tr>
          ))}
        </tbody>
      </table>

      {/* Pagination */}
      <div className="pagination">
        <button
          className="pagination__btn"
          disabled={page <= 1}
          onClick={() => onPageChange(page - 1)}
          aria-label="Previous page"
        >
          Previous
        </button>
        <span className="pagination__info">
          Page {page} of {pages}, {total} total
        </span>
        <button
          className="pagination__btn"
          disabled={page >= pages}
          onClick={() => onPageChange(page + 1)}
          aria-label="Next page"
        >
          Next
        </button>
      </div>
    </div>
  );
}

// src/pages/EmailBrowserPage.tsx
// Route: /emails
// Orchestrates FilterBar, EmailTable, and bulk admin actions.
// Zero hardcoded colors — all via CSS custom properties.
import { useState } from "react";
import { useNavigate } from "react-router-dom";
import { useEmails, useEmailMutations } from "@/hooks/useEmails";
import { useAuth } from "@/contexts/AuthContext";
import { FilterBar } from "@/components/FilterBar";
import { EmailTable } from "@/components/EmailTable";
import type { EmailFilterParams } from "@/types/generated/api";

/** Page size for the email browser — named constant (pre-mortem Cat 8). */
const PAGE_SIZE = 20;

export default function EmailBrowserPage() {
  const navigate = useNavigate();
  const { user } = useAuth();
  const isAdmin = user?.role === "admin";

  const [filters, setFilters] = useState<EmailFilterParams>({});
  const [page, setPage] = useState(1);
  const [selectedIds, setSelectedIds] = useState<Set<string>>(new Set());

  const { data, isLoading, error } = useEmails(filters, { page, page_size: PAGE_SIZE });
  const { reclassify } = useEmailMutations();

  function handleFilterChange(next: EmailFilterParams) {
    setFilters(next);
    setPage(1); // Reset pagination when filters change
    setSelectedIds(new Set()); // Clear selection on filter change
  }

  function handleRowClick(emailId: string) {
    void navigate(`/emails/${emailId}`);
  }

  function handleReclassifySelected() {
    selectedIds.forEach((id) => {
      reclassify.mutate(id);
    });
    setSelectedIds(new Set());
  }

  return (
    <div className="email-browser-page">
      {/* Page header */}
      <div className="email-browser-page__header">
        <h1 className="email-browser-page__title">Emails</h1>

        {/* Bulk actions — admin only */}
        {isAdmin && selectedIds.size > 0 && (
          <div className="email-browser-page__bulk-actions">
            <span className="email-browser-page__selection-count">
              {selectedIds.size} selected
            </span>
            <button
              type="button"
              className="btn btn--secondary"
              disabled={reclassify.isPending}
              onClick={handleReclassifySelected}
            >
              {reclassify.isPending ? "Queuing..." : "Reclassify Selected"}
            </button>
          </div>
        )}
      </div>

      {/* Filter bar */}
      <FilterBar value={filters} onChange={handleFilterChange} />

      {/* Error state */}
      {error && (
        <div className="email-browser-page__error" role="alert">
          <p className="email-browser-page__error-text">
            Failed to load emails: {error.message}
          </p>
        </div>
      )}

      {/* Email table */}
      <EmailTable
        emails={data?.items ?? []}
        total={data?.total ?? 0}
        page={data?.page ?? page}
        pageSize={PAGE_SIZE}
        pages={data?.pages ?? 1}
        isLoading={isLoading}
        selectedIds={selectedIds}
        onSelectIds={setSelectedIds}
        onPageChange={setPage}
        onRowClick={handleRowClick}
      />
    </div>
  );
}

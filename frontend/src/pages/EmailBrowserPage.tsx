// src/pages/EmailBrowserPage.tsx
// Route: /emails
// Orchestrates FilterBar, EmailTable, and bulk admin actions.
import { useState } from "react";
import { useNavigate } from "react-router-dom";
import { useEmails, useEmailMutations } from "@/hooks/useEmails";
import { useAuth } from "@/contexts/AuthContext";
import { FilterBar } from "@/components/FilterBar";
import { EmailTable } from "@/components/EmailTable";
import { Button } from "@/components/ui/button";
import { Card, CardHeader, CardContent } from "@/components/ui/card";
import { Alert, AlertDescription } from "@/components/ui/alert";
import type { EmailFilterParams } from "@/types/generated/api";

/** Page size for the email browser — named constant. */
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
    <div className="space-y-4 animate-in fade-in slide-in-from-bottom-2 duration-300 fill-mode-both">
      {/* Page header */}
      <div className="flex items-center justify-between">
        <h1 className="text-2xl font-semibold tracking-tight">Emails</h1>

        {/* Bulk actions — admin only */}
        {isAdmin && selectedIds.size > 0 && (
          <div className="flex items-center gap-3">
            <span className="text-sm text-muted-foreground">
              {selectedIds.size} selected
            </span>
            <Button
              variant="secondary"
              size="sm"
              disabled={reclassify.isPending}
              onClick={handleReclassifySelected}
            >
              {reclassify.isPending ? "Queuing..." : "Reclassify Selected"}
            </Button>
          </div>
        )}
      </div>

      {/* Filter bar + table in a single card */}
      <Card>
        <CardHeader className="pb-2">
          <FilterBar value={filters} onChange={handleFilterChange} />
        </CardHeader>

        <CardContent className="pt-0">
          {/* Error state */}
          {error && (
            <Alert variant="destructive" className="mb-4">
              <AlertDescription>
                Failed to load emails: {error.message}
              </AlertDescription>
            </Alert>
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
        </CardContent>
      </Card>
    </div>
  );
}

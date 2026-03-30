// src/pages/ReviewQueuePage.tsx
// Route: /review
// Two tabs: "Low Confidence" emails and "Pending Drafts".
// Draft detail panel opens in-page via DraftReview component.
import { useState } from "react";
import { useNavigate } from "react-router-dom";
import { ChevronLeft, ChevronRight, CheckCircle2, FileText } from "lucide-react";
import { useLowConfidenceEmails, usePendingDrafts } from "@/hooks/useReviewQueue";
import { useDraftDetail, useDraftMutations } from "@/hooks/useDrafts";
import { DraftReview } from "@/components/DraftReview";
import { ClassificationBadge } from "@/components/ClassificationBadge";
import { ConfidenceBadge } from "@/components/ConfidenceBadge";
import { Button } from "@/components/ui/button";
import { Badge } from "@/components/ui/badge";
import { Alert, AlertDescription } from "@/components/ui/alert";
import { Skeleton } from "@/components/ui/skeleton";
import { Card, CardContent } from "@/components/ui/card";
import { Tabs, TabsList, TabsTrigger, TabsContent } from "@/components/ui/tabs";
import { cn } from "@/lib/utils";

type ActiveTab = "low-confidence" | "pending-drafts";

/** Page size for review queue lists — named constant. */
const PAGE_SIZE = 20;

/** Format an ISO datetime string to a short locale-aware representation. */
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

export default function ReviewQueuePage() {
  const navigate = useNavigate();
  const [activeTab, setActiveTab] = useState<ActiveTab>("low-confidence");
  const [selectedDraftId, setSelectedDraftId] = useState<string | null>(null);
  const [page, setPage] = useState(1);

  // Low-confidence tab data
  const {
    emails: lowConfEmails,
    total: lowConfTotal,
    isLoading: lowConfLoading,
    error: lowConfError,
  } = useLowConfidenceEmails({ page, page_size: PAGE_SIZE });

  // Pending drafts tab data
  const {
    drafts: pendingDrafts,
    total: pendingTotal,
    isLoading: pendingLoading,
    error: pendingError,
  } = usePendingDrafts({ page, page_size: PAGE_SIZE });

  // Draft detail (only fetches when a draft is selected)
  const {
    data: draftDetail,
    isLoading: draftDetailLoading,
    error: draftDetailError,
  } = useDraftDetail(selectedDraftId ?? "");

  const { approve, reject, reassign } = useDraftMutations();

  function handleTabChange(tab: ActiveTab) {
    setActiveTab(tab);
    setPage(1);
    setSelectedDraftId(null);
  }

  function handleApprove(draftId: string) {
    approve.mutate(
      { draftId, body: { push_to_gmail: true } },
      { onSuccess: () => setSelectedDraftId(null) },
    );
  }

  function handleReject(draftId: string, reason: string) {
    reject.mutate(
      { draftId, body: { reason } },
      { onSuccess: () => setSelectedDraftId(null) },
    );
  }

  function handleReassign(draftId: string, reviewerId: string) {
    reassign.mutate(
      { draftId, body: { reviewer_id: reviewerId } },
      { onSuccess: () => setSelectedDraftId(null) },
    );
  }

  const isActioning = approve.isPending || reject.isPending || reassign.isPending;

  return (
    <div className="space-y-6 animate-in fade-in slide-in-from-bottom-2 duration-300 fill-mode-both">
      {/* Page header */}
      <h1 className="text-2xl font-semibold tracking-tight">Review Queue</h1>

      <Tabs
        value={activeTab}
        onValueChange={(v) => handleTabChange(v as ActiveTab)}
      >
        <TabsList>
          <TabsTrigger value="low-confidence">
            Low Confidence
            <Badge variant="secondary" className="ml-2">
              {lowConfLoading ? "..." : lowConfTotal}
            </Badge>
          </TabsTrigger>
          <TabsTrigger value="pending-drafts">
            Pending Drafts
            <Badge variant="secondary" className="ml-2">
              {pendingLoading ? "..." : pendingTotal}
            </Badge>
          </TabsTrigger>
        </TabsList>

        {/* Low Confidence tab */}
        <TabsContent value="low-confidence">
          {lowConfError && (
            <Alert variant="destructive" className="mb-4">
              <AlertDescription>
                Failed to load emails: {lowConfError.message}
              </AlertDescription>
            </Alert>
          )}

          {lowConfLoading && (
            <div className="space-y-2" role="status" aria-live="polite">
              {Array.from({ length: 5 }).map((_, i) => (
                <Skeleton key={i} className="h-16 w-full rounded-lg" />
              ))}
            </div>
          )}

          {!lowConfLoading && !lowConfError && lowConfEmails.length === 0 && (
            <div className="flex flex-col items-center justify-center py-16 text-center">
              <CheckCircle2 className="size-12 text-muted-foreground/40 mb-3" />
              <p className="text-sm font-medium text-muted-foreground">
                No low-confidence emails found
              </p>
              <p className="text-xs text-muted-foreground/70 mt-1">
                All emails are classified with high confidence.
              </p>
            </div>
          )}

          {!lowConfLoading && lowConfEmails.length > 0 && (
            <div className="space-y-4">
              <ul className="space-y-2">
                {lowConfEmails.map((email) => (
                  <li key={email.id}>
                    <Card className="py-3 hover:bg-muted/50 transition-colors cursor-default">
                      <CardContent className="flex items-center justify-between px-4">
                        <div className="flex flex-col gap-0.5 min-w-0">
                          <span className="text-sm font-medium truncate">
                            {email.subject}
                          </span>
                          <span className="text-xs text-muted-foreground">
                            {email.sender_email}
                          </span>
                          <span className="text-xs text-muted-foreground">
                            {formatDate(email.received_at)}
                          </span>
                        </div>
                        <div className="flex items-center gap-2 ml-4 shrink-0">
                          {email.classification && (
                            <>
                              <ClassificationBadge
                                classification={email.classification}
                              />
                              <ConfidenceBadge
                                confidence={email.classification.confidence}
                              />
                            </>
                          )}
                          <Button
                            variant="ghost"
                            size="sm"
                            onClick={() => void navigate(`/emails/${email.id}`)}
                          >
                            View Email
                          </Button>
                        </div>
                      </CardContent>
                    </Card>
                  </li>
                ))}
              </ul>

              {/* Pagination */}
              <div className="flex items-center justify-between">
                <Button
                  variant="outline"
                  size="sm"
                  disabled={page <= 1}
                  onClick={() => setPage((p) => p - 1)}
                  aria-label="Previous page"
                >
                  <ChevronLeft className="size-4 mr-1" />
                  Previous
                </Button>
                <span className="text-sm text-muted-foreground">
                  Page {page}, {lowConfTotal} items (filtered)
                </span>
                <Button
                  variant="outline"
                  size="sm"
                  disabled={lowConfEmails.length < PAGE_SIZE}
                  onClick={() => setPage((p) => p + 1)}
                  aria-label="Next page"
                >
                  Next
                  <ChevronRight className="size-4 ml-1" />
                </Button>
              </div>
            </div>
          )}
        </TabsContent>

        {/* Pending Drafts tab */}
        <TabsContent value="pending-drafts">
          {pendingError && (
            <Alert variant="destructive" className="mb-4">
              <AlertDescription>
                Failed to load drafts: {pendingError.message}
              </AlertDescription>
            </Alert>
          )}

          {pendingLoading && (
            <div className="space-y-2" role="status" aria-live="polite">
              {Array.from({ length: 5 }).map((_, i) => (
                <Skeleton key={i} className="h-16 w-full rounded-lg" />
              ))}
            </div>
          )}

          {!pendingLoading && !pendingError && pendingDrafts.length === 0 && (
            <div className="flex flex-col items-center justify-center py-16 text-center">
              <FileText className="size-12 text-muted-foreground/40 mb-3" />
              <p className="text-sm font-medium text-muted-foreground">
                No pending drafts in the queue
              </p>
              <p className="text-xs text-muted-foreground/70 mt-1">
                All draft responses have been reviewed.
              </p>
            </div>
          )}

          {!pendingLoading && pendingDrafts.length > 0 && (
            <div className="space-y-4">
              <div className="grid grid-cols-1 lg:grid-cols-[1fr_1fr] gap-4">
                {/* Draft list + pagination */}
                <div className="space-y-4">
                  <ul className="space-y-2">
                    {pendingDrafts.map((draft) => (
                      <li key={draft.id}>
                        <Card
                          className={cn(
                            "py-3 hover:bg-muted/50 transition-colors cursor-pointer",
                            selectedDraftId === draft.id && "ring-2 ring-primary",
                          )}
                          onClick={() =>
                            setSelectedDraftId(
                              selectedDraftId === draft.id ? null : draft.id,
                            )
                          }
                          aria-current={
                            selectedDraftId === draft.id ? "true" : undefined
                          }
                        >
                          <CardContent className="px-4">
                            <div className="flex flex-col gap-0.5">
                              <span className="text-sm font-medium truncate">
                                {draft.email_subject}
                              </span>
                              <span className="text-xs text-muted-foreground">
                                {draft.email_sender}
                              </span>
                              <span className="text-xs text-muted-foreground">
                                {formatDate(draft.created_at)}
                              </span>
                            </div>
                          </CardContent>
                        </Card>
                      </li>
                    ))}
                  </ul>

                  {/* Pagination */}
                  <div className="flex items-center justify-between">
                    <Button
                      variant="outline"
                      size="sm"
                      disabled={page <= 1}
                      onClick={() => {
                        setPage((p) => p - 1);
                        setSelectedDraftId(null);
                      }}
                      aria-label="Previous page"
                    >
                      <ChevronLeft className="size-4 mr-1" />
                      Previous
                    </Button>
                    <span className="text-sm text-muted-foreground">
                      Page {page} of {Math.ceil(pendingTotal / PAGE_SIZE) || 1},{" "}
                      {pendingTotal} total
                    </span>
                    <Button
                      variant="outline"
                      size="sm"
                      disabled={pendingDrafts.length < PAGE_SIZE}
                      onClick={() => {
                        setPage((p) => p + 1);
                        setSelectedDraftId(null);
                      }}
                      aria-label="Next page"
                    >
                      Next
                      <ChevronRight className="size-4 ml-1" />
                    </Button>
                  </div>
                </div>

                {/* Draft review panel */}
                {selectedDraftId && (
                  <div className="space-y-3">
                    {draftDetailLoading && (
                      <div
                        className="space-y-2"
                        role="status"
                        aria-live="polite"
                      >
                        <Skeleton className="h-8 w-48" />
                        <Skeleton className="h-48 w-full" />
                      </div>
                    )}
                    {draftDetailError && (
                      <Alert variant="destructive">
                        <AlertDescription>
                          Failed to load draft: {draftDetailError.message}
                        </AlertDescription>
                      </Alert>
                    )}
                    {draftDetail && (
                      <DraftReview
                        draft={draftDetail}
                        onApprove={handleApprove}
                        onReject={handleReject}
                        onReassign={handleReassign}
                        isActioning={isActioning}
                      />
                    )}
                  </div>
                )}
              </div>
            </div>
          )}
        </TabsContent>
      </Tabs>
    </div>
  );
}

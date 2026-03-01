// src/pages/ReviewQueuePage.tsx
// Route: /review
// Two tabs: "Low Confidence" emails and "Pending Drafts".
// Draft detail panel opens in-page via DraftReview component.
// Zero hardcoded colors — all via CSS custom properties.
import { useState } from "react";
import { useNavigate } from "react-router-dom";
import { useLowConfidenceEmails, usePendingDrafts } from "@/hooks/useReviewQueue";
import { useDraftDetail, useDraftMutations } from "@/hooks/useDrafts";
import { DraftReview } from "@/components/DraftReview";
import { ClassificationBadge } from "@/components/ClassificationBadge";
import { ConfidenceBadge } from "@/components/ConfidenceBadge";

type ActiveTab = "low-confidence" | "pending-drafts";

/** Page size for review queue lists — named constant (pre-mortem Cat 8). */
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
    <div className="review-queue-page">
      <div className="review-queue-page__header">
        <h1 className="review-queue-page__title">Review Queue</h1>
      </div>

      {/* Tab navigation */}
      <div className="review-queue-page__tabs" role="tablist">
        <button
          type="button"
          role="tab"
          aria-selected={activeTab === "low-confidence"}
          className={`review-queue-page__tab${activeTab === "low-confidence" ? " review-queue-page__tab--active" : ""}`}
          onClick={() => handleTabChange("low-confidence")}
        >
          Low Confidence
          <span className="review-queue-page__tab-badge">
            {lowConfLoading ? "..." : lowConfTotal}
          </span>
        </button>
        <button
          type="button"
          role="tab"
          aria-selected={activeTab === "pending-drafts"}
          className={`review-queue-page__tab${activeTab === "pending-drafts" ? " review-queue-page__tab--active" : ""}`}
          onClick={() => handleTabChange("pending-drafts")}
        >
          Pending Drafts
          <span className="review-queue-page__tab-badge">
            {pendingLoading ? "..." : pendingTotal}
          </span>
        </button>
      </div>

      {/* Tab content */}
      <div className="review-queue-page__content">
        {/* Low Confidence tab */}
        {activeTab === "low-confidence" && (
          <div
            className="review-queue-page__tab-panel"
            role="tabpanel"
            aria-label="Low Confidence emails"
          >
            {lowConfError && (
              <div className="review-queue-page__error" role="alert">
                Failed to load emails: {lowConfError.message}
              </div>
            )}

            {lowConfLoading && (
              <div className="review-queue-page__loading" role="status" aria-live="polite">
                Loading...
              </div>
            )}

            {!lowConfLoading && !lowConfError && lowConfEmails.length === 0 && (
              <div className="review-queue-page__empty">
                <p>No low-confidence emails found.</p>
              </div>
            )}

            {!lowConfLoading && lowConfEmails.length > 0 && (
              <>
                <ul className="review-list">
                  {lowConfEmails.map((email) => (
                    <li key={email.id} className="review-list__item">
                      <div className="review-list__item-main">
                        <div className="review-list__item-info">
                          <span className="review-list__item-subject">{email.subject}</span>
                          <span className="review-list__item-sender">{email.sender_email}</span>
                          <span className="review-list__item-date">
                            {formatDate(email.received_at)}
                          </span>
                        </div>
                        <div className="review-list__item-badges">
                          {email.classification && (
                            <>
                              <ClassificationBadge classification={email.classification} />
                              <ConfidenceBadge confidence={email.classification.confidence} />
                            </>
                          )}
                        </div>
                      </div>
                      <button
                        type="button"
                        className="btn btn--ghost review-list__item-link"
                        onClick={() => void navigate(`/emails/${email.id}`)}
                      >
                        View Email &rarr;
                      </button>
                    </li>
                  ))}
                </ul>

                {/* Pagination */}
                <div className="pagination">
                  <button
                    className="pagination__btn"
                    disabled={page <= 1}
                    onClick={() => setPage((p) => p - 1)}
                    aria-label="Previous page"
                  >
                    Previous
                  </button>
                  <span className="pagination__info">
                    Page {page}, {lowConfTotal} items (filtered)
                  </span>
                  <button
                    className="pagination__btn"
                    disabled={lowConfEmails.length < PAGE_SIZE}
                    onClick={() => setPage((p) => p + 1)}
                    aria-label="Next page"
                  >
                    Next
                  </button>
                </div>
              </>
            )}
          </div>
        )}

        {/* Pending Drafts tab */}
        {activeTab === "pending-drafts" && (
          <div
            className="review-queue-page__tab-panel"
            role="tabpanel"
            aria-label="Pending Drafts"
          >
            {pendingError && (
              <div className="review-queue-page__error" role="alert">
                Failed to load drafts: {pendingError.message}
              </div>
            )}

            {pendingLoading && (
              <div className="review-queue-page__loading" role="status" aria-live="polite">
                Loading...
              </div>
            )}

            {!pendingLoading && !pendingError && pendingDrafts.length === 0 && (
              <div className="review-queue-page__empty">
                <p>No pending drafts in the queue.</p>
              </div>
            )}

            {!pendingLoading && pendingDrafts.length > 0 && (
              <div className="review-queue-page__drafts-layout">
                {/* Draft list */}
                <ul className="review-list">
                  {pendingDrafts.map((draft) => (
                    <li
                      key={draft.id}
                      className={`review-list__item review-list__item--selectable${selectedDraftId === draft.id ? " review-list__item--selected" : ""}`}
                      onClick={() =>
                        setSelectedDraftId(selectedDraftId === draft.id ? null : draft.id)
                      }
                      aria-current={selectedDraftId === draft.id ? "true" : undefined}
                    >
                      <div className="review-list__item-main">
                        <div className="review-list__item-info">
                          <span className="review-list__item-subject">
                            {draft.email_subject}
                          </span>
                          <span className="review-list__item-sender">{draft.email_sender}</span>
                          <span className="review-list__item-date">
                            {formatDate(draft.created_at)}
                          </span>
                        </div>
                      </div>
                    </li>
                  ))}
                </ul>

                {/* Pagination */}
                <div className="pagination">
                  <button
                    className="pagination__btn"
                    disabled={page <= 1}
                    onClick={() => {
                      setPage((p) => p - 1);
                      setSelectedDraftId(null);
                    }}
                    aria-label="Previous page"
                  >
                    Previous
                  </button>
                  <span className="pagination__info">
                    Page {page} of {Math.ceil(pendingTotal / PAGE_SIZE) || 1},{" "}
                    {pendingTotal} total
                  </span>
                  <button
                    className="pagination__btn"
                    disabled={pendingDrafts.length < PAGE_SIZE}
                    onClick={() => {
                      setPage((p) => p + 1);
                      setSelectedDraftId(null);
                    }}
                    aria-label="Next page"
                  >
                    Next
                  </button>
                </div>
              </div>
            )}

            {/* Draft review panel */}
            {selectedDraftId && (
              <div className="review-queue-page__draft-panel">
                {draftDetailLoading && (
                  <div className="review-queue-page__loading" role="status" aria-live="polite">
                    Loading draft...
                  </div>
                )}
                {draftDetailError && (
                  <div className="review-queue-page__error" role="alert">
                    Failed to load draft: {draftDetailError.message}
                  </div>
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
        )}
      </div>
    </div>
  );
}

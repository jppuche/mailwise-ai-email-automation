// src/components/DraftReview.tsx
// Side-by-side draft review: email context (left) + draft content (right) + action buttons.
//
// Handoff delta #2: NO PUT /api/drafts/{id} endpoint — inline edit is NOT implemented.
// Only Approve / Reject (with reason textarea) / Reassign (admin only).
//
// Zero hardcoded colors — all via CSS custom properties.
import { useState } from "react";
import type { DraftDetailResponse } from "@/types/generated/api";
import { ClassificationBadge } from "./ClassificationBadge";

interface DraftReviewProps {
  draft: DraftDetailResponse;
  onApprove: (draftId: string) => void;
  onReject: (draftId: string, reason: string) => void;
  onReassign?: (draftId: string, reviewerId: string) => void;
  isActioning: boolean;
}

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

export function DraftReview({
  draft,
  onApprove,
  onReject,
  onReassign,
  isActioning,
}: DraftReviewProps) {
  const [showRejectForm, setShowRejectForm] = useState(false);
  const [rejectReason, setRejectReason] = useState("");
  const [showReassignForm, setShowReassignForm] = useState(false);
  const [reassignReviewerId, setReassignReviewerId] = useState("");

  const isPending = draft.status === "pending";

  function handleApprove() {
    onApprove(draft.id);
  }

  function handleRejectSubmit(e: React.FormEvent) {
    e.preventDefault();
    const trimmed = rejectReason.trim();
    if (!trimmed) return;
    onReject(draft.id, trimmed);
    setShowRejectForm(false);
    setRejectReason("");
  }

  function handleReassignSubmit(e: React.FormEvent) {
    e.preventDefault();
    const trimmed = reassignReviewerId.trim();
    if (!trimmed || !onReassign) return;
    onReassign(draft.id, trimmed);
    setShowReassignForm(false);
    setReassignReviewerId("");
  }

  return (
    <div className="draft-review">
      {/* Left panel — original email context */}
      <div className="draft-review__panel draft-review__panel--email">
        <header className="draft-review__panel-header">
          <h3 className="draft-review__panel-title">Original Email</h3>
        </header>

        <div className="draft-review__email-meta">
          <div className="draft-review__meta-row">
            <span className="draft-review__meta-label">Subject</span>
            <span className="draft-review__meta-value">{draft.email.subject}</span>
          </div>
          <div className="draft-review__meta-row">
            <span className="draft-review__meta-label">From</span>
            <span className="draft-review__meta-value">
              {draft.email.sender_name
                ? `${draft.email.sender_name} <${draft.email.sender_email}>`
                : draft.email.sender_email}
            </span>
          </div>
          <div className="draft-review__meta-row">
            <span className="draft-review__meta-label">Received</span>
            <span className="draft-review__meta-value">
              {formatDate(draft.email.received_at)}
            </span>
          </div>
          {draft.email.classification && (
            <div className="draft-review__meta-row">
              <span className="draft-review__meta-label">Classification</span>
              <span className="draft-review__meta-value">
                <ClassificationBadge classification={draft.email.classification} />
              </span>
            </div>
          )}
        </div>

        {draft.email.snippet && (
          <div className="draft-review__snippet">
            <p className="draft-review__snippet-text">{draft.email.snippet}</p>
          </div>
        )}
      </div>

      {/* Right panel — draft content */}
      <div className="draft-review__panel draft-review__panel--draft">
        <header className="draft-review__panel-header">
          <h3 className="draft-review__panel-title">Draft Reply</h3>
          <span
            className={`state-badge state-badge--${draft.status}`}
            aria-label={`Draft status: ${draft.status}`}
          >
            {draft.status}
          </span>
        </header>

        <pre className="draft-review__content">{draft.content}</pre>

        {/* Actions — only shown for pending drafts */}
        {isPending && (
          <div className="draft-review__actions">
            {/* Approve */}
            {!showRejectForm && !showReassignForm && (
              <button
                className="btn btn--success"
                disabled={isActioning}
                onClick={handleApprove}
              >
                Approve
              </button>
            )}

            {/* Reject toggle */}
            {!showRejectForm && !showReassignForm && (
              <button
                className="btn btn--danger"
                disabled={isActioning}
                onClick={() => setShowRejectForm(true)}
              >
                Reject
              </button>
            )}

            {/* Reject form */}
            {showRejectForm && (
              <form className="draft-review__reject-form" onSubmit={handleRejectSubmit}>
                <label
                  className="draft-review__reject-label"
                  htmlFor="reject-reason"
                >
                  Rejection reason (required)
                </label>
                <textarea
                  id="reject-reason"
                  className="draft-review__reject-textarea"
                  rows={3}
                  placeholder="Explain why this draft is being rejected..."
                  value={rejectReason}
                  onChange={(e) => setRejectReason(e.target.value)}
                  required
                />
                <div className="draft-review__reject-actions">
                  <button
                    type="submit"
                    className="btn btn--danger"
                    disabled={isActioning || !rejectReason.trim()}
                  >
                    Confirm Reject
                  </button>
                  <button
                    type="button"
                    className="btn btn--secondary"
                    disabled={isActioning}
                    onClick={() => {
                      setShowRejectForm(false);
                      setRejectReason("");
                    }}
                  >
                    Cancel
                  </button>
                </div>
              </form>
            )}

            {/* Reassign — only if handler provided (admin only) */}
            {onReassign && !showRejectForm && !showReassignForm && (
              <button
                className="btn btn--secondary"
                disabled={isActioning}
                onClick={() => setShowReassignForm(true)}
              >
                Reassign
              </button>
            )}

            {/* Reassign form */}
            {onReassign && showReassignForm && (
              <form className="draft-review__reassign-form" onSubmit={handleReassignSubmit}>
                <label
                  className="draft-review__reassign-label"
                  htmlFor="reassign-reviewer"
                >
                  Reviewer ID (UUID)
                </label>
                <input
                  id="reassign-reviewer"
                  className="form-input"
                  type="text"
                  placeholder="e.g. 3fa85f64-5717-4562-b3fc-2c963f66afa6"
                  value={reassignReviewerId}
                  onChange={(e) => setReassignReviewerId(e.target.value)}
                  required
                />
                <div className="draft-review__reassign-actions">
                  <button
                    type="submit"
                    className="btn btn--primary"
                    disabled={isActioning || !reassignReviewerId.trim()}
                  >
                    Confirm Reassign
                  </button>
                  <button
                    type="button"
                    className="btn btn--secondary"
                    disabled={isActioning}
                    onClick={() => {
                      setShowReassignForm(false);
                      setReassignReviewerId("");
                    }}
                  >
                    Cancel
                  </button>
                </div>
              </form>
            )}
          </div>
        )}

        {/* Reviewed-at metadata for non-pending drafts */}
        {!isPending && draft.reviewed_at && (
          <p className="draft-review__reviewed-at">
            Reviewed {formatDate(draft.reviewed_at)}
          </p>
        )}
      </div>
    </div>
  );
}

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
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Button } from "@/components/ui/button";
import { Textarea } from "@/components/ui/textarea";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { cn } from "@/lib/utils";

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
    <div className="grid grid-cols-1 lg:grid-cols-2 gap-4">
      {/* Left panel — original email context */}
      <Card>
        <CardHeader className="pb-3">
          <CardTitle className="text-base">Original Email</CardTitle>
        </CardHeader>
        <CardContent className="space-y-4">
          <dl className="grid grid-cols-[auto_1fr] gap-x-4 gap-y-2 text-sm">
            <dt className="text-muted-foreground font-medium">Subject</dt>
            <dd className="text-foreground">{draft.email.subject}</dd>

            <dt className="text-muted-foreground font-medium">From</dt>
            <dd className="text-foreground">
              {draft.email.sender_name
                ? `${draft.email.sender_name} <${draft.email.sender_email}>`
                : draft.email.sender_email}
            </dd>

            <dt className="text-muted-foreground font-medium">Received</dt>
            <dd className="text-foreground">{formatDate(draft.email.received_at)}</dd>

            {draft.email.classification && (
              <>
                <dt className="text-muted-foreground font-medium">Classification</dt>
                <dd>
                  <ClassificationBadge classification={draft.email.classification} />
                </dd>
              </>
            )}
          </dl>

          {draft.email.snippet && (
            <div className="rounded-md bg-muted px-3 py-2 text-sm text-muted-foreground italic">
              {draft.email.snippet}
            </div>
          )}
        </CardContent>
      </Card>

      {/* Right panel — draft content */}
      <Card>
        <CardHeader className="pb-3">
          <div className="flex items-center justify-between">
            <CardTitle className="text-base">Draft Reply</CardTitle>
            <span
              className={cn(
                "inline-flex items-center rounded-full px-2.5 py-0.5 text-xs font-medium capitalize",
                draft.status === "pending" && "bg-warning/10 text-warning",
                draft.status === "approved" && "bg-success/10 text-success",
                draft.status === "rejected" && "bg-destructive/10 text-destructive",
                !["pending", "approved", "rejected"].includes(draft.status) && "bg-muted text-muted-foreground",
              )}
              aria-label={`Draft status: ${draft.status}`}
            >
              {draft.status}
            </span>
          </div>
        </CardHeader>
        <CardContent className="space-y-4">
          <pre className="whitespace-pre-wrap text-sm text-foreground font-mono bg-muted rounded-md p-3 overflow-auto max-h-64">
            {draft.content}
          </pre>

          {/* Actions — only shown for pending drafts */}
          {isPending && (
            <div className="space-y-3">
              {/* Approve + Reject + Reassign buttons row */}
              {!showRejectForm && !showReassignForm && (
                <div className="flex flex-wrap gap-2">
                  <Button
                    variant="default"
                    disabled={isActioning}
                    onClick={handleApprove}
                    className="bg-success hover:bg-success/90 text-success-foreground"
                  >
                    Approve
                  </Button>
                  <Button
                    variant="destructive"
                    disabled={isActioning}
                    onClick={() => setShowRejectForm(true)}
                  >
                    Reject
                  </Button>
                  {onReassign && (
                    <Button
                      variant="secondary"
                      disabled={isActioning}
                      onClick={() => setShowReassignForm(true)}
                    >
                      Reassign
                    </Button>
                  )}
                </div>
              )}

              {/* Reject form */}
              {showRejectForm && (
                <form className="space-y-3" onSubmit={handleRejectSubmit}>
                  <div className="space-y-1.5">
                    <Label htmlFor="reject-reason">Rejection reason (required)</Label>
                    <Textarea
                      id="reject-reason"
                      rows={3}
                      placeholder="Explain why this draft is being rejected..."
                      value={rejectReason}
                      onChange={(e) => setRejectReason(e.target.value)}
                      required
                    />
                  </div>
                  <div className="flex gap-2">
                    <Button
                      type="submit"
                      variant="destructive"
                      disabled={isActioning || !rejectReason.trim()}
                    >
                      Confirm Reject
                    </Button>
                    <Button
                      type="button"
                      variant="secondary"
                      disabled={isActioning}
                      onClick={() => {
                        setShowRejectForm(false);
                        setRejectReason("");
                      }}
                    >
                      Cancel
                    </Button>
                  </div>
                </form>
              )}

              {/* Reassign form */}
              {onReassign && showReassignForm && (
                <form className="space-y-3" onSubmit={handleReassignSubmit}>
                  <div className="space-y-1.5">
                    <Label htmlFor="reassign-reviewer">Reviewer ID (UUID)</Label>
                    <Input
                      id="reassign-reviewer"
                      type="text"
                      placeholder="e.g. 3fa85f64-5717-4562-b3fc-2c963f66afa6"
                      value={reassignReviewerId}
                      onChange={(e) => setReassignReviewerId(e.target.value)}
                      required
                    />
                  </div>
                  <div className="flex gap-2">
                    <Button
                      type="submit"
                      variant="default"
                      disabled={isActioning || !reassignReviewerId.trim()}
                    >
                      Confirm Reassign
                    </Button>
                    <Button
                      type="button"
                      variant="secondary"
                      disabled={isActioning}
                      onClick={() => {
                        setShowReassignForm(false);
                        setReassignReviewerId("");
                      }}
                    >
                      Cancel
                    </Button>
                  </div>
                </form>
              )}
            </div>
          )}

          {/* Reviewed-at metadata for non-pending drafts */}
          {!isPending && draft.reviewed_at && (
            <p className="text-xs text-muted-foreground">
              Reviewed {formatDate(draft.reviewed_at)}
            </p>
          )}
        </CardContent>
      </Card>
    </div>
  );
}

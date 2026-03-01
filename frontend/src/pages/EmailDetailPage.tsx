// src/pages/EmailDetailPage.tsx
// Route: /emails/:id
// Full email detail view with classification, routing actions, CRM sync, and draft info.
// Zero hardcoded colors — all via CSS custom properties.
import { useParams, useNavigate } from "react-router-dom";
import { useEmailDetail, useEmailMutations } from "@/hooks/useEmails";
import { useAuth } from "@/contexts/AuthContext";
import { ClassificationBadge } from "@/components/ClassificationBadge";
import { ConfidenceBadge } from "@/components/ConfidenceBadge";

/** Format an ISO datetime string to a short locale-aware representation. */
function formatDate(iso: string | null): string {
  if (!iso) return "—";
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

export default function EmailDetailPage() {
  const { id } = useParams<{ id: string }>();
  const navigate = useNavigate();
  const { user } = useAuth();
  const isAdmin = user?.role === "admin";

  const emailId = id ?? "";
  const { data: email, isLoading, error } = useEmailDetail(emailId);
  const { reclassify, retry } = useEmailMutations();

  function handleBack() {
    void navigate("/emails");
  }

  function handleReclassify() {
    reclassify.mutate(emailId);
  }

  function handleRetry() {
    retry.mutate(emailId);
  }

  // Loading state
  if (isLoading) {
    return (
      <div className="email-detail-page" role="status" aria-live="polite">
        <div className="email-detail-page__loading">Loading email...</div>
      </div>
    );
  }

  // Error state
  if (error) {
    return (
      <div className="email-detail-page">
        <div className="email-detail-page__error" role="alert">
          <p className="email-detail-page__error-text">
            Failed to load email: {error.message}
          </p>
          <button type="button" className="btn btn--secondary" onClick={handleBack}>
            Back to Emails
          </button>
        </div>
      </div>
    );
  }

  // No data (shouldn't happen if enabled only when id is truthy, but guard for TS)
  if (!email) {
    return (
      <div className="email-detail-page">
        <div className="email-detail-page__not-found" role="alert">
          <p>Email not found.</p>
          <button type="button" className="btn btn--secondary" onClick={handleBack}>
            Back to Emails
          </button>
        </div>
      </div>
    );
  }

  return (
    <div className="email-detail-page">
      {/* Back navigation */}
      <button
        type="button"
        className="email-detail-page__back btn btn--ghost"
        onClick={handleBack}
      >
        &larr; Back to Emails
      </button>

      {/* Header */}
      <div className="email-detail-page__header">
        <div className="email-detail-page__header-main">
          <h1 className="email-detail-page__subject">{email.subject}</h1>
          <span
            className={`state-badge state-badge--${email.state.replace(/_/g, "-")}`}
            aria-label={`Email state: ${email.state}`}
          >
            {email.state.replace(/_/g, " ")}
          </span>
        </div>
        <div className="email-detail-page__header-meta">
          <span className="email-detail-page__sender">
            {email.sender_name
              ? `${email.sender_name} <${email.sender_email}>`
              : email.sender_email}
          </span>
          <span className="email-detail-page__date">{formatDate(email.received_at)}</span>
        </div>
      </div>

      {/* Admin actions */}
      {isAdmin && (
        <div className="email-detail-page__admin-actions">
          <button
            type="button"
            className="btn btn--secondary"
            disabled={reclassify.isPending}
            onClick={handleReclassify}
          >
            {reclassify.isPending ? "Queuing..." : "Reclassify"}
          </button>
          <button
            type="button"
            className="btn btn--secondary"
            disabled={retry.isPending}
            onClick={handleRetry}
          >
            {retry.isPending ? "Queuing..." : "Retry Pipeline"}
          </button>
        </div>
      )}

      {/* Classification section */}
      <section className="email-detail-page__section" aria-labelledby="section-classification">
        <h2 className="email-detail-page__section-title" id="section-classification">
          Classification
        </h2>
        {email.classification ? (
          <div className="email-detail-page__classification">
            <ClassificationBadge classification={email.classification} />
            <ConfidenceBadge confidence={email.classification.confidence} />
            {email.classification.is_fallback && (
              <span className="email-detail-page__fallback-note">
                (fallback classification)
              </span>
            )}
          </div>
        ) : (
          <p className="email-detail-page__empty-section">No classification yet.</p>
        )}
      </section>

      {/* Routing actions section */}
      <section className="email-detail-page__section" aria-labelledby="section-routing">
        <h2 className="email-detail-page__section-title" id="section-routing">
          Routing Actions
        </h2>
        {email.routing_actions.length > 0 ? (
          <table className="detail-table" role="grid">
            <thead className="detail-table__header">
              <tr>
                <th className="detail-table__th">Channel</th>
                <th className="detail-table__th">Destination</th>
                <th className="detail-table__th">Status</th>
                <th className="detail-table__th">Dispatched At</th>
              </tr>
            </thead>
            <tbody>
              {email.routing_actions.map((action) => (
                <tr key={action.id} className="detail-table__row">
                  <td className="detail-table__td">{action.channel}</td>
                  <td className="detail-table__td">{action.destination}</td>
                  <td className="detail-table__td">
                    <span
                      className={`state-badge state-badge--${action.status.replace(/_/g, "-")}`}
                    >
                      {action.status}
                    </span>
                  </td>
                  <td className="detail-table__td">{formatDate(action.dispatched_at)}</td>
                </tr>
              ))}
            </tbody>
          </table>
        ) : (
          <p className="email-detail-page__empty-section">No routing actions yet.</p>
        )}
      </section>

      {/* CRM sync section */}
      <section className="email-detail-page__section" aria-labelledby="section-crm">
        <h2 className="email-detail-page__section-title" id="section-crm">
          CRM Sync
        </h2>
        {email.crm_sync ? (
          <dl className="email-detail-page__dl">
            <div className="email-detail-page__dl-row">
              <dt className="email-detail-page__dt">Status</dt>
              <dd className="email-detail-page__dd">
                <span
                  className={`state-badge state-badge--${email.crm_sync.status.replace(/_/g, "-")}`}
                >
                  {email.crm_sync.status}
                </span>
              </dd>
            </div>
            <div className="email-detail-page__dl-row">
              <dt className="email-detail-page__dt">Contact ID</dt>
              <dd className="email-detail-page__dd">
                {email.crm_sync.contact_id ?? "—"}
              </dd>
            </div>
            <div className="email-detail-page__dl-row">
              <dt className="email-detail-page__dt">Synced At</dt>
              <dd className="email-detail-page__dd">
                {formatDate(email.crm_sync.synced_at)}
              </dd>
            </div>
          </dl>
        ) : (
          <p className="email-detail-page__empty-section">No CRM sync data.</p>
        )}
      </section>

      {/* Draft section */}
      <section className="email-detail-page__section" aria-labelledby="section-draft">
        <h2 className="email-detail-page__section-title" id="section-draft">
          Draft
        </h2>
        {email.draft ? (
          <dl className="email-detail-page__dl">
            <div className="email-detail-page__dl-row">
              <dt className="email-detail-page__dt">Status</dt>
              <dd className="email-detail-page__dd">
                <span
                  className={`state-badge state-badge--${email.draft.status}`}
                >
                  {email.draft.status}
                </span>
              </dd>
            </div>
            <div className="email-detail-page__dl-row">
              <dt className="email-detail-page__dt">Created At</dt>
              <dd className="email-detail-page__dd">
                {formatDate(email.draft.created_at)}
              </dd>
            </div>
            <div className="email-detail-page__dl-row">
              <dt className="email-detail-page__dt">Review</dt>
              <dd className="email-detail-page__dd">
                <a
                  href="/review"
                  className="email-detail-page__link"
                >
                  Go to Review Queue
                </a>
              </dd>
            </div>
          </dl>
        ) : (
          <p className="email-detail-page__empty-section">No draft generated yet.</p>
        )}
      </section>
    </div>
  );
}

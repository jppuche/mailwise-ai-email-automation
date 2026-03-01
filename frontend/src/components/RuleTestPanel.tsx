// src/components/RuleTestPanel.tsx
// Dry-run test panel for routing rules.
// Receives onTest callback from parent — does not mutate directly.
import { useState } from "react";
import type { RuleTestRequest, RuleTestResponse } from "@/types/generated/api";

interface RuleTestPanelProps {
  onTest: (request: RuleTestRequest) => Promise<RuleTestResponse>;
  onClose: () => void;
}

export function RuleTestPanel({ onTest, onClose }: RuleTestPanelProps) {
  const [emailId, setEmailId] = useState("");
  const [actionSlug, setActionSlug] = useState("");
  const [typeSlug, setTypeSlug] = useState("");
  const [confidence, setConfidence] = useState<"high" | "low">("high");
  const [senderEmail, setSenderEmail] = useState("");
  const [senderDomain, setSenderDomain] = useState("");
  const [subject, setSubject] = useState("");
  const [snippet, setSnippet] = useState("");
  const [testing, setTesting] = useState(false);
  const [result, setResult] = useState<RuleTestResponse | null>(null);
  const [testError, setTestError] = useState<string | null>(null);

  async function handleSubmit(e: React.FormEvent) {
    e.preventDefault();
    setTestError(null);
    setResult(null);
    setTesting(true);

    try {
      const response = await onTest({
        email_id: emailId.trim(),
        action_slug: actionSlug.trim(),
        type_slug: typeSlug.trim(),
        confidence,
        sender_email: senderEmail.trim(),
        sender_domain: senderDomain.trim(),
        subject: subject.trim(),
        snippet: snippet.trim(),
      });
      setResult(response);
    } catch (err) {
      setTestError(err instanceof Error ? err.message : "Test failed");
    } finally {
      setTesting(false);
    }
  }

  const isValid =
    emailId.trim().length > 0 &&
    actionSlug.trim().length > 0 &&
    typeSlug.trim().length > 0 &&
    senderEmail.trim().length > 0 &&
    senderDomain.trim().length > 0 &&
    subject.trim().length > 0 &&
    snippet.trim().length > 0;

  return (
    <div className="rule-test-panel" role="region" aria-label="Rule test panel">
      <div className="rule-test-panel__header">
        <h3 className="rule-test-panel__title">Test Routing Rules (Dry Run)</h3>
        <button
          type="button"
          className="btn btn--ghost"
          onClick={onClose}
          aria-label="Close test panel"
        >
          &#x2715;
        </button>
      </div>

      <form className="rule-test-panel__form" onSubmit={handleSubmit} noValidate>
        <div className="rule-test-panel__fields">
          <div className="form-group">
            <label className="form-label" htmlFor="test-email-id">Email ID *</label>
            <input
              id="test-email-id"
              type="text"
              className="form-input"
              value={emailId}
              onChange={(e) => setEmailId(e.target.value)}
              placeholder="UUID"
              disabled={testing}
            />
          </div>

          <div className="form-group">
            <label className="form-label" htmlFor="test-action-slug">Action Slug *</label>
            <input
              id="test-action-slug"
              type="text"
              className="form-input"
              value={actionSlug}
              onChange={(e) => setActionSlug(e.target.value)}
              placeholder="e.g. respond"
              disabled={testing}
            />
          </div>

          <div className="form-group">
            <label className="form-label" htmlFor="test-type-slug">Type Slug *</label>
            <input
              id="test-type-slug"
              type="text"
              className="form-input"
              value={typeSlug}
              onChange={(e) => setTypeSlug(e.target.value)}
              placeholder="e.g. sales-inquiry"
              disabled={testing}
            />
          </div>

          <div className="form-group">
            <label className="form-label" htmlFor="test-confidence">Confidence</label>
            <select
              id="test-confidence"
              className="form-input"
              value={confidence}
              onChange={(e) => setConfidence(e.target.value as "high" | "low")}
              disabled={testing}
            >
              <option value="high">high</option>
              <option value="low">low</option>
            </select>
          </div>

          <div className="form-group">
            <label className="form-label" htmlFor="test-sender-email">Sender Email *</label>
            <input
              id="test-sender-email"
              type="text"
              className="form-input"
              value={senderEmail}
              onChange={(e) => setSenderEmail(e.target.value)}
              placeholder="sender@example.com"
              disabled={testing}
            />
          </div>

          <div className="form-group">
            <label className="form-label" htmlFor="test-sender-domain">Sender Domain *</label>
            <input
              id="test-sender-domain"
              type="text"
              className="form-input"
              value={senderDomain}
              onChange={(e) => setSenderDomain(e.target.value)}
              placeholder="example.com"
              disabled={testing}
            />
          </div>

          <div className="form-group">
            <label className="form-label" htmlFor="test-subject">Subject *</label>
            <input
              id="test-subject"
              type="text"
              className="form-input"
              value={subject}
              onChange={(e) => setSubject(e.target.value)}
              placeholder="Email subject"
              disabled={testing}
            />
          </div>

          <div className="form-group">
            <label className="form-label" htmlFor="test-snippet">Snippet *</label>
            <textarea
              id="test-snippet"
              className="form-input rule-test-panel__textarea"
              value={snippet}
              onChange={(e) => setSnippet(e.target.value)}
              placeholder="Email snippet / preview text"
              rows={3}
              disabled={testing}
            />
          </div>
        </div>

        <div className="rule-test-panel__submit">
          <button
            type="submit"
            className="btn btn--primary"
            disabled={testing || !isValid}
          >
            {testing ? "Testing..." : "Run Test"}
          </button>
        </div>
      </form>

      {testError && (
        <div className="rule-test-panel__error" role="alert">
          {testError}
        </div>
      )}

      {result && (
        <div className="rule-test-panel__results" role="status">
          <h4 className="rule-test-panel__results-title">
            Results — {result.matching_rules.length} rule(s) matched
          </h4>
          <dl className="rule-test-panel__results-summary">
            <div className="rule-test-panel__results-row">
              <dt>Rules evaluated:</dt>
              <dd>{result.total_rules_evaluated}</dd>
            </div>
            <div className="rule-test-panel__results-row">
              <dt>Total actions:</dt>
              <dd>{result.total_actions}</dd>
            </div>
            <div className="rule-test-panel__results-row">
              <dt>Dry run:</dt>
              <dd>{result.dry_run ? "Yes" : "No"}</dd>
            </div>
          </dl>

          {result.matching_rules.length > 0 && (
            <ul className="rule-test-panel__matched-list">
              {result.matching_rules.map((match) => (
                <li key={match.rule_id} className="rule-test-panel__matched-item">
                  <span className="rule-test-panel__matched-name">{match.rule_name}</span>
                  <span className="rule-test-panel__matched-priority">
                    Priority {match.priority}
                  </span>
                  <ul className="rule-test-panel__dispatch-list">
                    {match.would_dispatch.map((action, i) => (
                      <li key={i} className="rule-test-panel__dispatch-item">
                        {action.channel}: {action.destination}
                      </li>
                    ))}
                  </ul>
                </li>
              ))}
            </ul>
          )}

          {result.matching_rules.length === 0 && (
            <p className="rule-test-panel__no-match">
              No rules matched this email context.
            </p>
          )}
        </div>
      )}
    </div>
  );
}

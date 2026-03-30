// src/components/RuleTestPanel.tsx
// Dry-run test panel for routing rules.
// Receives onTest callback from parent — does not mutate directly.
import { useState } from "react";
import { X } from "lucide-react";
import type { RuleTestRequest, RuleTestResponse } from "@/types/generated/api";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { Textarea } from "@/components/ui/textarea";
import { Badge } from "@/components/ui/badge";
import { Alert, AlertDescription } from "@/components/ui/alert";

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
    <Card role="region" aria-label="Rule test panel">
      <CardHeader className="pb-3">
        <div className="flex items-center justify-between">
          <CardTitle className="text-base">Test Routing Rules (Dry Run)</CardTitle>
          <Button
            type="button"
            variant="ghost"
            size="icon"
            className="h-8 w-8"
            onClick={onClose}
            aria-label="Close test panel"
          >
            <X className="h-4 w-4" />
          </Button>
        </div>
      </CardHeader>

      <CardContent className="space-y-4">
        <form className="space-y-4" onSubmit={handleSubmit} noValidate>
          <div className="grid grid-cols-1 sm:grid-cols-2 gap-4">
            <div className="space-y-1.5">
              <Label htmlFor="test-email-id">Email ID *</Label>
              <Input
                id="test-email-id"
                type="text"
                value={emailId}
                onChange={(e) => setEmailId(e.target.value)}
                placeholder="UUID"
                disabled={testing}
              />
            </div>

            <div className="space-y-1.5">
              <Label htmlFor="test-action-slug">Action Slug *</Label>
              <Input
                id="test-action-slug"
                type="text"
                value={actionSlug}
                onChange={(e) => setActionSlug(e.target.value)}
                placeholder="e.g. respond"
                disabled={testing}
              />
            </div>

            <div className="space-y-1.5">
              <Label htmlFor="test-type-slug">Type Slug *</Label>
              <Input
                id="test-type-slug"
                type="text"
                value={typeSlug}
                onChange={(e) => setTypeSlug(e.target.value)}
                placeholder="e.g. sales-inquiry"
                disabled={testing}
              />
            </div>

            <div className="space-y-1.5">
              <Label htmlFor="test-confidence">Confidence</Label>
              <select
                id="test-confidence"
                className="flex h-9 w-full rounded-md border border-input bg-transparent px-3 py-1 text-sm shadow-sm focus:outline-none focus:ring-1 focus:ring-ring disabled:cursor-not-allowed disabled:opacity-50"
                value={confidence}
                onChange={(e) => setConfidence(e.target.value as "high" | "low")}
                disabled={testing}
              >
                <option value="high">high</option>
                <option value="low">low</option>
              </select>
            </div>

            <div className="space-y-1.5">
              <Label htmlFor="test-sender-email">Sender Email *</Label>
              <Input
                id="test-sender-email"
                type="text"
                value={senderEmail}
                onChange={(e) => setSenderEmail(e.target.value)}
                placeholder="sender@example.com"
                disabled={testing}
              />
            </div>

            <div className="space-y-1.5">
              <Label htmlFor="test-sender-domain">Sender Domain *</Label>
              <Input
                id="test-sender-domain"
                type="text"
                value={senderDomain}
                onChange={(e) => setSenderDomain(e.target.value)}
                placeholder="example.com"
                disabled={testing}
              />
            </div>

            <div className="space-y-1.5 sm:col-span-2">
              <Label htmlFor="test-subject">Subject *</Label>
              <Input
                id="test-subject"
                type="text"
                value={subject}
                onChange={(e) => setSubject(e.target.value)}
                placeholder="Email subject"
                disabled={testing}
              />
            </div>

            <div className="space-y-1.5 sm:col-span-2">
              <Label htmlFor="test-snippet">Snippet *</Label>
              <Textarea
                id="test-snippet"
                value={snippet}
                onChange={(e) => setSnippet(e.target.value)}
                placeholder="Email snippet / preview text"
                rows={3}
                disabled={testing}
              />
            </div>
          </div>

          <div>
            <Button
              type="submit"
              disabled={testing || !isValid}
            >
              {testing ? "Testing..." : "Run Test"}
            </Button>
          </div>
        </form>

        {testError && (
          <Alert variant="destructive" role="alert">
            <AlertDescription>{testError}</AlertDescription>
          </Alert>
        )}

        {result && (
          <Card role="status">
            <CardHeader className="pb-2">
              <CardTitle className="text-sm">
                Results — {result.matching_rules.length} rule(s) matched
              </CardTitle>
            </CardHeader>
            <CardContent className="space-y-3">
              <dl className="grid grid-cols-[auto_1fr] gap-x-4 gap-y-1 text-sm">
                <dt className="text-muted-foreground">Rules evaluated:</dt>
                <dd>{result.total_rules_evaluated}</dd>
                <dt className="text-muted-foreground">Total actions:</dt>
                <dd>{result.total_actions}</dd>
                <dt className="text-muted-foreground">Dry run:</dt>
                <dd>{result.dry_run ? "Yes" : "No"}</dd>
              </dl>

              {result.matching_rules.length > 0 && (
                <ul className="space-y-2">
                  {result.matching_rules.map((match) => (
                    <li key={match.rule_id} className="rounded-md border border-border p-3 space-y-2">
                      <div className="flex items-center gap-2 flex-wrap">
                        <span className="text-sm font-medium">{match.rule_name}</span>
                        <Badge variant="secondary" className="text-xs">
                          Priority {match.priority}
                        </Badge>
                      </div>
                      <ul className="space-y-1">
                        {match.would_dispatch.map((action, i) => (
                          <li key={i} className="text-xs text-muted-foreground">
                            {action.channel}: {action.destination}
                          </li>
                        ))}
                      </ul>
                    </li>
                  ))}
                </ul>
              )}

              {result.matching_rules.length === 0 && (
                <p className="text-sm text-muted-foreground">
                  No rules matched this email context.
                </p>
              )}
            </CardContent>
          </Card>
        )}
      </CardContent>
    </Card>
  );
}

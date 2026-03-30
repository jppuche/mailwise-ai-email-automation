// src/pages/EmailDetailPage.tsx
// Route: /emails/:id
// Full email detail view with classification, routing actions, CRM sync, and draft info.
import { useParams, useNavigate, Link } from "react-router-dom";
import { ArrowLeft, RefreshCw, RotateCcw } from "lucide-react";
import { useEmailDetail, useEmailMutations } from "@/hooks/useEmails";
import { useAuth } from "@/contexts/AuthContext";
import { ClassificationBadge } from "@/components/ClassificationBadge";
import { ConfidenceBadge } from "@/components/ConfidenceBadge";
import { Button } from "@/components/ui/button";
import { Badge } from "@/components/ui/badge";
import { Alert, AlertDescription } from "@/components/ui/alert";
import { Skeleton } from "@/components/ui/skeleton";
import { Card, CardHeader, CardTitle, CardContent } from "@/components/ui/card";
import {
  Table,
  TableHeader,
  TableHead,
  TableBody,
  TableRow,
  TableCell,
} from "@/components/ui/table";

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

/** Map an email/action state string to a shadcn Badge variant. */
function stateBadgeVariant(
  state: string,
): "destructive" | "outline" | "secondary" {
  if (state.startsWith("failed")) return "destructive";
  if (state.startsWith("draft")) return "outline";
  return "secondary";
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
      <div className="space-y-4" role="status" aria-live="polite">
        <Skeleton className="h-8 w-48" />
        <Skeleton className="h-6 w-96" />
        <Skeleton className="h-64 w-full" />
      </div>
    );
  }

  // Error state
  if (error) {
    return (
      <div className="flex flex-col items-center gap-4 py-12">
        <Alert variant="destructive" className="max-w-lg">
          <AlertDescription>
            Failed to load email: {error.message}
          </AlertDescription>
        </Alert>
        <Button variant="secondary" onClick={handleBack}>
          Back to Emails
        </Button>
      </div>
    );
  }

  // No data (guard for TS)
  if (!email) {
    return (
      <div className="flex flex-col items-center gap-4 py-12">
        <Alert variant="destructive" className="max-w-lg">
          <AlertDescription>Email not found.</AlertDescription>
        </Alert>
        <Button variant="secondary" onClick={handleBack}>
          Back to Emails
        </Button>
      </div>
    );
  }

  return (
    <div className="space-y-6 animate-in fade-in slide-in-from-bottom-2 duration-300 fill-mode-both">
      {/* Back navigation */}
      <Button variant="ghost" size="sm" onClick={handleBack}>
        <ArrowLeft className="mr-1 size-4" />
        Back to Emails
      </Button>

      {/* Header */}
      <div className="space-y-2">
        <div className="flex flex-wrap items-center gap-3">
          <h1 className="text-xl font-semibold">{email.subject}</h1>
          <Badge
            variant={stateBadgeVariant(email.state)}
            aria-label={`Email state: ${email.state}`}
          >
            {email.state.replace(/_/g, " ")}
          </Badge>
        </div>
        <div className="flex flex-wrap items-center gap-4 text-sm text-muted-foreground">
          <span>
            {email.sender_name
              ? `${email.sender_name} <${email.sender_email}>`
              : email.sender_email}
          </span>
          <span>{formatDate(email.received_at)}</span>
        </div>
      </div>

      {/* Admin actions */}
      {isAdmin && (
        <div className="flex gap-2">
          <Button
            variant="secondary"
            size="sm"
            disabled={reclassify.isPending}
            onClick={handleReclassify}
          >
            <RefreshCw className="mr-1 size-4" />
            {reclassify.isPending ? "Queuing..." : "Reclassify"}
          </Button>
          <Button
            variant="secondary"
            size="sm"
            disabled={retry.isPending}
            onClick={handleRetry}
          >
            <RotateCcw className="mr-1 size-4" />
            {retry.isPending ? "Queuing..." : "Retry Pipeline"}
          </Button>
        </div>
      )}

      {/* Classification section */}
      <Card>
        <CardHeader>
          <CardTitle className="text-base font-medium">Classification</CardTitle>
        </CardHeader>
        <CardContent>
          {email.classification ? (
            <div className="flex flex-wrap items-center gap-3">
              <ClassificationBadge classification={email.classification} />
              <ConfidenceBadge confidence={email.classification.confidence} />
              {email.classification.is_fallback && (
                <span className="text-sm text-muted-foreground">
                  (fallback classification)
                </span>
              )}
            </div>
          ) : (
            <p className="text-sm text-muted-foreground">No classification yet.</p>
          )}
        </CardContent>
      </Card>

      {/* Routing actions section */}
      <Card>
        <CardHeader>
          <CardTitle className="text-base font-medium">Routing Actions</CardTitle>
        </CardHeader>
        <CardContent>
          {email.routing_actions.length > 0 ? (
            <Table role="grid">
              <TableHeader>
                <TableRow>
                  <TableHead>Channel</TableHead>
                  <TableHead>Destination</TableHead>
                  <TableHead>Status</TableHead>
                  <TableHead>Dispatched At</TableHead>
                </TableRow>
              </TableHeader>
              <TableBody>
                {email.routing_actions.map((action) => (
                  <TableRow key={action.id}>
                    <TableCell>{action.channel}</TableCell>
                    <TableCell>{action.destination}</TableCell>
                    <TableCell>
                      <Badge variant={stateBadgeVariant(action.status)}>
                        {action.status}
                      </Badge>
                    </TableCell>
                    <TableCell>{formatDate(action.dispatched_at)}</TableCell>
                  </TableRow>
                ))}
              </TableBody>
            </Table>
          ) : (
            <p className="text-sm text-muted-foreground">No routing actions yet.</p>
          )}
        </CardContent>
      </Card>

      {/* CRM sync section */}
      <Card>
        <CardHeader>
          <CardTitle className="text-base font-medium">CRM Sync</CardTitle>
        </CardHeader>
        <CardContent>
          {email.crm_sync ? (
            <dl className="grid grid-cols-[auto_1fr] gap-x-4 gap-y-2 text-sm">
              <dt className="font-medium text-muted-foreground">Status</dt>
              <dd>
                <Badge variant={stateBadgeVariant(email.crm_sync.status)}>
                  {email.crm_sync.status}
                </Badge>
              </dd>
              <dt className="font-medium text-muted-foreground">Contact ID</dt>
              <dd>{email.crm_sync.contact_id ?? "—"}</dd>
              <dt className="font-medium text-muted-foreground">Synced At</dt>
              <dd>{formatDate(email.crm_sync.synced_at)}</dd>
            </dl>
          ) : (
            <p className="text-sm text-muted-foreground">No CRM sync data.</p>
          )}
        </CardContent>
      </Card>

      {/* Draft section */}
      <Card>
        <CardHeader>
          <CardTitle className="text-base font-medium">Draft</CardTitle>
        </CardHeader>
        <CardContent>
          {email.draft ? (
            <dl className="grid grid-cols-[auto_1fr] gap-x-4 gap-y-2 text-sm">
              <dt className="font-medium text-muted-foreground">Status</dt>
              <dd>
                <Badge variant={stateBadgeVariant(email.draft.status)}>
                  {email.draft.status}
                </Badge>
              </dd>
              <dt className="font-medium text-muted-foreground">Created At</dt>
              <dd>{formatDate(email.draft.created_at)}</dd>
              <dt className="font-medium text-muted-foreground">Review</dt>
              <dd>
                <Button variant="link" asChild className="h-auto p-0">
                  <Link to="/review">Go to Review Queue</Link>
                </Button>
              </dd>
            </dl>
          ) : (
            <p className="text-sm text-muted-foreground">No draft generated yet.</p>
          )}
        </CardContent>
      </Card>
    </div>
  );
}

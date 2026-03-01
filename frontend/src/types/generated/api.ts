// AUTO-GENERATED — DO NOT EDIT MANUALLY
// Run: npm run generate-types
// Source: http://localhost:8000/openapi.json
//
// This file is a PLACEHOLDER matching the actual backend schemas (B02/B13/B14).
// Run `npm run generate-types` with the backend live to regenerate the full spec.

export type paths = Record<string, never>;
export type webhooks = Record<string, never>;

export interface components {
  schemas: {
    // ----------------------------------------------------------------
    // Auth (B02)
    // ----------------------------------------------------------------

    /** POST /api/v1/auth/login request body */
    LoginRequest: {
      username: string;
      password: string;
    };
    /** Successful auth response: access token + refresh token */
    TokenResponse: {
      access_token: string;
      refresh_token: string;
      token_type: string;
    };
    /** POST /api/v1/auth/refresh request body */
    RefreshRequest: {
      refresh_token: string;
    };
    /** GET /api/v1/auth/me response — safe user representation */
    UserResponse: {
      id: string;
      username: string;
      role: "admin" | "reviewer";
      is_active: boolean;
    };

    // ----------------------------------------------------------------
    // Common (B13)
    // ----------------------------------------------------------------

    /** Paginated list response — generic via convenience aliases below */
    PaginatedResponseBase: {
      total: number;
      page: number;
      page_size: number;
      pages: number;
    };

    /** Pagination query params */
    PaginationParams: {
      page?: number;
      page_size?: number;
    };

    // ----------------------------------------------------------------
    // Emails (B13 — src/api/schemas/emails.py)
    // ----------------------------------------------------------------

    /**
     * EmailState — 12-state pipeline enum.
     * Values are lowercase (backend uses values_callable for StrEnum serialization).
     */
    EmailState:
      | "fetched"
      | "sanitized"
      | "classified"
      | "routed"
      | "draft_generated"
      | "draft_approved"
      | "draft_rejected"
      | "draft_sent"
      | "failed_classification"
      | "failed_routing"
      | "failed_draft"
      | "archived";

    /** Optional filters for GET /emails */
    EmailFilter: {
      state?: components["schemas"]["EmailState"];
      action?: string;
      type?: string;
      sender?: string;
      date_from?: string;
      date_to?: string;
    };

    /** Classification metadata for list and detail views */
    ClassificationSummary: {
      action: string;
      type: string;
      confidence: "high" | "low";
      is_fallback: boolean;
    };

    /** Routing action summary for email detail */
    RoutingActionSummary: {
      id: string;
      channel: string;
      destination: string;
      status: string;
      dispatched_at: string | null;
    };

    /** CRM sync status summary */
    CRMSyncSummary: {
      status: string;
      contact_id: string | null;
      activity_id: string | null;
      synced_at: string | null;
    };

    /** Draft summary for email detail */
    DraftSummary: {
      id: string;
      status: string;
      created_at: string;
    };

    /** Single email in a paginated list */
    EmailListItem: {
      id: string;
      subject: string;
      sender_email: string;
      sender_name: string | null;
      received_at: string;
      state: components["schemas"]["EmailState"];
      snippet: string | null;
      classification: components["schemas"]["ClassificationSummary"] | null;
    };

    /** Full email detail including all pipeline stages */
    EmailDetailResponse: {
      id: string;
      subject: string;
      sender_email: string;
      sender_name: string | null;
      received_at: string;
      state: components["schemas"]["EmailState"];
      snippet: string | null;
      thread_id: string | null;
      classification: components["schemas"]["ClassificationSummary"] | null;
      routing_actions: components["schemas"]["RoutingActionSummary"][];
      crm_sync: components["schemas"]["CRMSyncSummary"] | null;
      draft: components["schemas"]["DraftSummary"] | null;
      created_at: string;
      updated_at: string;
    };

    /** Request body for POST /emails/{id}/retry */
    RetryRequest: {
      reason?: string;
    };

    /** Response for retry action */
    RetryResponse: {
      queued: boolean;
      message: string;
      email_id: string;
    };

    /** Request body for POST /emails/{id}/reclassify */
    ReclassifyRequest: {
      reason?: string;
    };

    /** Response for reclassify action */
    ReclassifyResponse: {
      queued: boolean;
      message: string;
      email_id: string;
    };

    /** Full classification result for GET /emails/{id}/classification */
    ClassificationDetailResponse: {
      id: string;
      email_id: string;
      action: string;
      type: string;
      confidence: "high" | "low";
      is_fallback: boolean;
      classified_at: string;
    };

    /** Request body for POST /emails/{id}/classification/feedback */
    ClassificationFeedbackRequest: {
      corrected_action: string;
      corrected_type: string;
    };

    /** Response after submitting classification feedback */
    FeedbackResponse: {
      recorded: boolean;
      feedback_id: string;
    };

    // ----------------------------------------------------------------
    // Drafts (B13 — src/api/schemas/drafts.py)
    // ----------------------------------------------------------------

    /** Single draft in a paginated list */
    DraftListItem: {
      id: string;
      email_id: string;
      email_subject: string;
      email_sender: string;
      status: "pending" | "approved" | "rejected";
      reviewer_id: string | null;
      created_at: string;
    };

    /** Email context for side-by-side draft review */
    EmailForDraftReview: {
      id: string;
      subject: string;
      sender_email: string;
      sender_name: string | null;
      snippet: string | null;
      received_at: string;
      classification: components["schemas"]["ClassificationSummary"] | null;
    };

    /** Full draft detail for review */
    DraftDetailResponse: {
      id: string;
      content: string;
      status: "pending" | "approved" | "rejected";
      reviewer_id: string | null;
      reviewed_at: string | null;
      pushed_to_provider: boolean;
      email: components["schemas"]["EmailForDraftReview"];
      created_at: string;
      updated_at: string;
    };

    /** Request body for POST /drafts/{id}/approve */
    DraftApproveRequest: {
      push_to_gmail?: boolean;
    };

    /** Response after approving a draft */
    DraftApproveResponse: {
      draft_id: string;
      approved: boolean;
      gmail_draft_id: string | null;
      approved_at: string;
      note: string | null;
    };

    /** Request body for POST /drafts/{id}/reject */
    DraftRejectRequest: {
      reason: string;
    };

    /** Request body for POST /drafts/{id}/reassign */
    DraftReassignRequest: {
      reviewer_id: string;
    };

    /** Query params for GET /drafts */
    DraftFilter: {
      page?: number;
      page_size?: number;
      status?: "pending" | "approved" | "rejected";
    };

    // ----------------------------------------------------------------
    // Categories (B14 — src/api/schemas/categories.py)
    // ----------------------------------------------------------------

    /** Response schema for an action or type category */
    ActionCategoryResponse: {
      id: string;
      slug: string;
      name: string;
      description: string;
      is_fallback: boolean;
      is_active: boolean;
      display_order: number;
      created_at: string;
      updated_at: string;
    };

    /** TypeCategory has the same shape as ActionCategory */
    TypeCategoryResponse: {
      id: string;
      slug: string;
      name: string;
      description: string;
      is_fallback: boolean;
      is_active: boolean;
      display_order: number;
      created_at: string;
      updated_at: string;
    };

    /** Request body for POST /categories/actions */
    ActionCategoryCreate: {
      name: string;
      slug: string;
      description?: string;
      is_fallback?: boolean;
      is_active?: boolean;
    };

    /** Request body for PUT /categories/actions/{id} */
    ActionCategoryUpdate: {
      name?: string;
      description?: string;
      is_fallback?: boolean;
      is_active?: boolean;
    };

    /** TypeCategory create/update have the same shape */
    TypeCategoryCreate: {
      name: string;
      slug: string;
      description?: string;
      is_fallback?: boolean;
      is_active?: boolean;
    };

    TypeCategoryUpdate: {
      name?: string;
      description?: string;
      is_fallback?: boolean;
      is_active?: boolean;
    };

    /** Ordered list of IDs: index 0 → display_order 1 */
    ReorderRequest: {
      ordered_ids: string[];
    };

    // ----------------------------------------------------------------
    // Few-shot examples (B14 — src/api/schemas/categories.py)
    // ----------------------------------------------------------------

    /** Response schema for a few-shot example */
    FewShotExampleResponse: {
      id: string;
      email_snippet: string;
      action_slug: string;
      type_slug: string;
      rationale: string | null;
      is_active: boolean;
      created_at: string;
      updated_at: string;
    };

    /** Request body for POST /classification/examples */
    FewShotExampleCreate: {
      email_snippet: string;
      action_slug: string;
      type_slug: string;
      rationale?: string;
    };

    /** Request body for PUT /classification/examples/{id} */
    FewShotExampleUpdate: {
      email_snippet?: string;
      action_slug?: string;
      type_slug?: string;
      rationale?: string;
      is_active?: boolean;
    };

    // ----------------------------------------------------------------
    // Integrations (B14 — src/api/schemas/integrations.py)
    // ----------------------------------------------------------------

    /** LLM integration config — read-only, no credentials */
    LLMIntegrationConfig: {
      openai_api_key_configured: boolean;
      anthropic_api_key_configured: boolean;
      classify_model: string;
      draft_model: string;
      temperature_classify: number;
      temperature_draft: number;
      fallback_model: string;
      timeout_seconds: number;
      base_url: string;
    };

    /** Result of POST /integrations/llm/test */
    ConnectionTestResult: {
      success: boolean;
      latency_ms: number | null;
      error_detail: string | null;
      adapter_type: string;
    };

    // ----------------------------------------------------------------
    // Routing Rules (B13 — src/api/routers/routing_rules.py)
    // ----------------------------------------------------------------

    /** Condition within a routing rule */
    RoutingConditionSchema: {
      field: string;
      operator: string;
      value: string | string[];
    };

    /** Action to take when a routing rule matches */
    RoutingActionSchema: {
      channel: string;
      destination: string;
      template_id?: string | null;
    };

    /** Response schema for a routing rule */
    RoutingRuleResponse: {
      id: string;
      name: string;
      is_active: boolean;
      priority: number;
      conditions: components["schemas"]["RoutingConditionSchema"][];
      actions: components["schemas"]["RoutingActionSchema"][];
      created_at: string;
      updated_at: string;
    };

    /** Request body for POST /routing-rules */
    RoutingRuleCreate: {
      name: string;
      is_active?: boolean;
      conditions: components["schemas"]["RoutingConditionSchema"][];
      actions: components["schemas"]["RoutingActionSchema"][];
    };

    /** Request body for PUT /routing-rules/{id} — all fields optional */
    RoutingRuleUpdate: {
      name?: string | null;
      is_active?: boolean | null;
      conditions?: components["schemas"]["RoutingConditionSchema"][] | null;
      actions?: components["schemas"]["RoutingActionSchema"][] | null;
    };

    /** Request body for PUT /routing-rules/reorder */
    RoutingRuleReorderRequest: {
      ordered_ids: string[];
    };

    /** Request body for POST /routing-rules/test */
    RuleTestRequest: {
      email_id: string;
      action_slug: string;
      type_slug: string;
      confidence: "high" | "low";
      sender_email: string;
      sender_domain: string;
      subject: string;
      snippet: string;
      sender_name?: string | null;
    };

    /** Response from POST /routing-rules/test */
    RuleTestResponse: {
      matching_rules: components["schemas"]["RuleTestMatchResponse"][];
      total_rules_evaluated: number;
      total_actions: number;
      dry_run: boolean;
    };

    /** Single matched rule in a test response */
    RuleTestMatchResponse: {
      rule_id: string;
      rule_name: string;
      priority: number;
      would_dispatch: components["schemas"]["RoutingActionSchema"][];
    };

    // ----------------------------------------------------------------
    // Analytics (B14 — src/api/routers/analytics.py)
    // ----------------------------------------------------------------

    /** Single data point for volume time series */
    VolumeDataPoint: {
      date: string;
      count: number;
    };

    /** Response from GET /analytics/volume */
    VolumeResponse: {
      data_points: components["schemas"]["VolumeDataPoint"][];
      total_emails: number;
      start_date: string;
      end_date: string;
    };

    /** Single item in a classification distribution */
    DistributionItem: {
      category: string;
      display_name: string;
      count: number;
      percentage: number;
    };

    /** Response from GET /analytics/classification-distribution */
    ClassificationDistributionResponse: {
      actions: components["schemas"]["DistributionItem"][];
      types: components["schemas"]["DistributionItem"][];
      total_classified: number;
    };

    /** Response from GET /analytics/accuracy */
    AccuracyResponse: {
      total_classified: number;
      total_overridden: number;
      accuracy_pct: number;
      period_start: string;
      period_end: string;
    };

    /** Per-channel routing stats */
    RoutingChannelStat: {
      channel: string;
      dispatched: number;
      failed: number;
      success_rate: number;
    };

    /** Response from GET /analytics/routing */
    RoutingResponse: {
      channels: components["schemas"]["RoutingChannelStat"][];
      total_dispatched: number;
      total_failed: number;
      unrouted_count: number;
    };

    // ----------------------------------------------------------------
    // Integrations — additional configs (B14)
    // ----------------------------------------------------------------

    /** Email integration config — read-only */
    EmailIntegrationConfig: {
      oauth_configured: boolean;
      credentials_file: string;
      token_file: string;
      poll_interval_seconds: number;
      max_results: number;
    };

    /** Slack/channel integration config — read-only */
    ChannelIntegrationConfig: {
      bot_token_configured: boolean;
      signing_secret_configured: boolean;
      default_channel: string;
      snippet_length: number;
      timeout_seconds: number;
    };

    /** HubSpot CRM integration config — read-only */
    CRMIntegrationConfig: {
      access_token_configured: boolean;
      auto_create_contacts: boolean;
      default_lead_status: string;
      rate_limit_per_10s: number;
      api_timeout_seconds: number;
    };

    // ----------------------------------------------------------------
    // System Logs (B14 — src/api/routers/logs.py)
    // ----------------------------------------------------------------

    /** Single system log entry */
    LogEntry: {
      id: string;
      timestamp: string;
      level: string;
      source: string;
      message: string;
      email_id: string | null;
      context: Record<string, string>;
    };

    /** Paginated log response (offset/limit, NOT page-based) */
    LogListResponse: {
      items: components["schemas"]["LogEntry"][];
      total: number;
      limit: number;
      offset: number;
    };

    // ----------------------------------------------------------------
    // Health (B13 — src/api/routers/health.py)
    // ----------------------------------------------------------------

    /** Individual adapter health status */
    AdapterHealthItem: {
      name: string;
      status: "ok" | "degraded" | "unavailable";
      latency_ms: number | null;
      error: string | null;
    };

    /** Response from GET /health */
    HealthResponse: {
      status: "ok" | "degraded";
      version: string;
      adapters: components["schemas"]["AdapterHealthItem"][];
    };

    // ----------------------------------------------------------------
    // Validation errors (FastAPI standard)
    // ----------------------------------------------------------------

    HTTPValidationError: {
      detail?: components["schemas"]["ValidationError"][];
    };
    ValidationError: {
      loc: (string | number)[];
      msg: string;
      type: string;
    };
  };
  responses: never;
  parameters: never;
  requestBodies: never;
  headers: never;
  pathItems: never;
}

export type $defs = Record<string, never>;

export type external = Record<string, never>;

export type operations = Record<string, never>;

// ----------------------------------------------------------------
// Convenience aliases — import these in API modules and components
// ----------------------------------------------------------------

export type EmailState = components["schemas"]["EmailState"];
export type EmailFilter = components["schemas"]["EmailFilter"];
export type PaginationParams = components["schemas"]["PaginationParams"];

export type ClassificationSummary = components["schemas"]["ClassificationSummary"];
export type RoutingActionSummary = components["schemas"]["RoutingActionSummary"];
export type CRMSyncSummary = components["schemas"]["CRMSyncSummary"];
export type DraftSummary = components["schemas"]["DraftSummary"];

export type EmailListItem = components["schemas"]["EmailListItem"];
export type EmailDetailResponse = components["schemas"]["EmailDetailResponse"];

export type RetryRequest = components["schemas"]["RetryRequest"];
export type RetryResponse = components["schemas"]["RetryResponse"];
export type ReclassifyRequest = components["schemas"]["ReclassifyRequest"];
export type ReclassifyResponse = components["schemas"]["ReclassifyResponse"];
export type ClassificationDetailResponse = components["schemas"]["ClassificationDetailResponse"];
export type ClassificationFeedbackRequest = components["schemas"]["ClassificationFeedbackRequest"];
export type FeedbackResponse = components["schemas"]["FeedbackResponse"];

export type DraftListItem = components["schemas"]["DraftListItem"];
export type EmailForDraftReview = components["schemas"]["EmailForDraftReview"];
export type DraftDetailResponse = components["schemas"]["DraftDetailResponse"];
export type DraftApproveRequest = components["schemas"]["DraftApproveRequest"];
export type DraftApproveResponse = components["schemas"]["DraftApproveResponse"];
export type DraftRejectRequest = components["schemas"]["DraftRejectRequest"];
export type DraftReassignRequest = components["schemas"]["DraftReassignRequest"];
export type DraftFilter = components["schemas"]["DraftFilter"];

export type ActionCategoryResponse = components["schemas"]["ActionCategoryResponse"];
export type ActionCategoryCreate = components["schemas"]["ActionCategoryCreate"];
export type ActionCategoryUpdate = components["schemas"]["ActionCategoryUpdate"];
export type TypeCategoryResponse = components["schemas"]["TypeCategoryResponse"];
export type TypeCategoryCreate = components["schemas"]["TypeCategoryCreate"];
export type TypeCategoryUpdate = components["schemas"]["TypeCategoryUpdate"];
export type ReorderRequest = components["schemas"]["ReorderRequest"];

export type FewShotExampleResponse = components["schemas"]["FewShotExampleResponse"];
export type FewShotExampleCreate = components["schemas"]["FewShotExampleCreate"];
export type FewShotExampleUpdate = components["schemas"]["FewShotExampleUpdate"];

export type LLMIntegrationConfig = components["schemas"]["LLMIntegrationConfig"];
export type ConnectionTestResult = components["schemas"]["ConnectionTestResult"];
export type LLMTestResult = components["schemas"]["ConnectionTestResult"];

export type RoutingConditionSchema = components["schemas"]["RoutingConditionSchema"];
export type RoutingActionSchema = components["schemas"]["RoutingActionSchema"];
export type RoutingRuleResponse = components["schemas"]["RoutingRuleResponse"];
export type RoutingRuleCreate = components["schemas"]["RoutingRuleCreate"];
export type RoutingRuleUpdate = components["schemas"]["RoutingRuleUpdate"];
export type RoutingRuleReorderRequest = components["schemas"]["RoutingRuleReorderRequest"];
export type RuleTestRequest = components["schemas"]["RuleTestRequest"];
export type RuleTestResponse = components["schemas"]["RuleTestResponse"];
export type RuleTestMatchResponse = components["schemas"]["RuleTestMatchResponse"];

export type VolumeDataPoint = components["schemas"]["VolumeDataPoint"];
export type VolumeResponse = components["schemas"]["VolumeResponse"];
export type DistributionItem = components["schemas"]["DistributionItem"];
export type ClassificationDistributionResponse = components["schemas"]["ClassificationDistributionResponse"];
export type AccuracyResponse = components["schemas"]["AccuracyResponse"];
export type RoutingChannelStat = components["schemas"]["RoutingChannelStat"];
export type RoutingResponse = components["schemas"]["RoutingResponse"];

export type EmailIntegrationConfig = components["schemas"]["EmailIntegrationConfig"];
export type ChannelIntegrationConfig = components["schemas"]["ChannelIntegrationConfig"];
export type CRMIntegrationConfig = components["schemas"]["CRMIntegrationConfig"];

export type LogEntry = components["schemas"]["LogEntry"];
export type LogListResponse = components["schemas"]["LogListResponse"];

export type AdapterHealthItem = components["schemas"]["AdapterHealthItem"];
export type HealthResponse = components["schemas"]["HealthResponse"];

/** Generic paginated response — not in components (generic) */
export interface PaginatedResponse<T> {
  items: T[];
  total: number;
  page: number;
  page_size: number;
  pages: number;
}

/** Convenience alias matching the B16 task spec */
export type EmailFilterParams = EmailFilter;

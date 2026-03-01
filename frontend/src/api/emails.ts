// src/api/emails.ts
// Typed API functions for email endpoints — types from generated schema (tighten-types D4)
import apiClient from "./client";
import type {
  EmailFilterParams,
  PaginationParams,
  PaginatedResponse,
  EmailListItem,
  EmailDetailResponse,
  ClassificationDetailResponse,
  RetryResponse,
  ReclassifyResponse,
  ClassificationFeedbackRequest,
  FeedbackResponse,
} from "@/types/generated/api";

/**
 * GET /emails — paginated email list with optional filters.
 * Both filter and pagination params are optional query strings.
 */
export async function fetchEmails(
  params: EmailFilterParams & PaginationParams,
): Promise<PaginatedResponse<EmailListItem>> {
  const { data } = await apiClient.get<PaginatedResponse<EmailListItem>>("/emails", {
    params,
  });
  return data;
}

/**
 * GET /emails/{emailId} — full email detail with classification, routing, CRM, draft.
 */
export async function fetchEmailDetail(emailId: string): Promise<EmailDetailResponse> {
  const { data } = await apiClient.get<EmailDetailResponse>(`/emails/${emailId}`);
  return data;
}

/**
 * GET /emails/{emailId}/classification — full classification result.
 */
export async function fetchEmailClassification(emailId: string): Promise<ClassificationDetailResponse> {
  const { data } = await apiClient.get<ClassificationDetailResponse>(
    `/emails/${emailId}/classification`,
  );
  return data;
}

/**
 * POST /emails/{emailId}/retry — re-queue email through the pipeline (admin only).
 */
export async function retryEmail(emailId: string): Promise<RetryResponse> {
  const { data } = await apiClient.post<RetryResponse>(`/emails/${emailId}/retry`);
  return data;
}

/**
 * POST /emails/{emailId}/reclassify — re-queue email for classification (admin only).
 */
export async function reclassifyEmail(emailId: string): Promise<ReclassifyResponse> {
  const { data } = await apiClient.post<ReclassifyResponse>(`/emails/${emailId}/reclassify`);
  return data;
}

/**
 * POST /emails/{emailId}/classification/feedback — submit manual correction (reviewer+).
 * Returns HTTP 201 Created.
 */
export async function submitClassificationFeedback(
  emailId: string,
  body: ClassificationFeedbackRequest,
): Promise<FeedbackResponse> {
  const { data } = await apiClient.post<FeedbackResponse>(
    `/emails/${emailId}/classification/feedback`,
    body,
  );
  return data;
}

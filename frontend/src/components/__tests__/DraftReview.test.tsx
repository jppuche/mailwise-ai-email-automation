import { describe, it, expect, vi, beforeEach } from "vitest";
import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { DraftReview } from "../DraftReview";
import type { DraftDetailResponse } from "@/types/generated/api";

const mockDraft: DraftDetailResponse = {
  id: "draft-1",
  content: "Dear user, thank you for your email...",
  status: "pending",
  reviewer_id: null,
  reviewed_at: null,
  pushed_to_provider: false,
  email: {
    id: "email-1",
    subject: "Re: Complaint about service",
    sender_email: "user@example.com",
    sender_name: "Test User",
    snippet: "I am writing to complain...",
    received_at: "2026-01-15T10:30:00Z",
    classification: {
      action: "respond",
      type: "complaint",
      confidence: "low",
      is_fallback: false,
    },
  },
  created_at: "2026-01-15T11:00:00Z",
  updated_at: "2026-01-15T11:00:00Z",
};

describe("DraftReview", () => {
  beforeEach(() => {
    vi.clearAllMocks();
  });

  it("renders email subject in the left panel", () => {
    const onApprove = vi.fn();
    const onReject = vi.fn();
    render(
      <DraftReview
        draft={mockDraft}
        onApprove={onApprove}
        onReject={onReject}
        isActioning={false}
      />,
    );

    expect(screen.getByText("Re: Complaint about service")).toBeInTheDocument();
  });

  it("renders sender info in the left panel", () => {
    const onApprove = vi.fn();
    const onReject = vi.fn();
    render(
      <DraftReview
        draft={mockDraft}
        onApprove={onApprove}
        onReject={onReject}
        isActioning={false}
      />,
    );

    expect(screen.getByText(/Test User/)).toBeInTheDocument();
    expect(screen.getByText(/user@example\.com/)).toBeInTheDocument();
  });

  it("renders the email snippet in the left panel", () => {
    const onApprove = vi.fn();
    const onReject = vi.fn();
    render(
      <DraftReview
        draft={mockDraft}
        onApprove={onApprove}
        onReject={onReject}
        isActioning={false}
      />,
    );

    expect(screen.getByText("I am writing to complain...")).toBeInTheDocument();
  });

  it("renders draft content in the right panel", () => {
    const onApprove = vi.fn();
    const onReject = vi.fn();
    render(
      <DraftReview
        draft={mockDraft}
        onApprove={onApprove}
        onReject={onReject}
        isActioning={false}
      />,
    );

    expect(screen.getByText("Dear user, thank you for your email...")).toBeInTheDocument();
  });

  it("renders Original Email and Draft Reply panel titles", () => {
    const onApprove = vi.fn();
    const onReject = vi.fn();
    render(
      <DraftReview
        draft={mockDraft}
        onApprove={onApprove}
        onReject={onReject}
        isActioning={false}
      />,
    );

    expect(screen.getByText("Original Email")).toBeInTheDocument();
    expect(screen.getByText("Draft Reply")).toBeInTheDocument();
  });

  it("Approve button calls onApprove with the draft ID", async () => {
    const onApprove = vi.fn();
    const onReject = vi.fn();
    const user = userEvent.setup();
    render(
      <DraftReview
        draft={mockDraft}
        onApprove={onApprove}
        onReject={onReject}
        isActioning={false}
      />,
    );

    await user.click(screen.getByRole("button", { name: /^approve$/i }));
    expect(onApprove).toHaveBeenCalledWith("draft-1");
  });

  it("clicking Reject shows the reason textarea", async () => {
    const onApprove = vi.fn();
    const onReject = vi.fn();
    const user = userEvent.setup();
    render(
      <DraftReview
        draft={mockDraft}
        onApprove={onApprove}
        onReject={onReject}
        isActioning={false}
      />,
    );

    expect(screen.queryByLabelText(/rejection reason/i)).not.toBeInTheDocument();

    await user.click(screen.getByRole("button", { name: /^reject$/i }));
    expect(screen.getByLabelText(/rejection reason/i)).toBeInTheDocument();
  });

  it("submitting reject form calls onReject with draft ID and reason", async () => {
    const onApprove = vi.fn();
    const onReject = vi.fn();
    const user = userEvent.setup();
    render(
      <DraftReview
        draft={mockDraft}
        onApprove={onApprove}
        onReject={onReject}
        isActioning={false}
      />,
    );

    await user.click(screen.getByRole("button", { name: /^reject$/i }));
    const textarea = screen.getByLabelText(/rejection reason/i);
    await user.type(textarea, "Draft is factually incorrect");

    await user.click(screen.getByRole("button", { name: /confirm reject/i }));
    expect(onReject).toHaveBeenCalledWith("draft-1", "Draft is factually incorrect");
  });

  it("cancel on reject form hides the textarea", async () => {
    const onApprove = vi.fn();
    const onReject = vi.fn();
    const user = userEvent.setup();
    render(
      <DraftReview
        draft={mockDraft}
        onApprove={onApprove}
        onReject={onReject}
        isActioning={false}
      />,
    );

    await user.click(screen.getByRole("button", { name: /^reject$/i }));
    expect(screen.getByLabelText(/rejection reason/i)).toBeInTheDocument();

    await user.click(screen.getByRole("button", { name: /^cancel$/i }));
    expect(screen.queryByLabelText(/rejection reason/i)).not.toBeInTheDocument();
  });

  it("Reassign button is NOT shown when onReassign prop is not provided", () => {
    const onApprove = vi.fn();
    const onReject = vi.fn();
    render(
      <DraftReview
        draft={mockDraft}
        onApprove={onApprove}
        onReject={onReject}
        isActioning={false}
      />,
    );

    expect(screen.queryByRole("button", { name: /^reassign$/i })).not.toBeInTheDocument();
  });

  it("Reassign button is shown when onReassign prop is provided", () => {
    const onApprove = vi.fn();
    const onReject = vi.fn();
    const onReassign = vi.fn();
    render(
      <DraftReview
        draft={mockDraft}
        onApprove={onApprove}
        onReject={onReject}
        onReassign={onReassign}
        isActioning={false}
      />,
    );

    expect(screen.getByRole("button", { name: /^reassign$/i })).toBeInTheDocument();
  });

  it("clicking Reassign shows reviewer ID input", async () => {
    const onApprove = vi.fn();
    const onReject = vi.fn();
    const onReassign = vi.fn();
    const user = userEvent.setup();
    render(
      <DraftReview
        draft={mockDraft}
        onApprove={onApprove}
        onReject={onReject}
        onReassign={onReassign}
        isActioning={false}
      />,
    );

    await user.click(screen.getByRole("button", { name: /^reassign$/i }));
    expect(screen.getByLabelText(/reviewer id/i)).toBeInTheDocument();
  });

  it("action buttons are disabled when isActioning is true", () => {
    const onApprove = vi.fn();
    const onReject = vi.fn();
    render(
      <DraftReview
        draft={mockDraft}
        onApprove={onApprove}
        onReject={onReject}
        isActioning={true}
      />,
    );

    expect(screen.getByRole("button", { name: /^approve$/i })).toBeDisabled();
    expect(screen.getByRole("button", { name: /^reject$/i })).toBeDisabled();
  });

  it("action buttons are NOT shown for non-pending drafts", () => {
    const approvedDraft: DraftDetailResponse = { ...mockDraft, status: "approved" };
    const onApprove = vi.fn();
    const onReject = vi.fn();
    render(
      <DraftReview
        draft={approvedDraft}
        onApprove={onApprove}
        onReject={onReject}
        isActioning={false}
      />,
    );

    expect(screen.queryByRole("button", { name: /^approve$/i })).not.toBeInTheDocument();
    expect(screen.queryByRole("button", { name: /^reject$/i })).not.toBeInTheDocument();
  });

  it("shows reviewed-at date for non-pending drafts that have been reviewed", () => {
    const approvedDraft: DraftDetailResponse = {
      ...mockDraft,
      status: "approved",
      reviewed_at: "2026-01-16T09:00:00Z",
    };
    const onApprove = vi.fn();
    const onReject = vi.fn();
    render(
      <DraftReview
        draft={approvedDraft}
        onApprove={onApprove}
        onReject={onReject}
        isActioning={false}
      />,
    );

    expect(screen.getByText(/reviewed/i)).toBeInTheDocument();
  });
});

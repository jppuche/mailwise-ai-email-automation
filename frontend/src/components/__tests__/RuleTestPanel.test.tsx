// src/components/__tests__/RuleTestPanel.test.tsx
// Tests for the RuleTestPanel component — form fields, submit, results display,
// error display, and close button.
import { describe, it, expect, vi, beforeEach } from "vitest";
import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { RuleTestPanel } from "../RuleTestPanel";
import type { RuleTestRequest, RuleTestResponse } from "@/types/generated/api";

// ─────────────────────────────────────────────────────────────────────────────
// Test data factories
// ─────────────────────────────────────────────────────────────────────────────

function makeTestResponse(overrides: Partial<RuleTestResponse> = {}): RuleTestResponse {
  return {
    matching_rules: [
      {
        rule_id: "rule-1",
        rule_name: "Slack Alerts",
        priority: 1,
        would_dispatch: [{ channel: "slack", destination: "#alerts" }],
      },
    ],
    total_rules_evaluated: 3,
    total_actions: 1,
    dry_run: true,
    ...overrides,
  };
}

// ─────────────────────────────────────────────────────────────────────────────
// Helper: fill in all required fields
// ─────────────────────────────────────────────────────────────────────────────

async function fillValidForm(user: ReturnType<typeof userEvent.setup>) {
  await user.type(screen.getByLabelText(/email id/i), "email-abc-123");
  await user.type(screen.getByLabelText(/action slug/i), "respond");
  await user.type(screen.getByLabelText(/type slug/i), "inquiry");
  await user.type(screen.getByLabelText(/sender email/i), "customer@example.com");
  await user.type(screen.getByLabelText(/sender domain/i), "example.com");
  await user.type(screen.getByLabelText(/subject/i), "Question about pricing");
  await user.type(
    screen.getByLabelText(/snippet/i),
    "I would like to know more about your pricing options.",
  );
}

// ─────────────────────────────────────────────────────────────────────────────
// RuleTestPanel — form field rendering
// ─────────────────────────────────────────────────────────────────────────────

describe("RuleTestPanel — form fields", () => {
  beforeEach(() => {
    vi.clearAllMocks();
  });

  it("renders the panel title", () => {
    const onTest = vi.fn();
    const onClose = vi.fn();
    render(<RuleTestPanel onTest={onTest} onClose={onClose} />);

    expect(screen.getByText(/test routing rules/i)).toBeInTheDocument();
  });

  it("renders all required form fields", () => {
    const onTest = vi.fn();
    const onClose = vi.fn();
    render(<RuleTestPanel onTest={onTest} onClose={onClose} />);

    expect(screen.getByLabelText(/email id/i)).toBeInTheDocument();
    expect(screen.getByLabelText(/action slug/i)).toBeInTheDocument();
    expect(screen.getByLabelText(/type slug/i)).toBeInTheDocument();
    expect(screen.getByLabelText(/confidence/i)).toBeInTheDocument();
    expect(screen.getByLabelText(/sender email/i)).toBeInTheDocument();
    expect(screen.getByLabelText(/sender domain/i)).toBeInTheDocument();
    expect(screen.getByLabelText(/subject/i)).toBeInTheDocument();
    expect(screen.getByLabelText(/snippet/i)).toBeInTheDocument();
  });

  it("renders confidence select with 'high' and 'low' options", () => {
    const onTest = vi.fn();
    const onClose = vi.fn();
    render(<RuleTestPanel onTest={onTest} onClose={onClose} />);

    const confidenceSelect = screen.getByLabelText(/confidence/i);
    expect(confidenceSelect).toBeInTheDocument();
    expect(screen.getByRole("option", { name: "high" })).toBeInTheDocument();
    expect(screen.getByRole("option", { name: "low" })).toBeInTheDocument();
  });

  it("confidence defaults to 'high'", () => {
    const onTest = vi.fn();
    const onClose = vi.fn();
    render(<RuleTestPanel onTest={onTest} onClose={onClose} />);

    const confidenceSelect = screen.getByLabelText(/confidence/i) as HTMLSelectElement;
    expect(confidenceSelect.value).toBe("high");
  });

  it("'Run Test' button is disabled when required fields are empty", () => {
    const onTest = vi.fn();
    const onClose = vi.fn();
    render(<RuleTestPanel onTest={onTest} onClose={onClose} />);

    expect(screen.getByRole("button", { name: /run test/i })).toBeDisabled();
  });
});

// ─────────────────────────────────────────────────────────────────────────────
// RuleTestPanel — submit
// ─────────────────────────────────────────────────────────────────────────────

describe("RuleTestPanel — submit", () => {
  beforeEach(() => {
    vi.clearAllMocks();
  });

  it("'Run Test' button is enabled when all required fields are filled", async () => {
    const onTest = vi.fn().mockResolvedValue(makeTestResponse());
    const onClose = vi.fn();
    const user = userEvent.setup();
    render(<RuleTestPanel onTest={onTest} onClose={onClose} />);

    await fillValidForm(user);

    expect(screen.getByRole("button", { name: /run test/i })).not.toBeDisabled();
  });

  it("submitting calls onTest with the correct RuleTestRequest data", async () => {
    const onTest = vi.fn().mockResolvedValue(makeTestResponse());
    const onClose = vi.fn();
    const user = userEvent.setup();
    render(<RuleTestPanel onTest={onTest} onClose={onClose} />);

    await fillValidForm(user);
    await user.click(screen.getByRole("button", { name: /run test/i }));

    expect(onTest).toHaveBeenCalledOnce();
    expect(onTest).toHaveBeenCalledWith(
      expect.objectContaining<RuleTestRequest>({
        email_id: "email-abc-123",
        action_slug: "respond",
        type_slug: "inquiry",
        confidence: "high",
        sender_email: "customer@example.com",
        sender_domain: "example.com",
        subject: "Question about pricing",
        snippet: "I would like to know more about your pricing options.",
      }),
    );
  });

  it("submitting with confidence 'low' passes low to onTest", async () => {
    const onTest = vi.fn().mockResolvedValue(makeTestResponse());
    const onClose = vi.fn();
    const user = userEvent.setup();
    render(<RuleTestPanel onTest={onTest} onClose={onClose} />);

    await fillValidForm(user);
    await user.selectOptions(screen.getByLabelText(/confidence/i), "low");
    await user.click(screen.getByRole("button", { name: /run test/i }));

    expect(onTest).toHaveBeenCalledWith(
      expect.objectContaining({ confidence: "low" }),
    );
  });
});

// ─────────────────────────────────────────────────────────────────────────────
// RuleTestPanel — results display
// ─────────────────────────────────────────────────────────────────────────────

describe("RuleTestPanel — results display", () => {
  beforeEach(() => {
    vi.clearAllMocks();
  });

  it("displays results section after successful test", async () => {
    const response = makeTestResponse();
    const onTest = vi.fn().mockResolvedValue(response);
    const onClose = vi.fn();
    const user = userEvent.setup();
    render(<RuleTestPanel onTest={onTest} onClose={onClose} />);

    await fillValidForm(user);
    await user.click(screen.getByRole("button", { name: /run test/i }));

    expect(await screen.findByRole("status")).toBeInTheDocument();
  });

  it("displays number of matched rules in results title", async () => {
    const response = makeTestResponse();
    const onTest = vi.fn().mockResolvedValue(response);
    const onClose = vi.fn();
    const user = userEvent.setup();
    render(<RuleTestPanel onTest={onTest} onClose={onClose} />);

    await fillValidForm(user);
    await user.click(screen.getByRole("button", { name: /run test/i }));

    // "Results — 1 rule(s) matched"
    expect(await screen.findByText(/1 rule\(s\) matched/i)).toBeInTheDocument();
  });

  it("displays total_rules_evaluated in results summary", async () => {
    const response = makeTestResponse({ total_rules_evaluated: 5 });
    const onTest = vi.fn().mockResolvedValue(response);
    const onClose = vi.fn();
    const user = userEvent.setup();
    render(<RuleTestPanel onTest={onTest} onClose={onClose} />);

    await fillValidForm(user);
    await user.click(screen.getByRole("button", { name: /run test/i }));

    expect(await screen.findByText("5")).toBeInTheDocument();
  });

  it("displays matching rule name and priority in results", async () => {
    const response = makeTestResponse();
    const onTest = vi.fn().mockResolvedValue(response);
    const onClose = vi.fn();
    const user = userEvent.setup();
    render(<RuleTestPanel onTest={onTest} onClose={onClose} />);

    await fillValidForm(user);
    await user.click(screen.getByRole("button", { name: /run test/i }));

    expect(await screen.findByText("Slack Alerts")).toBeInTheDocument();
    expect(await screen.findByText(/priority 1/i)).toBeInTheDocument();
  });

  it("displays channel and destination for each dispatched action", async () => {
    const response = makeTestResponse();
    const onTest = vi.fn().mockResolvedValue(response);
    const onClose = vi.fn();
    const user = userEvent.setup();
    render(<RuleTestPanel onTest={onTest} onClose={onClose} />);

    await fillValidForm(user);
    await user.click(screen.getByRole("button", { name: /run test/i }));

    expect(await screen.findByText(/slack: #alerts/i)).toBeInTheDocument();
  });

  it("shows 'No rules matched' message when matching_rules is empty", async () => {
    const response = makeTestResponse({ matching_rules: [], total_rules_evaluated: 3, total_actions: 0 });
    const onTest = vi.fn().mockResolvedValue(response);
    const onClose = vi.fn();
    const user = userEvent.setup();
    render(<RuleTestPanel onTest={onTest} onClose={onClose} />);

    await fillValidForm(user);
    await user.click(screen.getByRole("button", { name: /run test/i }));

    expect(await screen.findByText(/no rules matched/i)).toBeInTheDocument();
  });

  it("does not show results section before test is run", () => {
    const onTest = vi.fn();
    const onClose = vi.fn();
    render(<RuleTestPanel onTest={onTest} onClose={onClose} />);

    expect(screen.queryByRole("status")).not.toBeInTheDocument();
  });
});

// ─────────────────────────────────────────────────────────────────────────────
// RuleTestPanel — error display
// ─────────────────────────────────────────────────────────────────────────────

describe("RuleTestPanel — error display", () => {
  beforeEach(() => {
    vi.clearAllMocks();
  });

  it("shows error alert when onTest rejects", async () => {
    const onTest = vi.fn().mockRejectedValue(new Error("Backend unavailable"));
    const onClose = vi.fn();
    const user = userEvent.setup();
    render(<RuleTestPanel onTest={onTest} onClose={onClose} />);

    await fillValidForm(user);
    await user.click(screen.getByRole("button", { name: /run test/i }));

    expect(await screen.findByRole("alert")).toHaveTextContent("Backend unavailable");
  });

  it("does not show error section before test is run", () => {
    const onTest = vi.fn();
    const onClose = vi.fn();
    render(<RuleTestPanel onTest={onTest} onClose={onClose} />);

    expect(screen.queryByRole("alert")).not.toBeInTheDocument();
  });
});

// ─────────────────────────────────────────────────────────────────────────────
// RuleTestPanel — close button
// ─────────────────────────────────────────────────────────────────────────────

describe("RuleTestPanel — close button", () => {
  beforeEach(() => {
    vi.clearAllMocks();
  });

  it("clicking close button calls onClose", async () => {
    const onTest = vi.fn();
    const onClose = vi.fn();
    const user = userEvent.setup();
    render(<RuleTestPanel onTest={onTest} onClose={onClose} />);

    await user.click(screen.getByRole("button", { name: /close test panel/i }));

    expect(onClose).toHaveBeenCalledOnce();
  });
});

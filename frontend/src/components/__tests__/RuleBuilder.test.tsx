// src/components/__tests__/RuleBuilder.test.tsx
// Tests for the RuleBuilder component — create mode, edit mode,
// condition/action row CRUD, form submit, and close button.
import { describe, it, expect, vi, beforeEach } from "vitest";
import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { RuleBuilder } from "../RuleBuilder";
import type { RoutingRuleResponse } from "@/types/generated/api";

// ─────────────────────────────────────────────────────────────────────────────
// Test data
// ─────────────────────────────────────────────────────────────────────────────

const mockRule: RoutingRuleResponse = {
  id: "rule-1",
  name: "Slack Alerts",
  is_active: true,
  priority: 1,
  conditions: [
    { field: "action_slug", operator: "eq", value: "urgent" },
  ],
  actions: [
    { channel: "slack", destination: "#alerts" },
  ],
  created_at: "2026-01-01T00:00:00Z",
  updated_at: "2026-01-01T00:00:00Z",
};

// ─────────────────────────────────────────────────────────────────────────────
// RuleBuilder — create mode
// ─────────────────────────────────────────────────────────────────────────────

describe("RuleBuilder — create mode (no rule prop)", () => {
  beforeEach(() => {
    vi.clearAllMocks();
  });

  it("renders the 'New Routing Rule' title in create mode", () => {
    const onSubmit = vi.fn();
    const onClose = vi.fn();
    render(<RuleBuilder onSubmit={onSubmit} onClose={onClose} />);

    expect(screen.getByRole("dialog", { name: /new routing rule/i })).toBeInTheDocument();
    expect(screen.getByText("New Routing Rule")).toBeInTheDocument();
  });

  it("renders empty rule name input in create mode", () => {
    const onSubmit = vi.fn();
    const onClose = vi.fn();
    render(<RuleBuilder onSubmit={onSubmit} onClose={onClose} />);

    const nameInput = screen.getByLabelText(/rule name/i);
    expect(nameInput).toHaveValue("");
  });

  it("renders the submit button labelled 'Create Rule'", () => {
    const onSubmit = vi.fn();
    const onClose = vi.fn();
    render(<RuleBuilder onSubmit={onSubmit} onClose={onClose} />);

    expect(screen.getByRole("button", { name: /^create rule$/i })).toBeInTheDocument();
  });

  it("renders one default condition row", () => {
    const onSubmit = vi.fn();
    const onClose = vi.fn();
    render(<RuleBuilder onSubmit={onSubmit} onClose={onClose} />);

    // Default condition row has field/operator/value inputs
    expect(screen.getByLabelText(/condition 1 field/i)).toBeInTheDocument();
  });

  it("renders one default action row", () => {
    const onSubmit = vi.fn();
    const onClose = vi.fn();
    render(<RuleBuilder onSubmit={onSubmit} onClose={onClose} />);

    expect(screen.getByLabelText(/action 1 channel/i)).toBeInTheDocument();
  });

  it("submit button is disabled when name is empty", () => {
    const onSubmit = vi.fn();
    const onClose = vi.fn();
    render(<RuleBuilder onSubmit={onSubmit} onClose={onClose} />);

    // Empty name → form is invalid
    expect(screen.getByRole("button", { name: /^create rule$/i })).toBeDisabled();
  });
});

// ─────────────────────────────────────────────────────────────────────────────
// RuleBuilder — edit mode
// ─────────────────────────────────────────────────────────────────────────────

describe("RuleBuilder — edit mode (rule prop provided)", () => {
  beforeEach(() => {
    vi.clearAllMocks();
  });

  it("renders the 'Edit Routing Rule' title in edit mode", () => {
    const onSubmit = vi.fn();
    const onClose = vi.fn();
    render(<RuleBuilder rule={mockRule} onSubmit={onSubmit} onClose={onClose} />);

    expect(screen.getByRole("dialog", { name: /edit routing rule/i })).toBeInTheDocument();
    expect(screen.getByText("Edit Routing Rule")).toBeInTheDocument();
  });

  it("pre-populates the rule name field in edit mode", () => {
    const onSubmit = vi.fn();
    const onClose = vi.fn();
    render(<RuleBuilder rule={mockRule} onSubmit={onSubmit} onClose={onClose} />);

    const nameInput = screen.getByLabelText(/rule name/i);
    expect(nameInput).toHaveValue("Slack Alerts");
  });

  it("renders 'Update Rule' submit button in edit mode", () => {
    const onSubmit = vi.fn();
    const onClose = vi.fn();
    render(<RuleBuilder rule={mockRule} onSubmit={onSubmit} onClose={onClose} />);

    expect(screen.getByRole("button", { name: /^update rule$/i })).toBeInTheDocument();
  });

  it("pre-populates conditions from the rule in edit mode", () => {
    const onSubmit = vi.fn();
    const onClose = vi.fn();
    render(<RuleBuilder rule={mockRule} onSubmit={onSubmit} onClose={onClose} />);

    const conditionValueInput = screen.getByLabelText(/condition 1 value/i);
    expect(conditionValueInput).toHaveValue("urgent");
  });

  it("pre-populates action channel from the rule in edit mode", () => {
    const onSubmit = vi.fn();
    const onClose = vi.fn();
    render(<RuleBuilder rule={mockRule} onSubmit={onSubmit} onClose={onClose} />);

    const channelInput = screen.getByLabelText(/action 1 channel/i);
    expect(channelInput).toHaveValue("slack");
  });

  it("pre-populates action destination from the rule in edit mode", () => {
    const onSubmit = vi.fn();
    const onClose = vi.fn();
    render(<RuleBuilder rule={mockRule} onSubmit={onSubmit} onClose={onClose} />);

    const destInput = screen.getByLabelText(/action 1 destination/i);
    expect(destInput).toHaveValue("#alerts");
  });
});

// ─────────────────────────────────────────────────────────────────────────────
// RuleBuilder — close button
// ─────────────────────────────────────────────────────────────────────────────

describe("RuleBuilder — close button", () => {
  beforeEach(() => {
    vi.clearAllMocks();
  });

  it("clicking the header close button calls onClose", async () => {
    const onSubmit = vi.fn();
    const onClose = vi.fn();
    const user = userEvent.setup();
    render(<RuleBuilder onSubmit={onSubmit} onClose={onClose} />);

    await user.click(screen.getByRole("button", { name: /^close$/i }));

    expect(onClose).toHaveBeenCalledOnce();
  });

  it("clicking the Cancel button calls onClose", async () => {
    const onSubmit = vi.fn();
    const onClose = vi.fn();
    const user = userEvent.setup();
    render(<RuleBuilder onSubmit={onSubmit} onClose={onClose} />);

    await user.click(screen.getByRole("button", { name: /^cancel$/i }));

    expect(onClose).toHaveBeenCalledOnce();
  });
});

// ─────────────────────────────────────────────────────────────────────────────
// RuleBuilder — adding conditions
// ─────────────────────────────────────────────────────────────────────────────

describe("RuleBuilder — add/remove condition rows", () => {
  beforeEach(() => {
    vi.clearAllMocks();
  });

  it("clicking 'Add Condition' appends a new condition row", async () => {
    const onSubmit = vi.fn();
    const onClose = vi.fn();
    const user = userEvent.setup();
    render(<RuleBuilder onSubmit={onSubmit} onClose={onClose} />);

    // Initially 1 condition row
    expect(screen.getByLabelText(/condition 1 field/i)).toBeInTheDocument();
    expect(screen.queryByLabelText(/condition 2 field/i)).not.toBeInTheDocument();

    await user.click(screen.getByRole("button", { name: /^add condition$/i }));

    expect(screen.getByLabelText(/condition 2 field/i)).toBeInTheDocument();
  });

  it("clicking 'Remove' on a condition row removes it", async () => {
    const onSubmit = vi.fn();
    const onClose = vi.fn();
    const user = userEvent.setup();
    render(<RuleBuilder onSubmit={onSubmit} onClose={onClose} />);

    // Add a second condition first
    await user.click(screen.getByRole("button", { name: /^add condition$/i }));
    expect(screen.getByLabelText(/condition 2 field/i)).toBeInTheDocument();

    // Remove the first condition
    await user.click(screen.getByRole("button", { name: /remove condition 1/i }));

    expect(screen.queryByLabelText(/condition 2 field/i)).not.toBeInTheDocument();
    expect(screen.getByLabelText(/condition 1 field/i)).toBeInTheDocument();
  });

  it("shows empty hint when all conditions are removed", async () => {
    const onSubmit = vi.fn();
    const onClose = vi.fn();
    const user = userEvent.setup();
    render(<RuleBuilder onSubmit={onSubmit} onClose={onClose} />);

    await user.click(screen.getByRole("button", { name: /remove condition 1/i }));

    expect(screen.getByText(/at least one condition is required/i)).toBeInTheDocument();
  });
});

// ─────────────────────────────────────────────────────────────────────────────
// RuleBuilder — adding actions
// ─────────────────────────────────────────────────────────────────────────────

describe("RuleBuilder — add/remove action rows", () => {
  beforeEach(() => {
    vi.clearAllMocks();
  });

  it("clicking 'Add Action' appends a new action row", async () => {
    const onSubmit = vi.fn();
    const onClose = vi.fn();
    const user = userEvent.setup();
    render(<RuleBuilder onSubmit={onSubmit} onClose={onClose} />);

    // Initially 1 action row
    expect(screen.getByLabelText(/action 1 channel/i)).toBeInTheDocument();
    expect(screen.queryByLabelText(/action 2 channel/i)).not.toBeInTheDocument();

    await user.click(screen.getByRole("button", { name: /^add action$/i }));

    expect(screen.getByLabelText(/action 2 channel/i)).toBeInTheDocument();
  });

  it("clicking 'Remove' on an action row removes it", async () => {
    const onSubmit = vi.fn();
    const onClose = vi.fn();
    const user = userEvent.setup();
    render(<RuleBuilder onSubmit={onSubmit} onClose={onClose} />);

    // Add a second action first
    await user.click(screen.getByRole("button", { name: /^add action$/i }));
    expect(screen.getByLabelText(/action 2 channel/i)).toBeInTheDocument();

    // Remove the first action
    await user.click(screen.getByRole("button", { name: /remove action 1/i }));

    expect(screen.queryByLabelText(/action 2 channel/i)).not.toBeInTheDocument();
    expect(screen.getByLabelText(/action 1 channel/i)).toBeInTheDocument();
  });

  it("shows empty hint when all actions are removed", async () => {
    const onSubmit = vi.fn();
    const onClose = vi.fn();
    const user = userEvent.setup();
    render(<RuleBuilder onSubmit={onSubmit} onClose={onClose} />);

    await user.click(screen.getByRole("button", { name: /remove action 1/i }));

    expect(screen.getByText(/at least one action is required/i)).toBeInTheDocument();
  });
});

// ─────────────────────────────────────────────────────────────────────────────
// RuleBuilder — submit
// ─────────────────────────────────────────────────────────────────────────────

describe("RuleBuilder — form submit", () => {
  beforeEach(() => {
    vi.clearAllMocks();
  });

  it("submitting a valid form calls onSubmit with the correct data structure", async () => {
    const onSubmit = vi.fn().mockResolvedValue(undefined);
    const onClose = vi.fn();
    const user = userEvent.setup();
    render(<RuleBuilder onSubmit={onSubmit} onClose={onClose} />);

    // Fill in rule name
    await user.type(screen.getByLabelText(/rule name/i), "New Test Rule");

    // Fill in condition value (field and operator already default)
    await user.type(screen.getByLabelText(/condition 1 value/i), "respond");

    // Fill in action channel and destination
    await user.type(screen.getByLabelText(/action 1 channel/i), "slack");
    await user.type(screen.getByLabelText(/action 1 destination/i), "#general");

    await user.click(screen.getByRole("button", { name: /^create rule$/i }));

    expect(onSubmit).toHaveBeenCalledOnce();
    expect(onSubmit).toHaveBeenCalledWith(
      expect.objectContaining({
        name: "New Test Rule",
        is_active: true,
        conditions: [
          expect.objectContaining({
            field: "action_slug",
            operator: "eq",
            value: "respond",
          }),
        ],
        actions: [
          expect.objectContaining({
            channel: "slack",
            destination: "#general",
          }),
        ],
      }),
    );
  });

  it("shows error message when onSubmit rejects", async () => {
    const onSubmit = vi.fn().mockRejectedValue(new Error("Server error"));
    const onClose = vi.fn();
    const user = userEvent.setup();
    render(<RuleBuilder onSubmit={onSubmit} onClose={onClose} />);

    // Fill valid data to enable submit button
    await user.type(screen.getByLabelText(/rule name/i), "Bad Rule");
    await user.type(screen.getByLabelText(/condition 1 value/i), "urgent");
    await user.type(screen.getByLabelText(/action 1 channel/i), "slack");
    await user.type(screen.getByLabelText(/action 1 destination/i), "#errors");

    await user.click(screen.getByRole("button", { name: /^create rule$/i }));

    expect(await screen.findByRole("alert")).toHaveTextContent("Server error");
  });

  it("pre-populates and submits correctly in edit mode", async () => {
    const onSubmit = vi.fn().mockResolvedValue(undefined);
    const onClose = vi.fn();
    const user = userEvent.setup();
    render(<RuleBuilder rule={mockRule} onSubmit={onSubmit} onClose={onClose} />);

    // Update the name field
    const nameInput = screen.getByLabelText(/rule name/i);
    await user.clear(nameInput);
    await user.type(nameInput, "Updated Rule Name");

    await user.click(screen.getByRole("button", { name: /^update rule$/i }));

    expect(onSubmit).toHaveBeenCalledOnce();
    expect(onSubmit).toHaveBeenCalledWith(
      expect.objectContaining({
        name: "Updated Rule Name",
      }),
    );
  });
});

// ─────────────────────────────────────────────────────────────────────────────
// RuleBuilder — dialog role
// ─────────────────────────────────────────────────────────────────────────────

describe("RuleBuilder — accessibility", () => {
  beforeEach(() => {
    vi.clearAllMocks();
  });

  it("has role='dialog'", () => {
    const onSubmit = vi.fn();
    const onClose = vi.fn();
    render(<RuleBuilder onSubmit={onSubmit} onClose={onClose} />);

    const dialog = screen.getByRole("dialog");
    expect(dialog).toBeInTheDocument();
  });

  it("renders Conditions and Actions sections", () => {
    const onSubmit = vi.fn();
    const onClose = vi.fn();
    render(<RuleBuilder onSubmit={onSubmit} onClose={onClose} />);

    expect(screen.getByRole("region", { name: /conditions/i })).toBeInTheDocument();
    expect(screen.getByRole("region", { name: /actions/i })).toBeInTheDocument();
  });
});

// ─────────────────────────────────────────────────────────────────────────────
// RuleBuilder — Active toggle
// ─────────────────────────────────────────────────────────────────────────────

describe("RuleBuilder — active toggle", () => {
  beforeEach(() => {
    vi.clearAllMocks();
  });

  it("active switch is checked by default in create mode", () => {
    const onSubmit = vi.fn();
    const onClose = vi.fn();
    render(<RuleBuilder onSubmit={onSubmit} onClose={onClose} />);

    // The active toggle is a shadcn Switch (role="switch")
    const switches = screen.getAllByRole("switch");
    expect(switches).toHaveLength(1);
    expect(switches[0]).toBeChecked();
  });
});

import { describe, it, expect, vi, beforeEach } from "vitest";
import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { CategoryList } from "../CategoryList";
import type { ActionCategoryResponse } from "@/types/generated/api";

const mockCategories: ActionCategoryResponse[] = [
  {
    id: "1",
    slug: "respond",
    name: "Respond",
    description: "Direct reply",
    is_fallback: false,
    is_active: true,
    display_order: 1,
    created_at: "2026-01-01T00:00:00Z",
    updated_at: "2026-01-01T00:00:00Z",
  },
  {
    id: "2",
    slug: "escalate",
    name: "Escalate",
    description: "Forward to manager",
    is_fallback: false,
    is_active: true,
    display_order: 2,
    created_at: "2026-01-01T00:00:00Z",
    updated_at: "2026-01-01T00:00:00Z",
  },
];

describe("CategoryList", () => {
  beforeEach(() => {
    vi.clearAllMocks();
  });

  it("renders all category items with their names", () => {
    const onReorder = vi.fn();
    const onEdit = vi.fn();
    const onDelete = vi.fn();
    const onToggleActive = vi.fn();
    render(
      <CategoryList
        categories={mockCategories}
        onReorder={onReorder}
        onEdit={onEdit}
        onDelete={onDelete}
        onToggleActive={onToggleActive}
      />,
    );

    expect(screen.getByText("Respond")).toBeInTheDocument();
    expect(screen.getByText("Escalate")).toBeInTheDocument();
  });

  it("renders category slugs", () => {
    const onReorder = vi.fn();
    const onEdit = vi.fn();
    const onDelete = vi.fn();
    const onToggleActive = vi.fn();
    render(
      <CategoryList
        categories={mockCategories}
        onReorder={onReorder}
        onEdit={onEdit}
        onDelete={onDelete}
        onToggleActive={onToggleActive}
      />,
    );

    expect(screen.getByText("respond")).toBeInTheDocument();
    expect(screen.getByText("escalate")).toBeInTheDocument();
  });

  it("renders empty state when categories is empty", () => {
    const onReorder = vi.fn();
    const onEdit = vi.fn();
    const onDelete = vi.fn();
    const onToggleActive = vi.fn();
    render(
      <CategoryList
        categories={[]}
        onReorder={onReorder}
        onEdit={onEdit}
        onDelete={onDelete}
        onToggleActive={onToggleActive}
      />,
    );

    expect(screen.getByText("No categories defined yet.")).toBeInTheDocument();
  });

  it("clicking Delete button shows confirmation dialog", async () => {
    const onReorder = vi.fn();
    const onEdit = vi.fn();
    const onDelete = vi.fn();
    const onToggleActive = vi.fn();
    const user = userEvent.setup();
    render(
      <CategoryList
        categories={mockCategories}
        onReorder={onReorder}
        onEdit={onEdit}
        onDelete={onDelete}
        onToggleActive={onToggleActive}
      />,
    );

    // Initially no confirmation dialog
    expect(screen.queryByRole("dialog")).not.toBeInTheDocument();

    // Click delete for "Respond"
    await user.click(screen.getByRole("button", { name: /delete respond/i }));

    // Confirmation dialog should appear with the category name in the message
    expect(screen.getByRole("dialog")).toBeInTheDocument();
    expect(screen.getByText(/are you sure you want to delete/i)).toBeInTheDocument();
    // The category name appears in the confirm dialog's strong element
    const dialog = screen.getByRole("dialog");
    expect(dialog).toHaveTextContent("Respond");
  });

  it("confirming delete calls onDelete with the category ID", async () => {
    const onReorder = vi.fn();
    const onEdit = vi.fn();
    const onDelete = vi.fn();
    const onToggleActive = vi.fn();
    const user = userEvent.setup();
    render(
      <CategoryList
        categories={mockCategories}
        onReorder={onReorder}
        onEdit={onEdit}
        onDelete={onDelete}
        onToggleActive={onToggleActive}
      />,
    );

    await user.click(screen.getByRole("button", { name: /delete respond/i }));
    await user.click(screen.getByRole("button", { name: /^delete$/i }));

    expect(onDelete).toHaveBeenCalledWith("1");
  });

  it("cancelling delete dialog dismisses without calling onDelete", async () => {
    const onReorder = vi.fn();
    const onEdit = vi.fn();
    const onDelete = vi.fn();
    const onToggleActive = vi.fn();
    const user = userEvent.setup();
    render(
      <CategoryList
        categories={mockCategories}
        onReorder={onReorder}
        onEdit={onEdit}
        onDelete={onDelete}
        onToggleActive={onToggleActive}
      />,
    );

    await user.click(screen.getByRole("button", { name: /delete respond/i }));
    expect(screen.getByRole("dialog")).toBeInTheDocument();

    await user.click(screen.getByRole("button", { name: /^cancel$/i }));
    expect(screen.queryByRole("dialog")).not.toBeInTheDocument();
    expect(onDelete).not.toHaveBeenCalled();
  });

  it("toggling the active checkbox calls onToggleActive with ID and new value", async () => {
    const onReorder = vi.fn();
    const onEdit = vi.fn();
    const onDelete = vi.fn();
    const onToggleActive = vi.fn();
    const user = userEvent.setup();
    render(
      <CategoryList
        categories={mockCategories}
        onReorder={onReorder}
        onEdit={onEdit}
        onDelete={onDelete}
        onToggleActive={onToggleActive}
      />,
    );

    // Toggle Respond (id="1") from active to inactive
    await user.click(screen.getByRole("checkbox", { name: /toggle respond active/i }));
    expect(onToggleActive).toHaveBeenCalledWith("1", false);
  });

  it("clicking Edit button calls onEdit with the category object", async () => {
    const onReorder = vi.fn();
    const onEdit = vi.fn();
    const onDelete = vi.fn();
    const onToggleActive = vi.fn();
    const user = userEvent.setup();
    render(
      <CategoryList
        categories={mockCategories}
        onReorder={onReorder}
        onEdit={onEdit}
        onDelete={onDelete}
        onToggleActive={onToggleActive}
      />,
    );

    await user.click(screen.getByRole("button", { name: /edit respond/i }));
    expect(onEdit).toHaveBeenCalledWith(mockCategories[0]);
  });

  it("renders Edit and Delete buttons for each category item", () => {
    const onReorder = vi.fn();
    const onEdit = vi.fn();
    const onDelete = vi.fn();
    const onToggleActive = vi.fn();
    render(
      <CategoryList
        categories={mockCategories}
        onReorder={onReorder}
        onEdit={onEdit}
        onDelete={onDelete}
        onToggleActive={onToggleActive}
      />,
    );

    expect(screen.getByRole("button", { name: /edit respond/i })).toBeInTheDocument();
    expect(screen.getByRole("button", { name: /edit escalate/i })).toBeInTheDocument();
    expect(screen.getByRole("button", { name: /delete respond/i })).toBeInTheDocument();
    expect(screen.getByRole("button", { name: /delete escalate/i })).toBeInTheDocument();
  });

  it("renders drag handles for each category item", () => {
    const onReorder = vi.fn();
    const onEdit = vi.fn();
    const onDelete = vi.fn();
    const onToggleActive = vi.fn();
    render(
      <CategoryList
        categories={mockCategories}
        onReorder={onReorder}
        onEdit={onEdit}
        onDelete={onDelete}
        onToggleActive={onToggleActive}
      />,
    );

    const handles = screen.getAllByLabelText("Drag to reorder");
    expect(handles).toHaveLength(2);
  });

  it("renders fallback badge for fallback categories", () => {
    const onReorder = vi.fn();
    const onEdit = vi.fn();
    const onDelete = vi.fn();
    const onToggleActive = vi.fn();
    const categoriesWithFallback: ActionCategoryResponse[] = [
      { ...mockCategories[0], is_fallback: true },
      mockCategories[1],
    ];
    render(
      <CategoryList
        categories={categoriesWithFallback}
        onReorder={onReorder}
        onEdit={onEdit}
        onDelete={onDelete}
        onToggleActive={onToggleActive}
      />,
    );

    expect(screen.getByText("fallback")).toBeInTheDocument();
  });

  it("active/inactive label reflects category is_active state", () => {
    const onReorder = vi.fn();
    const onEdit = vi.fn();
    const onDelete = vi.fn();
    const onToggleActive = vi.fn();
    const categoriesWithInactive: ActionCategoryResponse[] = [
      mockCategories[0],
      { ...mockCategories[1], is_active: false },
    ];
    render(
      <CategoryList
        categories={categoriesWithInactive}
        onReorder={onReorder}
        onEdit={onEdit}
        onDelete={onDelete}
        onToggleActive={onToggleActive}
      />,
    );

    const activeLabels = screen.getAllByText("Active");
    const inactiveLabels = screen.getAllByText("Inactive");
    expect(activeLabels).toHaveLength(1);
    expect(inactiveLabels).toHaveLength(1);
  });
});

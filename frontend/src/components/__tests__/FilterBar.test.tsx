import { describe, it, expect, vi, beforeEach, afterEach } from "vitest";
import { render, screen, act } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { FilterBar } from "../FilterBar";
import type { EmailFilterParams } from "@/types/generated/api";

const emptyFilters: EmailFilterParams = {};

describe("FilterBar", () => {
  it("renders state select with All option and all email state options", () => {
    const onChange = vi.fn();
    render(<FilterBar value={emptyFilters} onChange={onChange} />);

    const select = screen.getByRole("combobox", { name: /state/i });
    expect(select).toBeInTheDocument();
    expect(screen.getByText("All")).toBeInTheDocument();
    expect(screen.getByText("Classified")).toBeInTheDocument();
    expect(screen.getByText("Fetched")).toBeInTheDocument();
    expect(screen.getByText("Draft Generated")).toBeInTheDocument();
    expect(screen.getByText("Archived")).toBeInTheDocument();
  });

  it("renders action, type, and sender text inputs", () => {
    const onChange = vi.fn();
    render(<FilterBar value={emptyFilters} onChange={onChange} />);

    expect(screen.getByRole("textbox", { name: /action/i })).toBeInTheDocument();
    expect(screen.getByRole("textbox", { name: /type/i })).toBeInTheDocument();
    expect(screen.getByRole("textbox", { name: /sender/i })).toBeInTheDocument();
  });

  it("renders date from and to inputs", () => {
    const onChange = vi.fn();
    render(<FilterBar value={emptyFilters} onChange={onChange} />);

    expect(screen.getByLabelText(/^from$/i)).toBeInTheDocument();
    expect(screen.getByLabelText(/^to$/i)).toBeInTheDocument();
  });

  it("state select reflects the value prop", () => {
    const onChange = vi.fn();
    const filters: EmailFilterParams = { state: "classified" };
    render(<FilterBar value={filters} onChange={onChange} />);

    const select = screen.getByRole("combobox", { name: /state/i }) as HTMLSelectElement;
    expect(select.value).toBe("classified");
  });

  it("date inputs reflect the value prop", () => {
    const onChange = vi.fn();
    const filters: EmailFilterParams = { date_from: "2026-01-01", date_to: "2026-01-31" };
    render(<FilterBar value={filters} onChange={onChange} />);

    const fromInput = screen.getByLabelText(/^from$/i) as HTMLInputElement;
    const toInput = screen.getByLabelText(/^to$/i) as HTMLInputElement;
    expect(fromInput.value).toBe("2026-01-01");
    expect(toInput.value).toBe("2026-01-31");
  });

  it("text inputs reflect their value from value prop", () => {
    const onChange = vi.fn();
    const filters: EmailFilterParams = { action: "respond", type: "complaint", sender: "alice" };
    render(<FilterBar value={filters} onChange={onChange} />);

    const actionInput = screen.getByRole("textbox", { name: /action/i }) as HTMLInputElement;
    const typeInput = screen.getByRole("textbox", { name: /^type$/i }) as HTMLInputElement;
    const senderInput = screen.getByRole("textbox", { name: /sender/i }) as HTMLInputElement;

    expect(actionInput.value).toBe("respond");
    expect(typeInput.value).toBe("complaint");
    expect(senderInput.value).toBe("alice");
  });

  describe("interactions with fake timers", () => {
    beforeEach(() => {
      vi.useFakeTimers({ shouldAdvanceTime: true });
    });

    afterEach(() => {
      vi.runOnlyPendingTimers();
      vi.useRealTimers();
    });

    it("changing state select calls onChange immediately with updated state", async () => {
      const onChange = vi.fn();
      const user = userEvent.setup({ advanceTimers: vi.advanceTimersByTime });
      render(<FilterBar value={emptyFilters} onChange={onChange} />);

      const select = screen.getByRole("combobox", { name: /state/i });
      await user.selectOptions(select, "routed");

      expect(onChange).toHaveBeenCalledWith({ state: "routed" });
    });

    it("clearing state select calls onChange with state: undefined", async () => {
      const onChange = vi.fn();
      const user = userEvent.setup({ advanceTimers: vi.advanceTimersByTime });
      const filters: EmailFilterParams = { state: "classified" };
      render(<FilterBar value={filters} onChange={onChange} />);

      const select = screen.getByRole("combobox", { name: /state/i });
      await user.selectOptions(select, "");

      expect(onChange).toHaveBeenCalledWith({ state: undefined });
    });

    it("action text input change is debounced 300ms before calling onChange", async () => {
      const onChange = vi.fn();
      const user = userEvent.setup({ advanceTimers: vi.advanceTimersByTime });
      render(<FilterBar value={emptyFilters} onChange={onChange} />);

      const actionInput = screen.getByRole("textbox", { name: /action/i });
      await user.type(actionInput, "res");

      // Before debounce settles, onChange should not have been called
      expect(onChange).not.toHaveBeenCalled();

      // After 300ms debounce
      act(() => {
        vi.advanceTimersByTime(300);
      });
      expect(onChange).toHaveBeenCalledWith({ action: "res" });
    });

    it("sender text input change is debounced 300ms", async () => {
      const onChange = vi.fn();
      const user = userEvent.setup({ advanceTimers: vi.advanceTimersByTime });
      render(<FilterBar value={emptyFilters} onChange={onChange} />);

      const senderInput = screen.getByRole("textbox", { name: /sender/i });
      await user.type(senderInput, "test@");

      expect(onChange).not.toHaveBeenCalled();

      act(() => {
        vi.advanceTimersByTime(300);
      });
      expect(onChange).toHaveBeenCalledWith({ sender: "test@" });
    });

    it("type text input change is debounced 300ms", async () => {
      const onChange = vi.fn();
      const user = userEvent.setup({ advanceTimers: vi.advanceTimersByTime });
      render(<FilterBar value={emptyFilters} onChange={onChange} />);

      const typeInput = screen.getByRole("textbox", { name: /^type$/i });
      await user.type(typeInput, "complaint");

      expect(onChange).not.toHaveBeenCalled();

      act(() => {
        vi.advanceTimersByTime(300);
      });
      expect(onChange).toHaveBeenCalledWith({ type: "complaint" });
    });

    it("date from input emits onChange immediately (no debounce)", async () => {
      const onChange = vi.fn();
      const user = userEvent.setup({ advanceTimers: vi.advanceTimersByTime });
      render(<FilterBar value={emptyFilters} onChange={onChange} />);

      const fromInput = screen.getByLabelText(/^from$/i);
      await user.type(fromInput, "2026-03-01");

      // Date input fires onChange on each character — at least one call is immediate
      expect(onChange).toHaveBeenCalled();
    });

    it("date to input emits onChange immediately (no debounce)", async () => {
      const onChange = vi.fn();
      const user = userEvent.setup({ advanceTimers: vi.advanceTimersByTime });
      render(<FilterBar value={emptyFilters} onChange={onChange} />);

      const toInput = screen.getByLabelText(/^to$/i);
      await user.type(toInput, "2026-03-31");

      expect(onChange).toHaveBeenCalled();
    });
  });
});

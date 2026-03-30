import { describe, it, expect, beforeEach, vi } from "vitest";
import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { ThemeProvider, useTheme } from "../ThemeContext";

function ThemeDisplay() {
  const { theme, toggleTheme } = useTheme();
  return (
    <div>
      <span data-testid="theme">{theme}</span>
      <button onClick={toggleTheme}>Toggle</button>
    </div>
  );
}

function renderWithTheme() {
  return render(
    <ThemeProvider>
      <ThemeDisplay />
    </ThemeProvider>,
  );
}

describe("ThemeContext", () => {
  beforeEach(() => {
    localStorage.clear();
    document.documentElement.removeAttribute("data-theme");
  });

  it("defaults to light when no saved preference and no system dark mode", () => {
    vi.spyOn(window, "matchMedia").mockReturnValue({
      matches: false,
    } as MediaQueryList);

    renderWithTheme();
    expect(screen.getByTestId("theme").textContent).toBe("light");
    expect(document.documentElement.getAttribute("data-theme")).toBe("light");
  });

  it("respects system dark mode preference on first render", () => {
    vi.spyOn(window, "matchMedia").mockReturnValue({
      matches: true,
    } as MediaQueryList);

    renderWithTheme();
    expect(screen.getByTestId("theme").textContent).toBe("dark");
    expect(document.documentElement.getAttribute("data-theme")).toBe("dark");
  });

  it("restores saved preference from localStorage", () => {
    localStorage.setItem("mailwise-theme", "dark");

    renderWithTheme();
    expect(screen.getByTestId("theme").textContent).toBe("dark");
  });

  it("toggles theme from light to dark", async () => {
    vi.spyOn(window, "matchMedia").mockReturnValue({
      matches: false,
    } as MediaQueryList);

    renderWithTheme();
    const user = userEvent.setup();

    await user.click(screen.getByText("Toggle"));

    expect(screen.getByTestId("theme").textContent).toBe("dark");
    expect(document.documentElement.getAttribute("data-theme")).toBe("dark");
  });

  it("persists theme preference to localStorage", async () => {
    vi.spyOn(window, "matchMedia").mockReturnValue({
      matches: false,
    } as MediaQueryList);

    renderWithTheme();
    const user = userEvent.setup();

    await user.click(screen.getByText("Toggle"));

    expect(localStorage.getItem("mailwise-theme")).toBe("dark");
  });

  it("toggles back from dark to light", async () => {
    localStorage.setItem("mailwise-theme", "dark");

    renderWithTheme();
    const user = userEvent.setup();

    await user.click(screen.getByText("Toggle"));

    expect(screen.getByTestId("theme").textContent).toBe("light");
    expect(localStorage.getItem("mailwise-theme")).toBe("light");
  });

  it("throws if useTheme is used outside ThemeProvider", () => {
    const consoleError = vi.spyOn(console, "error").mockImplementation(() => {});

    expect(() => render(<ThemeDisplay />)).toThrow(
      "useTheme must be used within ThemeProvider",
    );

    consoleError.mockRestore();
  });
});

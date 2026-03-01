import { describe, it, expect, vi, beforeEach } from "vitest";
import { render, screen } from "@testing-library/react";
import { MemoryRouter, Routes, Route } from "react-router-dom";
import ProtectedRoute from "../ProtectedRoute";
import type { AuthUser } from "@/contexts/AuthContext";

// Mock useAuth
const mockUseAuth = vi.fn<() => {
  user: AuthUser | null;
  isAuthenticated: boolean;
  isLoading: boolean;
  login: (u: string, p: string) => Promise<void>;
  logout: () => Promise<void>;
  getAccessToken: () => string | null;
}>();

vi.mock("@/contexts/AuthContext", () => ({
  useAuth: () => mockUseAuth(),
}));

function renderRoute(
  path: string,
  requiredRole?: "admin" | "reviewer",
) {
  return render(
    <MemoryRouter initialEntries={[path]}>
      <Routes>
        <Route path="/login" element={<div>Login Page</div>} />
        <Route element={<ProtectedRoute requiredRole={requiredRole} />}>
          <Route path="/protected" element={<div>Protected Content</div>} />
        </Route>
      </Routes>
    </MemoryRouter>,
  );
}

describe("ProtectedRoute", () => {
  beforeEach(() => {
    vi.clearAllMocks();
  });

  it("shows loading state while auth is initializing", () => {
    mockUseAuth.mockReturnValue({
      user: null,
      isAuthenticated: false,
      isLoading: true,
      login: vi.fn(),
      logout: vi.fn(),
      getAccessToken: () => null,
    });

    renderRoute("/protected");
    expect(screen.getByLabelText("Loading...")).toBeInTheDocument();
  });

  it("redirects to /login when not authenticated", () => {
    mockUseAuth.mockReturnValue({
      user: null,
      isAuthenticated: false,
      isLoading: false,
      login: vi.fn(),
      logout: vi.fn(),
      getAccessToken: () => null,
    });

    renderRoute("/protected");
    expect(screen.getByText("Login Page")).toBeInTheDocument();
  });

  it("renders protected content when authenticated (no role required)", () => {
    mockUseAuth.mockReturnValue({
      user: { id: "1", username: "testuser", role: "reviewer" },
      isAuthenticated: true,
      isLoading: false,
      login: vi.fn(),
      logout: vi.fn(),
      getAccessToken: () => "token",
    });

    renderRoute("/protected");
    expect(screen.getByText("Protected Content")).toBeInTheDocument();
  });

  it("renders protected content for admin accessing admin route", () => {
    mockUseAuth.mockReturnValue({
      user: { id: "1", username: "admin", role: "admin" },
      isAuthenticated: true,
      isLoading: false,
      login: vi.fn(),
      logout: vi.fn(),
      getAccessToken: () => "token",
    });

    renderRoute("/protected", "admin");
    expect(screen.getByText("Protected Content")).toBeInTheDocument();
  });

  it("shows ForbiddenPage for reviewer accessing admin-only route", () => {
    mockUseAuth.mockReturnValue({
      user: { id: "1", username: "reviewer1", role: "reviewer" },
      isAuthenticated: true,
      isLoading: false,
      login: vi.fn(),
      logout: vi.fn(),
      getAccessToken: () => "token",
    });

    renderRoute("/protected", "admin");
    expect(screen.getByText("403")).toBeInTheDocument();
    expect(screen.getByText("Access denied")).toBeInTheDocument();
  });

  it("admin can access reviewer routes", () => {
    mockUseAuth.mockReturnValue({
      user: { id: "1", username: "admin", role: "admin" },
      isAuthenticated: true,
      isLoading: false,
      login: vi.fn(),
      logout: vi.fn(),
      getAccessToken: () => "token",
    });

    renderRoute("/protected", "reviewer");
    expect(screen.getByText("Protected Content")).toBeInTheDocument();
  });
});

import { describe, it, expect, vi, beforeEach } from "vitest";
import { render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { AuthProvider, useAuth } from "../AuthContext";

// Mock the api modules
vi.mock("@/api/auth", () => ({
  loginRequest: vi.fn(),
  refreshRequest: vi.fn(),
  logoutRequest: vi.fn(),
  getMeRequest: vi.fn(),
}));

vi.mock("@/api/client", () => ({
  configureClient: vi.fn(),
  default: {},
}));

import { loginRequest, logoutRequest, getMeRequest } from "@/api/auth";
import { configureClient } from "@/api/client";

const mockLoginRequest = vi.mocked(loginRequest);
const mockLogoutRequest = vi.mocked(logoutRequest);
const mockGetMeRequest = vi.mocked(getMeRequest);
const mockConfigureClient = vi.mocked(configureClient);

// Helper: JWT with exp claim 900s from now (15 min)
function makeJwt(expInSeconds: number): string {
  const header = btoa(JSON.stringify({ alg: "HS256", typ: "JWT" }));
  const payload = btoa(
    JSON.stringify({ exp: Math.floor(Date.now() / 1000) + expInSeconds, sub: "test-user-id" }),
  );
  const signature = "test-signature";
  return `${header}.${payload}.${signature}`;
}

function AuthDisplay() {
  const { user, isAuthenticated, isLoading, login, logout } = useAuth();
  return (
    <div>
      <span data-testid="loading">{String(isLoading)}</span>
      <span data-testid="authenticated">{String(isAuthenticated)}</span>
      <span data-testid="username">{user?.username ?? "none"}</span>
      <span data-testid="role">{user?.role ?? "none"}</span>
      <button onClick={() => { void login("testuser", "password123"); }}>Login</button>
      <button onClick={() => { void logout(); }}>Logout</button>
    </div>
  );
}

function renderWithAuth() {
  return render(
    <AuthProvider>
      <AuthDisplay />
    </AuthProvider>,
  );
}

describe("AuthContext", () => {
  beforeEach(() => {
    vi.clearAllMocks();
    vi.useFakeTimers({ shouldAdvanceTime: true });
  });

  it("starts not loading and not authenticated", () => {
    renderWithAuth();

    expect(screen.getByTestId("loading").textContent).toBe("false");
    expect(screen.getByTestId("authenticated").textContent).toBe("false");
    expect(screen.getByTestId("username").textContent).toBe("none");
  });

  it("configures the api client on mount", () => {
    renderWithAuth();

    expect(mockConfigureClient).toHaveBeenCalledOnce();
    expect(mockConfigureClient).toHaveBeenCalledWith(
      expect.objectContaining({
        getAccessToken: expect.any(Function),
        getRefreshToken: expect.any(Function),
        onTokenRefreshed: expect.any(Function),
        redirectToLogin: expect.any(Function),
      }),
    );
  });

  it("logs in: calls loginRequest + getMeRequest, sets user state", async () => {
    const jwt = makeJwt(900);
    mockLoginRequest.mockResolvedValueOnce({
      access_token: jwt,
      refresh_token: "refresh-uuid-123",
      token_type: "bearer",
    });
    mockGetMeRequest.mockResolvedValueOnce({
      id: "user-uuid",
      username: "testuser",
      role: "admin",
      is_active: true,
    });

    renderWithAuth();
    const user = userEvent.setup({ advanceTimers: vi.advanceTimersByTime });

    await user.click(screen.getByText("Login"));

    await waitFor(() => {
      expect(screen.getByTestId("authenticated").textContent).toBe("true");
    });
    expect(screen.getByTestId("username").textContent).toBe("testuser");
    expect(screen.getByTestId("role").textContent).toBe("admin");
    expect(mockLoginRequest).toHaveBeenCalledWith({ username: "testuser", password: "password123" });
    expect(mockGetMeRequest).toHaveBeenCalledOnce();
  });

  it("logout clears user state and calls logoutRequest with refresh token", async () => {
    const jwt = makeJwt(900);
    mockLoginRequest.mockResolvedValueOnce({
      access_token: jwt,
      refresh_token: "refresh-uuid-123",
      token_type: "bearer",
    });
    mockGetMeRequest.mockResolvedValueOnce({
      id: "user-uuid",
      username: "testuser",
      role: "reviewer",
      is_active: true,
    });
    mockLogoutRequest.mockResolvedValueOnce(undefined);

    renderWithAuth();
    const user = userEvent.setup({ advanceTimers: vi.advanceTimersByTime });

    // Login first
    await user.click(screen.getByText("Login"));
    await waitFor(() => {
      expect(screen.getByTestId("authenticated").textContent).toBe("true");
    });

    // Logout
    await user.click(screen.getByText("Logout"));

    await waitFor(() => {
      expect(screen.getByTestId("authenticated").textContent).toBe("false");
    });
    expect(screen.getByTestId("username").textContent).toBe("none");
    expect(mockLogoutRequest).toHaveBeenCalledWith("refresh-uuid-123");
  });

  it("access token is NOT in localStorage or sessionStorage", async () => {
    const jwt = makeJwt(900);
    mockLoginRequest.mockResolvedValueOnce({
      access_token: jwt,
      refresh_token: "refresh-uuid-123",
      token_type: "bearer",
    });
    mockGetMeRequest.mockResolvedValueOnce({
      id: "user-uuid",
      username: "testuser",
      role: "admin",
      is_active: true,
    });

    renderWithAuth();
    const user = userEvent.setup({ advanceTimers: vi.advanceTimersByTime });

    await user.click(screen.getByText("Login"));
    await waitFor(() => {
      expect(screen.getByTestId("authenticated").textContent).toBe("true");
    });

    // Verify no tokens in storage
    expect(localStorage.getItem("access_token")).toBeNull();
    expect(localStorage.getItem("refresh_token")).toBeNull();
    expect(sessionStorage.getItem("access_token")).toBeNull();
    expect(sessionStorage.getItem("refresh_token")).toBeNull();

    // Verify no localStorage writes at all during login flow
    const allLocalStorage = Object.keys(localStorage);
    const tokenKeys = allLocalStorage.filter(
      (k) => k.includes("token") || k.includes("jwt") || k.includes("auth"),
    );
    expect(tokenKeys).toHaveLength(0);
  });

  it("getAccessToken returns token after login", async () => {
    const jwt = makeJwt(900);
    mockLoginRequest.mockResolvedValueOnce({
      access_token: jwt,
      refresh_token: "refresh-uuid-123",
      token_type: "bearer",
    });
    mockGetMeRequest.mockResolvedValueOnce({
      id: "user-uuid",
      username: "testuser",
      role: "admin",
      is_active: true,
    });

    renderWithAuth();
    const user = userEvent.setup({ advanceTimers: vi.advanceTimersByTime });

    await user.click(screen.getByText("Login"));
    await waitFor(() => {
      expect(screen.getByTestId("authenticated").textContent).toBe("true");
    });

    // Verify configureClient was called and the getAccessToken function works
    const configCall = mockConfigureClient.mock.calls[0][0];
    expect(configCall.getAccessToken()).toBe(jwt);
  });

  it("throws if useAuth is used outside AuthProvider", () => {
    const consoleError = vi.spyOn(console, "error").mockImplementation(() => {});

    expect(() => render(<AuthDisplay />)).toThrow(
      "useAuth must be used within AuthProvider",
    );

    consoleError.mockRestore();
  });
});

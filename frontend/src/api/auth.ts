// src/api/auth.ts
// Funciones tipadas de auth — tipos desde schema generado
import apiClient from "./client";
import type { components } from "@/types/generated/api";

type LoginRequest = components["schemas"]["LoginRequest"];
type TokenResponse = components["schemas"]["TokenResponse"];
type RefreshRequest = components["schemas"]["RefreshRequest"];
type UserResponse = components["schemas"]["UserResponse"];

export async function loginRequest(body: LoginRequest): Promise<TokenResponse> {
  const { data } = await apiClient.post<TokenResponse>("/auth/login", body);
  return data;
}

export async function refreshRequest(body: RefreshRequest): Promise<TokenResponse> {
  const { data } = await apiClient.post<TokenResponse>("/auth/refresh", body);
  return data;
}

export async function logoutRequest(refreshToken: string): Promise<void> {
  await apiClient.post("/auth/logout", { refresh_token: refreshToken });
}

export async function getMeRequest(): Promise<UserResponse> {
  const { data } = await apiClient.get<UserResponse>("/auth/me");
  return data;
}

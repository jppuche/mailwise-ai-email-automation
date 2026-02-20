// src/api/auth.ts
// Funciones tipadas de auth — tipos desde schema generado (D4: no duplicacion manual)
import apiClient from "./client";
import type { components } from "@/types/generated/api";

type LoginRequest = components["schemas"]["LoginRequest"];
type LoginResponse = components["schemas"]["LoginResponse"];
type RefreshResponse = components["schemas"]["RefreshResponse"];

export async function loginRequest(body: LoginRequest): Promise<LoginResponse> {
  const { data } = await apiClient.post<LoginResponse>("/auth/login", body);
  return data;
}

export async function refreshRequest(): Promise<RefreshResponse> {
  const { data } = await apiClient.post<RefreshResponse>("/auth/refresh");
  return data;
}

export async function logoutRequest(): Promise<void> {
  await apiClient.post("/auth/logout");
}

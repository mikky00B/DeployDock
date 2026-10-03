import { apiClient } from "./client";
import type { AuthResponse, User } from "../types/auth";

export type { AuthResponse };

export type LoginPayload = {
  email: string;
  password: string;
};

export type RegisterPayload = LoginPayload & {
  full_name?: string;
};

export function login(payload: LoginPayload) {
  return apiClient.request<AuthResponse>("/api/v1/auth/login", {
    method: "POST",
    body: payload,
  });
}

export function register(payload: RegisterPayload) {
  return apiClient.request<AuthResponse>("/api/v1/auth/register", {
    method: "POST",
    body: payload,
  });
}

export function getCurrentUser(token: string) {
  return apiClient.request<User>("/api/v1/auth/me", {
    method: "GET",
    token,
  });
}

export function logout(token: string | null) {
  return apiClient.request<{ detail: string }>("/api/v1/auth/logout", {
    method: "POST",
    token,
  });
}

export function verifyEmail(payload: { email: string; code: string }) {
  return apiClient.request<AuthResponse>("/api/v1/auth/verify-email", {
    method: "POST",
    body: payload,
  });
}

export function resendVerification(payload: { email: string }) {
  return apiClient.request<{ detail: string }>("/api/v1/auth/resend-verification", {
    method: "POST",
    body: payload,
  });
}

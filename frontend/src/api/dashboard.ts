import { apiClient } from "./client";
import type { Dashboard } from "../types/dashboard";

export function getDashboard(token: string) {
  return apiClient.request<Dashboard>("/api/v1/dashboard", { method: "GET", token });
}

import { apiClient } from "./client";
import type { Server, ServerConnectionTest, ServerPayload } from "../types/server";

export function listServers(token: string) {
  return apiClient.request<Server[]>("/api/v1/servers", { method: "GET", token });
}

export function getServer(token: string, serverId: string) {
  return apiClient.request<Server>(`/api/v1/servers/${serverId}`, { method: "GET", token });
}

export function createServer(token: string, payload: ServerPayload) {
  return apiClient.request<Server>("/api/v1/servers", { method: "POST", token, body: payload });
}

export function updateServer(token: string, serverId: string, payload: ServerPayload) {
  const body = Object.fromEntries(
    Object.entries(payload).filter(([, value]) => value !== undefined && value !== ""),
  );
  return apiClient.request<Server>(`/api/v1/servers/${serverId}`, { method: "PATCH", token, body });
}

export function deleteServer(token: string, serverId: string) {
  return apiClient.request<void>(`/api/v1/servers/${serverId}`, { method: "DELETE", token });
}

export function testServerConnection(token: string, serverId: string) {
  return apiClient.request<ServerConnectionTest>(`/api/v1/servers/${serverId}/test-connection`, {
    method: "POST",
    token,
  });
}

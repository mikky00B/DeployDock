import { apiClient } from "./client";
import type { Server, ServerConnectionTest, ServerHostKey, ServerPayload } from "../types/server";

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

/**
 * Re-pin the server's SSH host key. Only call this after the operator has
 * confirmed the change is legitimate: an unexpected host key change is
 * indistinguishable from an interception attempt.
 */
export function repinServerHostKey(token: string, serverId: string) {
  return apiClient.request<ServerHostKey>(`/api/v1/servers/${serverId}/host-key`, {
    method: "POST",
    token,
  });
}

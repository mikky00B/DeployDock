import { apiClient } from "./client";
import type { AppPayload, AppServiceLogs, AppServiceRestartResult, AppServiceStatus, DeployableApp } from "../types/app";

export function listApps(token: string) {
  return apiClient.request<DeployableApp[]>("/api/v1/apps", { method: "GET", token });
}

export function getApp(token: string, appId: string) {
  return apiClient.request<DeployableApp>(`/api/v1/apps/${appId}`, { method: "GET", token });
}

export function createApp(token: string, payload: AppPayload) {
  return apiClient.request<DeployableApp>("/api/v1/apps", { method: "POST", token, body: cleanAppPayload(payload) });
}

export function updateApp(token: string, appId: string, payload: AppPayload) {
  return apiClient.request<DeployableApp>(`/api/v1/apps/${appId}`, {
    method: "PATCH",
    token,
    body: cleanAppPayload(payload),
  });
}

export function deleteApp(token: string, appId: string) {
  return apiClient.request<void>(`/api/v1/apps/${appId}`, { method: "DELETE", token });
}

export function checkAppServiceStatus(token: string, appId: string) {
  return apiClient.request<AppServiceStatus>(`/api/v1/apps/${appId}/status`, { method: "GET", token });
}

export function restartAppService(token: string, appId: string) {
  return apiClient.request<AppServiceRestartResult>(`/api/v1/apps/${appId}/restart`, { method: "POST", token });
}

export function getAppServiceLogs(token: string, appId: string) {
  return apiClient.request<AppServiceLogs>(`/api/v1/apps/${appId}/logs`, { method: "GET", token });
}

function cleanAppPayload(payload: AppPayload) {
  return {
    ...payload,
    service_name: payload.service_name || null,
    restart_command: payload.restart_command || null,
    healthcheck_url: payload.healthcheck_url || null,
    port: payload.port || null,
    cpu_limit: payload.cpu_limit || null,
    memory_limit: payload.memory_limit || null,
  };
}

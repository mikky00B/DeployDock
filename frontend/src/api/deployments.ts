import { apiClient } from "./client";
import type { Deployment, DeploymentDetail, DeploymentLog } from "../types/deployment";

export function triggerDeployment(token: string, appId: string) {
  return apiClient.request<Deployment>(`/api/v1/apps/${appId}/deploy`, { method: "POST", token });
}

export function listAppDeployments(token: string, appId: string) {
  return apiClient.request<Deployment[]>(`/api/v1/apps/${appId}/deployments`, { method: "GET", token });
}

export function getDeployment(token: string, deploymentId: string) {
  return apiClient.request<DeploymentDetail>(`/api/v1/deployments/${deploymentId}`, { method: "GET", token });
}

export function getDeploymentLogs(token: string, deploymentId: string) {
  return apiClient.request<DeploymentLog[]>(`/api/v1/deployments/${deploymentId}/logs`, { method: "GET", token });
}

export function triggerRollback(token: string, deploymentId: string) {
  return apiClient.request<Deployment>(`/api/v1/deployments/${deploymentId}/rollback`, { method: "POST", token });
}

export function cancelDeployment(token: string, deploymentId: string) {
  return apiClient.request<Deployment>(`/api/v1/deployments/${deploymentId}/cancel`, { method: "POST", token });
}

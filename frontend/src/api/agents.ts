import { apiClient } from "./client";

export type AgentRegistrationToken = {
  token: string;
  expires_at: string;
};

export function createAgentRegistrationToken(token: string, serverId: string | null) {
  return apiClient.request<AgentRegistrationToken>("/api/v1/agents/registration-tokens", {
    method: "POST",
    token,
    body: { server_id: serverId },
  });
}

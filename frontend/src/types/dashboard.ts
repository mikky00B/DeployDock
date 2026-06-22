import type { DeploymentKind, DeploymentStatus } from "./deployment";

export type DashboardSummary = {
  total_servers: number;
  connected_servers: number;
  total_apps: number;
  deployed_apps: number;
  recent_failures: number;
  latest_deployment_status: DeploymentStatus | null;
};

export type DashboardServer = {
  id: string;
  name: string;
  host: string;
  status: string;
};

export type DashboardApp = {
  id: string;
  name: string;
  service_name: string | null;
  current_commit: string | null;
  last_successful_commit: string | null;
};

export type DashboardDeployment = {
  id: string;
  app_id: string;
  status: DeploymentStatus;
  kind: DeploymentKind;
  commit_sha: string | null;
  created_at: string;
  started_at: string | null;
  finished_at: string | null;
};

export type DashboardAuditLog = {
  id: string;
  owner_id: string;
  action: string;
  entity_type: string;
  entity_id: string;
  metadata_json: Record<string, unknown> | null;
  created_at: string;
};

export type Dashboard = {
  summary: DashboardSummary;
  recent_servers: DashboardServer[];
  recent_apps: DashboardApp[];
  recent_deployments: DashboardDeployment[];
  recent_audit_logs: DashboardAuditLog[];
};

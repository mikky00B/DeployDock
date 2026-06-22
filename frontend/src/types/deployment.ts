export type DeploymentStatus = "pending" | "running" | "success" | "failed" | "canceled";
export type DeploymentKind = "deploy" | "rollback";
export type DeploymentLogStream = "stdout" | "stderr" | "system";

export type Deployment = {
  id: string;
  owner_id: string;
  app_id: string;
  server_id: string;
  status: DeploymentStatus;
  kind: DeploymentKind;
  commit_sha: string | null;
  previous_commit_sha: string | null;
  started_at: string | null;
  finished_at: string | null;
  duration_seconds: number | null;
  triggered_by: string | null;
  exit_code: number | null;
  error_message: string | null;
  created_at: string;
  updated_at: string;
};

export type DeploymentLog = {
  id?: string;
  deployment_id?: string;
  stream: DeploymentLogStream;
  line: string;
  sequence: number;
  created_at?: string;
};

export type DeploymentDetail = Deployment & {
  logs: DeploymentLog[];
};

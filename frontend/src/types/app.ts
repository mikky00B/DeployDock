export type DeployableApp = {
  id: string;
  owner_id: string;
  server_id: string;
  name: string;
  repository_url: string;
  branch: string;
  app_path: string;
  service_name: string | null;
  deploy_command: string;
  restart_command: string | null;
  healthcheck_url: string | null;
  port: number | null;
  cpu_limit: string | null;
  memory_limit: string | null;
  current_commit: string | null;
  last_successful_commit: string | null;
  created_at: string;
  updated_at: string;
};

export type AppPayload = {
  name: string;
  server_id: string;
  repository_url: string;
  branch: string;
  app_path: string;
  service_name?: string | null;
  deploy_command: string;
  restart_command?: string | null;
  healthcheck_url?: string | null;
  port?: number | null;
  cpu_limit?: string | null;
  memory_limit?: string | null;
};

export type AppServiceStatus = {
  service_name: string | null;
  status: string;
};

export type AppServiceRestartResult = {
  service_name: string | null;
  success: boolean;
  exit_code: number;
  message: string;
};

export type AppServiceLogs = {
  service_name: string | null;
  logs: string;
};

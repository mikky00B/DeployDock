import type { Server } from "../../types/server";
import {
  buildHealthcheckUrl,
  resolveDeployUser,
  resolveHost,
  slugify,
  stackDescriptions,
  stripServiceSuffix,
  sudoersWarning,
  systemdSudoersSnippet,
  withSharedDefaults,
  type BootstrapPlan,
  type BootstrapPlanSection,
  type SharedBootstrapFields,
} from "./common";

export type BootstrapFastApiForm = SharedBootstrapFields & {
  stack: "fastapi";
  python_version_label: string;
  virtualenv_path: string;
  requirements_file: string;
  asgi_app: string;
  systemd_service_name: string;
  bind_host: string;
  bind_port: string;
  use_postgresql: boolean;
  use_redis: boolean;
  environment_file_path: string;
  start_command_mode: "gunicorn" | "uvicorn";
  migration_command: string;
};

export function createEmptyBootstrapFastApiForm(serverId = ""): BootstrapFastApiForm {
  return applyFastApiBootstrapDefaults({
    stack: "fastapi",
    server_id: serverId,
    app_name: "",
    repository_url: "",
    branch: "main",
    domain_or_ip: "",
    app_path: "",
    healthcheck_path: "/health",
    python_version_label: "python3",
    virtualenv_path: "venv",
    requirements_file: "requirements.txt",
    asgi_app: "app.main:app",
    systemd_service_name: "",
    bind_host: "127.0.0.1",
    bind_port: "8000",
    use_postgresql: true,
    use_redis: false,
    environment_file_path: "",
    start_command_mode: "gunicorn",
    migration_command: "",
  });
}

export function applyFastApiBootstrapDefaults(form: BootstrapFastApiForm): BootstrapFastApiForm {
  const shared = withSharedDefaults(form, "/health");
  const slug = slugify(shared.app_name) || "example-app";
  return {
    ...shared,
    python_version_label: shared.python_version_label.trim() || "python3",
    virtualenv_path: shared.virtualenv_path.trim() || "venv",
    requirements_file: shared.requirements_file.trim() || "requirements.txt",
    asgi_app: shared.asgi_app.trim() || "app.main:app",
    systemd_service_name: shared.systemd_service_name.trim() || slug,
    bind_host: shared.bind_host.trim() || "127.0.0.1",
    bind_port: shared.bind_port.trim() || "8000",
    environment_file_path: shared.environment_file_path.trim() || `${shared.app_path}/.env`,
    start_command_mode: shared.start_command_mode || "gunicorn",
  };
}

export function generateFastApiBootstrapPlan(rawForm: BootstrapFastApiForm, servers: Server[]): BootstrapPlan {
  const form = applyFastApiBootstrapDefaults(rawForm);
  const deployUser = resolveDeployUser(form, servers);
  const host = resolveHost(form, servers);
  const serviceName = stripServiceSuffix(form.systemd_service_name);
  const healthcheckUrl = buildHealthcheckUrl(host.origin, form.healthcheck_path);
  const venvBin = resolveVenvBin(form.app_path, form.virtualenv_path);
  const activateCommand = `source ${resolveVenvActivate(form.virtualenv_path)}`;
  const restartCommand = `sudo systemctl restart ${serviceName}`;
  const deployCommand = generateFastApiDeployCommand(form, serviceName);
  const execStart = form.start_command_mode === "uvicorn"
    ? `${venvBin}/uvicorn ${form.asgi_app} --host ${form.bind_host} --port ${form.bind_port}`
    : `${venvBin}/gunicorn ${form.asgi_app} -k uvicorn.workers.UvicornWorker --bind ${form.bind_host}:${form.bind_port} --workers 2`;

  const sections: BootstrapPlanSection[] = [
    {
      id: "server-prep",
      title: "Server Preparation Commands",
      language: "bash",
      helper: "Review these commands before running them. They are not executed by DeployDock.",
      content: [
        `sudo mkdir -p ${form.app_path}`,
        `sudo chown -R ${deployUser}:${deployUser} ${form.app_path}`,
        `cd ${form.app_path}`,
        `git clone ${form.repository_url || "<repo_url>"} .`,
        `git checkout ${form.branch}`,
        `${form.python_version_label} -m venv ${form.virtualenv_path}`,
        activateCommand,
        `pip install -r ${form.requirements_file}`,
        "pip install gunicorn uvicorn",
      ].join("\n"),
    },
    {
      id: "environment",
      title: "Environment Checklist",
      language: "env",
      helper: "Use placeholders only in plans. Keep real production secrets in the server-side environment file.",
      content: [
        "APP_ENV=production",
        "SECRET_KEY=change-me",
        ...(form.use_postgresql ? ["DATABASE_URL=postgresql://user:password@localhost:5432/dbname"] : []),
        ...(form.use_redis ? ["REDIS_URL=redis://localhost:6379"] : []),
        `CORS_ORIGINS=${host.origin}`,
      ].join("\n"),
    },
    {
      id: "systemd",
      title: "FastAPI systemd Service",
      language: "ini",
      helper: "Gunicorn with Uvicorn workers is the default. Pure Uvicorn can be used for smaller apps.",
      content: [
        "[Unit]",
        `Description=${form.app_name || "<App Name>"} FastAPI App`,
        "After=network.target",
        "",
        "[Service]",
        `User=${deployUser}`,
        `Group=${deployUser}`,
        `WorkingDirectory=${form.app_path}`,
        `EnvironmentFile=${form.environment_file_path}`,
        `ExecStart=${execStart}`,
        "Restart=always",
        "RestartSec=5",
        "",
        "[Install]",
        "WantedBy=multi-user.target",
        "",
        "# Pure Uvicorn alternative",
        `${venvBin}/uvicorn ${form.asgi_app} --host ${form.bind_host} --port ${form.bind_port}`,
      ].join("\n"),
    },
    {
      id: "nginx",
      title: "Nginx Config",
      language: "nginx",
      content: reverseProxyNginxConfig(host.serverName, form.bind_host, form.bind_port),
    },
    {
      id: "sudoers",
      title: "Sudoers Snippet",
      language: "text",
      helper: sudoersWarning,
      content: systemdSudoersSnippet(deployUser, serviceName),
    },
    {
      id: "deploydock-fields",
      title: "Recommended DeployDock App Fields",
      language: "text",
      content: [
        `Name: ${form.app_name || "<App Name>"}`,
        `Repository URL: ${form.repository_url || "<repo_url>"}`,
        `Branch: ${form.branch}`,
        `App path: ${form.app_path}`,
        `Service name: ${serviceName}`,
        `Healthcheck URL: ${healthcheckUrl}`,
        `Restart command: ${restartCommand}`,
      ].join("\n"),
    },
    {
      id: "deploy-command",
      title: "Recommended Deploy Command",
      language: "bash",
      content: deployCommand,
    },
  ];

  return {
    stack: "fastapi",
    stackLabel: "FastAPI",
    stackDescription: stackDescriptions.fastapi,
    sections,
    appPayload: {
      name: form.app_name,
      server_id: form.server_id,
      repository_url: form.repository_url,
      branch: form.branch,
      app_path: form.app_path,
      service_name: serviceName,
      deploy_command: deployCommand,
      restart_command: restartCommand,
      healthcheck_url: healthcheckUrl,
    },
  };
}

function generateFastApiDeployCommand(form: BootstrapFastApiForm, serviceName: string): string {
  return [
    "set -e",
    "",
    `cd ${form.app_path}`,
    "",
    "git fetch origin",
    `git checkout ${form.branch}`,
    `git pull origin ${form.branch}`,
    "",
    `source ${resolveVenvActivate(form.virtualenv_path)}`,
    "",
    `pip install -r ${form.requirements_file}`,
    "",
    ...(form.migration_command.trim() ? [form.migration_command.trim(), ""] : ["# Optional migrations if the app uses Alembic", "# alembic upgrade head", ""]),
    `sudo systemctl restart ${serviceName}`,
    "",
    "sleep 3",
    "",
    `sudo systemctl is-active ${serviceName}`,
    `sudo systemctl status ${serviceName} --no-pager`,
  ].join("\n");
}

function reverseProxyNginxConfig(serverName: string, bindHost: string, bindPort: string): string {
  return [
    "server {",
    "    listen 80;",
    `    server_name ${serverName};`,
    "",
    "    location / {",
    `        proxy_pass http://${bindHost}:${bindPort};`,
    "        proxy_set_header Host $host;",
    "        proxy_set_header X-Real-IP $remote_addr;",
    "        proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;",
    "        proxy_set_header X-Forwarded-Proto $scheme;",
    "    }",
    "}",
  ].join("\n");
}

function resolveVenvBin(appPath: string, virtualenvPath: string): string {
  const venv = virtualenvPath.trim();
  return venv.startsWith("/") ? `${venv}/bin` : `${appPath}/${venv}/bin`;
}

function resolveVenvActivate(virtualenvPath: string): string {
  const venv = virtualenvPath.trim() || "venv";
  return venv.startsWith("/") ? `${venv}/bin/activate` : `${venv}/bin/activate`;
}

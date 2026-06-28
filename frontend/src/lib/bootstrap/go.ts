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

export type BootstrapGoForm = SharedBootstrapFields & {
  stack: "go";
  binary_name: string;
  build_command: string;
  run_command: string;
  systemd_service_name: string;
  bind_host: string;
  bind_port: string;
  use_nginx: boolean;
  environment_file_path: string;
};

export function createEmptyBootstrapGoForm(serverId = ""): BootstrapGoForm {
  return applyGoBootstrapDefaults({
    stack: "go",
    server_id: serverId,
    app_name: "",
    repository_url: "",
    branch: "main",
    domain_or_ip: "",
    app_path: "",
    healthcheck_path: "/health",
    binary_name: "",
    build_command: "",
    run_command: "",
    systemd_service_name: "",
    bind_host: "127.0.0.1",
    bind_port: "8080",
    use_nginx: true,
    environment_file_path: "",
  });
}

export function applyGoBootstrapDefaults(form: BootstrapGoForm): BootstrapGoForm {
  const shared = withSharedDefaults(form, "/health");
  const slug = slugify(shared.app_name) || "example-app";
  const binaryName = shared.binary_name.trim() || slug;
  return {
    ...shared,
    binary_name: binaryName,
    build_command: shared.build_command.trim() || `go build -o bin/${binaryName} ./cmd/server`,
    run_command: shared.run_command.trim() || `${shared.app_path}/bin/${binaryName}`,
    systemd_service_name: shared.systemd_service_name.trim() || slug,
    bind_host: shared.bind_host.trim() || "127.0.0.1",
    bind_port: shared.bind_port.trim() || "8080",
    environment_file_path: shared.environment_file_path.trim() || `${shared.app_path}/.env`,
  };
}

export function generateGoBootstrapPlan(rawForm: BootstrapGoForm, servers: Server[]): BootstrapPlan {
  const form = applyGoBootstrapDefaults(rawForm);
  const deployUser = resolveDeployUser(form, servers);
  const host = resolveHost(form, servers);
  const serviceName = stripServiceSuffix(form.systemd_service_name);
  const healthcheckUrl = buildHealthcheckUrl(host.origin, form.healthcheck_path);
  const restartCommand = `sudo systemctl restart ${serviceName}`;
  const deployCommand = generateGoDeployCommand(form, serviceName);
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
        "mkdir -p bin",
        "go mod download",
        form.build_command,
      ].join("\n"),
    },
    {
      id: "environment",
      title: "Environment Checklist",
      language: "env",
      helper: "Use placeholders only in plans. Keep real production secrets in the server-side environment file.",
      content: ["APP_ENV=production", `PORT=${form.bind_port}`, "DATABASE_URL=change-me-if-needed", "REDIS_URL=redis://localhost:6379"].join("\n"),
    },
    {
      id: "systemd",
      title: "Go systemd Service",
      language: "ini",
      content: [
        "[Unit]",
        `Description=${form.app_name || "<App Name>"} Go Service`,
        "After=network.target",
        "",
        "[Service]",
        `User=${deployUser}`,
        `Group=${deployUser}`,
        `WorkingDirectory=${form.app_path}`,
        `EnvironmentFile=${form.environment_file_path}`,
        `ExecStart=${form.run_command}`,
        "Restart=always",
        "RestartSec=5",
        "",
        "[Install]",
        "WantedBy=multi-user.target",
      ].join("\n"),
    },
    ...(form.use_nginx
      ? [{
          id: "nginx",
          title: "Nginx Config",
          language: "nginx" as const,
          content: reverseProxyNginxConfig(host.serverName, form.bind_host, form.bind_port),
        }]
      : []),
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
    stack: "go",
    stackLabel: "Go service",
    stackDescription: stackDescriptions.go,
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

function generateGoDeployCommand(form: BootstrapGoForm, serviceName: string): string {
  return [
    "set -e",
    "",
    `cd ${form.app_path}`,
    "",
    "git fetch origin",
    `git checkout ${form.branch}`,
    `git pull origin ${form.branch}`,
    "",
    "go mod download",
    form.build_command,
    "",
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

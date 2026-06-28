import type { Server } from "../../types/server";
import {
  buildHealthcheckUrl,
  resolveDeployUser,
  resolveHost,
  slugify,
  stackDescriptions,
  sudoersWarning,
  withSharedDefaults,
  type BootstrapPlan,
  type BootstrapPlanSection,
  type SharedBootstrapFields,
} from "./common";

export type BootstrapStaticSiteForm = SharedBootstrapFields & {
  stack: "static";
  package_manager: "npm" | "yarn" | "pnpm";
  install_command: string;
  build_command: string;
  build_output_dir: string;
  node_version_label: string;
  nginx_site_name: string;
  spa_fallback: boolean;
};

export function createEmptyBootstrapStaticSiteForm(serverId = ""): BootstrapStaticSiteForm {
  return applyStaticSiteBootstrapDefaults({
    stack: "static",
    server_id: serverId,
    app_name: "",
    repository_url: "",
    branch: "main",
    domain_or_ip: "",
    app_path: "",
    healthcheck_path: "/",
    package_manager: "npm",
    install_command: "npm install",
    build_command: "npm run build",
    build_output_dir: "dist",
    node_version_label: "Node.js 20+",
    nginx_site_name: "",
    spa_fallback: true,
  });
}

export function applyStaticSiteBootstrapDefaults(form: BootstrapStaticSiteForm): BootstrapStaticSiteForm {
  const shared = withSharedDefaults(form, "/");
  const slug = slugify(shared.app_name) || "example-app";
  return {
    ...shared,
    install_command: shared.install_command.trim() || `${shared.package_manager} install`,
    build_command: shared.build_command.trim() || `${shared.package_manager} run build`,
    build_output_dir: shared.build_output_dir.trim() || "dist",
    node_version_label: shared.node_version_label.trim() || "Node.js 20+",
    nginx_site_name: shared.nginx_site_name.trim() || slug,
  };
}

export function generateStaticSiteBootstrapPlan(rawForm: BootstrapStaticSiteForm, servers: Server[]): BootstrapPlan {
  const form = applyStaticSiteBootstrapDefaults(rawForm);
  const deployUser = resolveDeployUser(form, servers);
  const host = resolveHost(form, servers);
  const healthcheckUrl = buildHealthcheckUrl(host.origin, form.healthcheck_path, "/");
  const restartCommand = "sudo nginx -t && sudo systemctl reload nginx";
  const deployCommand = generateStaticDeployCommand(form);
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
        form.install_command,
        form.build_command,
      ].join("\n"),
    },
    {
      id: "nginx",
      title: "Nginx Config",
      language: "nginx",
      content: [
        "server {",
        "    listen 80;",
        `    server_name ${host.serverName};`,
        "",
        `    root ${form.app_path}/${form.build_output_dir};`,
        "    index index.html;",
        "",
        "    location / {",
        `        try_files $uri $uri/ ${form.spa_fallback ? "/index.html" : "=404"};`,
        "    }",
        "}",
      ].join("\n"),
    },
    {
      id: "sudoers",
      title: "Sudoers Snippet",
      language: "text",
      helper: sudoersWarning,
      content: `${deployUser} ALL=(ALL) NOPASSWD: /usr/sbin/nginx -t, /usr/bin/systemctl reload nginx`,
    },
    {
      id: "deploydock-fields",
      title: "Recommended DeployDock App Fields",
      language: "text",
      helper: "Static apps do not need an app-specific systemd service. Use nginx only if your workflow requires a service name.",
      content: [
        `Name: ${form.app_name || "<App Name>"}`,
        `Repository URL: ${form.repository_url || "<repo_url>"}`,
        `Branch: ${form.branch}`,
        `App path: ${form.app_path}`,
        "Service name: blank or nginx",
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
    stack: "static",
    stackLabel: "Static React/Vite",
    stackDescription: stackDescriptions.static,
    sections,
    appPayload: {
      name: form.app_name,
      server_id: form.server_id,
      repository_url: form.repository_url,
      branch: form.branch,
      app_path: form.app_path,
      service_name: null,
      deploy_command: deployCommand,
      restart_command: restartCommand,
      healthcheck_url: healthcheckUrl,
    },
  };
}

function generateStaticDeployCommand(form: BootstrapStaticSiteForm): string {
  return [
    "set -e",
    "",
    `cd ${form.app_path}`,
    "",
    "git fetch origin",
    `git checkout ${form.branch}`,
    `git pull origin ${form.branch}`,
    "",
    form.install_command,
    form.build_command,
    "",
    "sudo nginx -t",
    "sudo systemctl reload nginx",
  ].join("\n");
}

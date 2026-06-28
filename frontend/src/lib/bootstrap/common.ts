import type { AppPayload } from "../../types/app";
import type { Server } from "../../types/server";

export type BootstrapStack = "django" | "fastapi" | "go" | "static";

export type BootstrapPlanSection = {
  id: string;
  title: string;
  language: "bash" | "env" | "ini" | "nginx" | "sql" | "text";
  content: string;
  helper?: string;
};

export type BootstrapPlan = {
  stack: BootstrapStack;
  stackLabel: string;
  stackDescription: string;
  sections: BootstrapPlanSection[];
  appPayload: AppPayload;
};

export type SharedBootstrapFields = {
  stack: BootstrapStack;
  server_id: string;
  app_name: string;
  repository_url: string;
  branch: string;
  domain_or_ip: string;
  app_path: string;
  healthcheck_path: string;
};

export const stackLabels: Record<BootstrapStack, string> = {
  django: "Django",
  fastapi: "FastAPI",
  go: "Go service",
  static: "Static React/Vite",
};

export const stackDescriptions: Record<BootstrapStack, string> = {
  django: "For Django apps served by Gunicorn behind Nginx.",
  fastapi: "For FastAPI apps served by Gunicorn/Uvicorn behind Nginx.",
  go: "For Go services managed by systemd, optionally behind Nginx.",
  static: "For static frontend builds served directly by Nginx.",
};

export function slugify(value: string): string {
  return value
    .trim()
    .toLowerCase()
    .replace(/[^a-z0-9]+/g, "-")
    .replace(/^-+|-+$/g, "");
}

export function normalizePath(value: string, fallback: string): string {
  const trimmed = value.trim() || fallback;
  return trimmed.startsWith("/") ? trimmed : `/${trimmed}`;
}

export function stripServiceSuffix(value: string): string {
  return value.trim().replace(/\.service$/, "");
}

export function parseHostInput(value: string, fallback?: string): { origin: string; serverName: string } {
  const rawHost = value.trim() || fallback?.trim() || "<domain_or_ip>";
  if (rawHost === "<domain_or_ip>") {
    return { origin: "http://<domain_or_ip>", serverName: "<domain_or_ip>" };
  }

  try {
    const parsed = new URL(rawHost.includes("://") ? rawHost : `http://${rawHost}`);
    return {
      origin: `${parsed.protocol}//${parsed.host}`,
      serverName: parsed.hostname,
    };
  } catch {
    const serverName = rawHost.replace(/^https?:\/\//, "").split("/")[0] || "<domain_or_ip>";
    return { origin: `http://${serverName}`, serverName };
  }
}

export function buildHealthcheckUrl(origin: string, healthcheckPath: string, fallback = "/health"): string {
  return `${origin}${normalizePath(healthcheckPath, fallback)}`;
}

export function resolveDeployUser(form: { server_id: string }, servers: Server[]): string {
  return servers.find((candidate) => candidate.id === form.server_id)?.username || "<deploy_user>";
}

export function resolveHost(form: { server_id: string; domain_or_ip: string }, servers: Server[]) {
  const server = servers.find((candidate) => candidate.id === form.server_id);
  return parseHostInput(form.domain_or_ip, server?.host);
}

export function withSharedDefaults<T extends SharedBootstrapFields>(
  form: T,
  fallbackHealthcheckPath: string,
): T {
  const slug = slugify(form.app_name) || "example-app";
  return {
    ...form,
    branch: form.branch.trim() || "main",
    app_path: form.app_path.trim() || `/opt/${slug}`,
    healthcheck_path: normalizePath(form.healthcheck_path, fallbackHealthcheckPath),
  };
}

export function systemdSudoersSnippet(deployUser: string, serviceName: string): string {
  return `${deployUser} ALL=(ALL) NOPASSWD: /usr/bin/systemctl restart ${serviceName}, /usr/bin/systemctl status ${serviceName}, /usr/bin/systemctl is-active ${serviceName}`;
}

export const sudoersWarning =
  "Check actual paths with which systemctl and which nginx. Use sudo visudo. Do not grant broad passwordless sudo.";

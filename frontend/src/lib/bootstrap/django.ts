import type { AppPayload } from "../../types/app";
import type { Server } from "../../types/server";

export type BootstrapDjangoForm = {
  server_id: string;
  app_name: string;
  repository_url: string;
  branch: string;
  domain_or_ip: string;
  app_path: string;
  python_version_label: string;
  virtualenv_path: string;
  django_settings_module: string;
  wsgi_application: string;
  systemd_service_name: string;
  gunicorn_bind: string;
  healthcheck_path: string;
  use_postgresql: boolean;
  use_redis: boolean;
  use_celery: boolean;
  serve_static_files: boolean;
  celery_app_module: string;
  celery_service_name: string;
  static_files_directory: string;
  environment_mode: string;
  requirements_file: string;
  post_migrate_command: string;
};

export type BootstrapPlanSection = {
  id: string;
  title: string;
  language: "bash" | "env" | "ini" | "nginx" | "sql" | "text";
  content: string;
  helper?: string;
};

export type BootstrapDjangoPlan = {
  sections: BootstrapPlanSection[];
  appPayload: AppPayload;
};

export function createEmptyBootstrapDjangoForm(serverId = ""): BootstrapDjangoForm {
  return applyDjangoBootstrapDefaults({
    server_id: serverId,
    app_name: "",
    repository_url: "",
    branch: "main",
    domain_or_ip: "",
    app_path: "",
    python_version_label: "python3",
    virtualenv_path: "venv",
    django_settings_module: "",
    wsgi_application: "config.wsgi:application",
    systemd_service_name: "",
    gunicorn_bind: "127.0.0.1:8010",
    healthcheck_path: "/api/v1/health/",
    use_postgresql: true,
    use_redis: false,
    use_celery: false,
    serve_static_files: true,
    celery_app_module: "config",
    celery_service_name: "",
    static_files_directory: "",
    environment_mode: "production",
    requirements_file: "requirements/dev.txt",
    post_migrate_command: "",
  });
}

export function applyDjangoBootstrapDefaults(form: BootstrapDjangoForm): BootstrapDjangoForm {
  const slug = slugify(form.app_name) || "example-app";
  const appPath = form.app_path.trim() || `/opt/${slug}`;
  const virtualenvPath = form.virtualenv_path.trim() || "venv";
  const serviceName = form.systemd_service_name.trim() || slug;

  return {
    ...form,
    branch: form.branch.trim() || "main",
    app_path: appPath,
    virtualenv_path: virtualenvPath,
    systemd_service_name: serviceName,
    celery_service_name: form.celery_service_name.trim() || `${serviceName}-celery`,
    static_files_directory: form.static_files_directory.trim() || `${appPath}/staticfiles`,
    healthcheck_path: normalizePath(form.healthcheck_path, "/api/v1/health/"),
    gunicorn_bind: form.gunicorn_bind.trim() || "127.0.0.1:8010",
    environment_mode: form.environment_mode.trim() || "production",
    requirements_file: form.requirements_file.trim() || "requirements/dev.txt",
    wsgi_application: form.wsgi_application.trim() || "config.wsgi:application",
    celery_app_module: form.celery_app_module.trim() || "config",
    python_version_label: form.python_version_label.trim() || "python3",
  };
}

export function generateDjangoBootstrapPlan(rawForm: BootstrapDjangoForm, servers: Server[]): BootstrapDjangoPlan {
  const form = applyDjangoBootstrapDefaults(rawForm);
  const server = servers.find((candidate) => candidate.id === form.server_id);
  const deployUser = server?.username || "<deploy_user>";
  const serviceName = stripServiceSuffix(form.systemd_service_name);
  const celeryServiceName = stripServiceSuffix(form.celery_service_name);
  const port = parseBindPort(form.gunicorn_bind);
  const appSlug = slugify(form.app_name) || "example_app";
  const dbName = appSlug.replaceAll("-", "_");
  const dbUser = `${dbName}_user`;
  const host = parseHostInput(form.domain_or_ip, server?.host);
  const healthcheckUrl = buildHealthcheckUrl(host.origin, form.healthcheck_path);
  const venvBin = resolveVenvBin(form.app_path, form.virtualenv_path);
  const activateCommand = `source ${resolveVenvActivate(form.virtualenv_path)}`;
  const restartCommand = `sudo systemctl restart ${serviceName}`;
  const deployCommand = generateDeployCommand(form, serviceName, celeryServiceName);

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
        "pip install gunicorn",
      ].join("\n"),
    },
    {
      id: "environment",
      title: "Environment Checklist",
      language: "env",
      helper:
        "Do not paste production secrets into DeployDock. Keep the real .env on the server by default. If HTTPS is not configured yet, SECURE_SSL_REDIRECT=False is safer for initial testing.",
      content: [
        `DJANGO_ENV=${form.environment_mode}`,
        "DJANGO_SECRET_KEY=change-me",
        `ALLOWED_HOSTS=${host.serverName},localhost,127.0.0.1`,
        `CSRF_TRUSTED_ORIGINS=${host.origin}`,
        "SECURE_SSL_REDIRECT=False",
        ...(form.django_settings_module ? [`DJANGO_SETTINGS_MODULE=${form.django_settings_module}`] : []),
        "",
        ...(form.use_postgresql
          ? ["DB_NAME=", "DB_USER=", "DB_PASSWORD=", "DB_HOST=localhost", "DB_PORT=5432", ""]
          : []),
        ...(form.use_redis || form.use_celery ? ["REDIS_URL=redis://localhost:6379", ""] : []),
      ].join("\n").trimEnd(),
    },
  ];

  if (form.use_postgresql) {
    sections.push({
      id: "postgresql",
      title: "PostgreSQL Setup Commands",
      language: "sql",
      helper: "Use a placeholder password first, then replace it with a strong value directly on the server.",
      content: [
        "sudo -u postgres psql",
        "",
        `CREATE DATABASE ${dbName};`,
        `CREATE USER ${dbUser} WITH PASSWORD '<change-me>';`,
        `GRANT ALL PRIVILEGES ON DATABASE ${dbName} TO ${dbUser};`,
        "",
        `\\c ${dbName}`,
        `GRANT ALL ON SCHEMA public TO ${dbUser};`,
        `ALTER SCHEMA public OWNER TO ${dbUser};`,
      ].join("\n"),
    });
  }

  sections.push(
    {
      id: "django-init",
      title: "Django Initialization Commands",
      language: "bash",
      content: [
        `cd ${form.app_path}`,
        activateCommand,
        "python manage.py migrate",
        "python manage.py collectstatic --noinput",
        ...(form.post_migrate_command.trim() ? [`python manage.py ${form.post_migrate_command.trim()}`] : []),
        "python manage.py createsuperuser",
      ].join("\n"),
    },
    {
      id: "gunicorn-systemd",
      title: "Gunicorn systemd Service",
      language: "ini",
      helper: "The WSGI application is editable. Adjust it if your Django project does not use config.wsgi:application.",
      content: [
        "[Unit]",
        `Description=${form.app_name || "<App Name>"} Django App`,
        `After=${afterServices(form)}`,
        "",
        "[Service]",
        `User=${deployUser}`,
        `Group=${deployUser}`,
        `WorkingDirectory=${form.app_path}`,
        `EnvironmentFile=${form.app_path}/.env`,
        `ExecStart=${venvBin}/gunicorn ${form.wsgi_application} --bind ${form.gunicorn_bind} --workers 3`,
        "Restart=always",
        "RestartSec=5",
        "",
        "[Install]",
        "WantedBy=multi-user.target",
        "",
        "# Install commands",
        `sudo nano /etc/systemd/system/${serviceName}.service`,
        "sudo systemctl daemon-reload",
        `sudo systemctl enable ${serviceName}`,
        `sudo systemctl start ${serviceName}`,
        `sudo systemctl status ${serviceName} --no-pager`,
      ].join("\n"),
    },
  );

  if (form.use_celery) {
    sections.push({
      id: "celery-systemd",
      title: "Celery systemd Service",
      language: "ini",
      helper: "The Celery app module is editable. Adjust it if your Celery app is not exposed from this module.",
      content: [
        "[Unit]",
        `Description=${form.app_name || "<App Name>"} Celery Worker`,
        `After=${afterServices({ ...form, use_redis: true })}`,
        "",
        "[Service]",
        `User=${deployUser}`,
        `Group=${deployUser}`,
        `WorkingDirectory=${form.app_path}`,
        `EnvironmentFile=${form.app_path}/.env`,
        `ExecStart=${venvBin}/celery -A ${form.celery_app_module} worker --loglevel=info`,
        "Restart=always",
        "RestartSec=5",
        "",
        "[Install]",
        "WantedBy=multi-user.target",
        "",
        "# Install commands",
        `sudo nano /etc/systemd/system/${celeryServiceName}.service`,
        "sudo systemctl daemon-reload",
        `sudo systemctl enable ${celeryServiceName}`,
        `sudo systemctl start ${celeryServiceName}`,
        `sudo systemctl status ${celeryServiceName} --no-pager`,
      ].join("\n"),
    });
  }

  sections.push(
    {
      id: "nginx",
      title: "Nginx Config",
      language: "nginx",
      helper:
        "If this VPS hosts multiple apps, use a real domain or subdomain instead of making this the default server. If using only the server IP, server_name must match the request.",
      content: [
        "server {",
        "    listen 80;",
        `    server_name ${host.serverName};`,
        "",
        ...(form.serve_static_files
          ? ["    location /static/ {", `        alias ${form.static_files_directory}/;`, "    }", ""]
          : []),
        "    location / {",
        `        proxy_pass http://127.0.0.1:${port};`,
        "        proxy_set_header Host $host;",
        "        proxy_set_header X-Real-IP $remote_addr;",
        "        proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;",
        "        proxy_set_header X-Forwarded-Proto $scheme;",
        "    }",
        "}",
        "",
        "# Enable commands",
        `sudo nano /etc/nginx/sites-available/${serviceName}`,
        `sudo ln -s /etc/nginx/sites-available/${serviceName} /etc/nginx/sites-enabled/${serviceName}`,
        "sudo nginx -t",
        "sudo systemctl reload nginx",
      ].join("\n"),
    },
    {
      id: "sudoers",
      title: "Sudoers Snippet",
      language: "text",
      helper:
        "Check paths with which systemctl. Use sudo visudo to edit sudoers safely. Do not grant broad NOPASSWD permissions. Add Nginx reload permissions only if you later add Nginx reload to the deploy command.",
      content: [
        `${deployUser} ALL=(root) NOPASSWD: /usr/bin/systemctl restart ${serviceName}, /usr/bin/systemctl status ${serviceName} --no-pager, /usr/bin/systemctl is-active ${serviceName}`,
        ...(form.use_celery
          ? [
              `${deployUser} ALL=(root) NOPASSWD: /usr/bin/systemctl restart ${celeryServiceName}, /usr/bin/systemctl status ${celeryServiceName} --no-pager, /usr/bin/systemctl is-active ${celeryServiceName}`,
            ]
          : []),
      ].join("\n"),
    },
    {
      id: "deploydock-fields",
      title: "Recommended DeployDock App Fields",
      language: "text",
      content: [
        "Name:",
        form.app_name || "<App Name>",
        "",
        "Repository URL:",
        form.repository_url || "<repo_url>",
        "",
        "Branch:",
        form.branch,
        "",
        "Existing app path:",
        form.app_path,
        "",
        "Systemd service name:",
        serviceName,
        "",
        "Healthcheck URL:",
        healthcheckUrl,
        "",
        "Restart command:",
        restartCommand,
      ].join("\n"),
    },
    {
      id: "deploy-command",
      title: "Recommended Deploy Command",
      language: "bash",
      content: deployCommand,
    },
  );

  return {
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

export function slugify(value: string): string {
  return value
    .trim()
    .toLowerCase()
    .replace(/[^a-z0-9]+/g, "-")
    .replace(/^-+|-+$/g, "");
}

function normalizePath(value: string, fallback: string): string {
  const trimmed = value.trim() || fallback;
  return trimmed.startsWith("/") ? trimmed : `/${trimmed}`;
}

function stripServiceSuffix(value: string): string {
  return value.trim().replace(/\.service$/, "");
}

function parseBindPort(bind: string): string {
  const match = bind.trim().match(/:(\d+)$/);
  return match?.[1] ?? "8010";
}

function parseHostInput(value: string, fallback?: string): { origin: string; serverName: string } {
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

function buildHealthcheckUrl(origin: string, healthcheckPath: string): string {
  return `${origin}${normalizePath(healthcheckPath, "/api/v1/health/")}`;
}

function resolveVenvBin(appPath: string, virtualenvPath: string): string {
  const venv = virtualenvPath.trim();
  return venv.startsWith("/") ? `${venv}/bin` : `${appPath}/${venv}/bin`;
}

function resolveVenvActivate(virtualenvPath: string): string {
  const venv = virtualenvPath.trim();
  return venv.startsWith("/") ? `${venv}/bin/activate` : `${venv}/bin/activate`;
}

function afterServices(form: BootstrapDjangoForm): string {
  const services = ["network.target"];
  if (form.use_postgresql) services.push("postgresql.service");
  if (form.use_redis || form.use_celery) services.push("redis-server.service");
  return services.join(" ");
}

function generateDeployCommand(form: BootstrapDjangoForm, serviceName: string, celeryServiceName: string): string {
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
    "python manage.py migrate",
    ...(form.post_migrate_command.trim() ? [`python manage.py ${form.post_migrate_command.trim()} || true`] : []),
    "python manage.py collectstatic --noinput",
    "",
    `sudo systemctl restart ${serviceName}`,
    ...(form.use_celery ? [`sudo systemctl restart ${celeryServiceName}`] : []),
    "",
    "sleep 3",
    "",
    `sudo systemctl is-active ${serviceName}`,
    `sudo systemctl status ${serviceName} --no-pager`,
  ].join("\n");
}

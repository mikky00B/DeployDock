import { useEffect, useMemo, useState, type FormEvent } from "react";

import {
  checkAppServiceStatus,
  createApp,
  deleteApp,
  getApp,
  getAppServiceLogs,
  listApps,
  restartAppService,
  updateApp,
} from "../api/apps";
import { listAppDeployments, triggerDeployment } from "../api/deployments";
import { listServers } from "../api/servers";
import { CodeValue, EmptyState, formatDateTime, StatusBadge } from "../components/common";
import { useAuth } from "../hooks/useAuth";
import {
  applyBootstrapDefaults,
  createEmptyBootstrapForm,
  generateBootstrapPlan,
  stackDescriptions,
  stackLabels,
  slugify,
  type BootstrapForm,
  type BootstrapPlanSection,
  type BootstrapStack,
} from "../lib/bootstrap";
import { navigateTo } from "../routes";
import { DeploymentTable } from "./DeploymentsPage";
import type { AppPayload, DeployableApp } from "../types/app";
import type { Deployment } from "../types/deployment";
import type { Server } from "../types/server";

const emptyAppForm: AppPayload = {
  name: "",
  server_id: "",
  repository_url: "",
  branch: "main",
  app_path: "",
  service_name: "",
  deploy_command: "",
  restart_command: "",
  healthcheck_url: "",
  port: null,
  cpu_limit: "",
  memory_limit: "",
};

export function AppsPage() {
  const { token } = useAuth();
  const [apps, setApps] = useState<DeployableApp[]>([]);
  const [servers, setServers] = useState<Server[]>([]);
  const [form, setForm] = useState<AppPayload>(emptyAppForm);
  const [addMode, setAddMode] = useState<"existing" | "bootstrap">("existing");
  const [bootstrapForm, setBootstrapForm] = useState<BootstrapForm>(() => createEmptyBootstrapForm());
  const [error, setError] = useState<string | null>(null);
  const [notice, setNotice] = useState<string | null>(null);
  const [isLoading, setIsLoading] = useState(true);
  const [isSubmitting, setIsSubmitting] = useState(false);

  useEffect(() => {
    if (!token) return;
    void loadAppWorkspace(token, setApps, setServers, setForm, setBootstrapForm, setError, setIsLoading);
  }, [token]);

  const serverNames = useMemo(() => new Map(servers.map((server) => [server.id, server.name])), [servers]);
  const bootstrapPlan = useMemo(() => generateBootstrapPlan(bootstrapForm, servers), [bootstrapForm, servers]);

  async function handleSubmit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    if (!token) return;
    setError(null);
    setNotice(null);
    setIsSubmitting(true);
    try {
      const created = await createApp(token, form);
      setApps((current) => [created, ...current]);
      setForm({ ...emptyAppForm, server_id: servers[0]?.id ?? "" });
      setNotice("App saved");
    } catch (submitError) {
      setError(submitError instanceof Error ? submitError.message : "Could not create app");
    } finally {
      setIsSubmitting(false);
    }
  }

  async function handleBootstrapSave(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    if (!token) return;
    setError(null);
    setNotice(null);
    setIsSubmitting(true);
    try {
      const created = await createApp(token, bootstrapPlan.appPayload);
      setApps((current) => [created, ...current]);
      setBootstrapForm(createEmptyBootstrapForm(bootstrapForm.stack, servers[0]?.id ?? ""));
      setNotice("Bootstrapped app saved to DeployDock");
    } catch (submitError) {
      setError(submitError instanceof Error ? submitError.message : "Could not save bootstrapped app");
    } finally {
      setIsSubmitting(false);
    }
  }

  async function handleDelete(appId: string) {
    if (!token) return;
    setError(null);
    setNotice(null);
    try {
      await deleteApp(token, appId);
      setApps((current) => current.filter((app) => app.id !== appId));
    } catch (deleteError) {
      setError(deleteError instanceof Error ? deleteError.message : "Could not delete app");
    }
  }

  return (
    <section className="resource-layout">
      <section className="resource-main" aria-labelledby="apps-title">
        <div className="section-heading">
          <div>
            <p className="eyebrow">Projects</p>
            <h2 id="apps-title">Apps</h2>
          </div>
        </div>
        {notice ? <p className="success-message">{notice}</p> : null}
        {error ? <p className="form-error">{error}</p> : null}
        {isLoading ? <p className="muted">Loading apps...</p> : null}
        {!isLoading && apps.length === 0 ? (
          <EmptyState title="No apps yet" body="Connect an existing app or generate a setup plan for a new VPS app." />
        ) : null}
        <div className="resource-list">
          {apps.map((deployableApp) => (
            <article className="resource-row" key={deployableApp.id}>
              <div>
                <button className="link-button title-link" type="button" onClick={() => navigateTo(`/apps/${deployableApp.id}`)}>
                  {deployableApp.name}
                </button>
                <p>{serverNames.get(deployableApp.server_id) ?? "Unknown server"} · {deployableApp.branch} · {deployableApp.app_path}</p>
                <p className="metadata-note">Last successful: <CodeValue value={deployableApp.last_successful_commit} /></p>
              </div>
              <StatusBadge label={deployableApp.service_name ?? "no service"} />
              <div className="row-actions">
                <button className="danger-button" type="button" onClick={() => void handleDelete(deployableApp.id)}>
                  Delete
                </button>
              </div>
            </article>
          ))}
        </div>
        {addMode === "bootstrap" ? (
          <BootstrapPlanPreview
            sections={bootstrapPlan.sections}
            appPayload={bootstrapPlan.appPayload}
            stackLabel={bootstrapPlan.stackLabel}
            stackDescription={bootstrapPlan.stackDescription}
          />
        ) : null}
      </section>
      <aside className="form-panel" aria-labelledby="add-app-title">
        <h2 id="add-app-title">Add app</h2>
        <ModeSelector mode={addMode} onChange={setAddMode} />
        {addMode === "existing" ? (
          <>
            <p className="form-helper">
              Register an app that already lives on your server. DeployDock runs your existing deploy command in the app path.
            </p>
            <AppForm
              form={form}
              isSubmitting={isSubmitting}
              servers={servers}
              submitLabel="Add app"
              onChange={setForm}
              onSubmit={handleSubmit}
            />
          </>
        ) : (
          <BootstrapFormPanel
            form={bootstrapForm}
            isSubmitting={isSubmitting}
            servers={servers}
            onChange={setBootstrapForm}
            onSubmit={handleBootstrapSave}
          />
        )}
      </aside>
    </section>
  );
}

export function AppDetailPage({ appId }: { appId: string }) {
  const { token } = useAuth();
  const [deployableApp, setDeployableApp] = useState<DeployableApp | null>(null);
  const [deployments, setDeployments] = useState<Deployment[]>([]);
  const [servers, setServers] = useState<Server[]>([]);
  const [form, setForm] = useState<AppPayload>(emptyAppForm);
  const [notice, setNotice] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [serviceStatus, setServiceStatus] = useState<string | null>(null);
  const [serviceLogs, setServiceLogs] = useState<string | null>(null);
  const [isLoading, setIsLoading] = useState(true);
  const [isDeploying, setIsDeploying] = useState(false);
  const [isSaving, setIsSaving] = useState(false);
  const [isCheckingStatus, setIsCheckingStatus] = useState(false);
  const [isRestarting, setIsRestarting] = useState(false);
  const [isLoadingLogs, setIsLoadingLogs] = useState(false);

  useEffect(() => {
    if (!token) return;
    setIsLoading(true);
    Promise.all([getApp(token, appId), listServers(token), listAppDeployments(token, appId)])
      .then(([loadedApp, loadedServers, loadedDeployments]) => {
        setDeployableApp(loadedApp);
        setServers(loadedServers);
        setDeployments(loadedDeployments);
        setForm(appToForm(loadedApp));
        setError(null);
      })
      .catch((loadError: unknown) => setError(loadError instanceof Error ? loadError.message : "Could not load app"))
      .finally(() => setIsLoading(false));
  }, [appId, token]);

  async function handleSubmit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    if (!token || !deployableApp) return;
    setNotice(null);
    setError(null);
    setIsSaving(true);
    try {
      const updated = await updateApp(token, deployableApp.id, form);
      setDeployableApp(updated);
      setForm(appToForm(updated));
      setNotice("App updated");
    } catch (submitError) {
      setError(submitError instanceof Error ? submitError.message : "Could not update app");
    } finally {
      setIsSaving(false);
    }
  }

  async function handleDeploy() {
    if (!token || !deployableApp) return;
    setNotice(null);
    setError(null);
    setIsDeploying(true);
    try {
      const deployment = await triggerDeployment(token, deployableApp.id);
      setDeployments((current) => [deployment, ...current]);
      navigateTo(`/deployments/${deployment.id}`);
    } catch (deployError) {
      setError(deployError instanceof Error ? deployError.message : "Could not start deployment");
    } finally {
      setIsDeploying(false);
    }
  }

  async function handleCheckStatus() {
    if (!token || !deployableApp) return;
    setNotice(null);
    setError(null);
    setIsCheckingStatus(true);
    try {
      const result = await checkAppServiceStatus(token, deployableApp.id);
      setServiceStatus(result.status);
      setNotice(`Service status: ${result.status}`);
    } catch (statusError) {
      setError(statusError instanceof Error ? statusError.message : "Could not check service status");
    } finally {
      setIsCheckingStatus(false);
    }
  }

  async function handleRestart() {
    if (!token || !deployableApp) return;
    const confirmed = window.confirm("Restart this app service on the remote server?");
    if (!confirmed) return;
    setNotice(null);
    setError(null);
    setIsRestarting(true);
    try {
      const result = await restartAppService(token, deployableApp.id);
      setNotice(result.message);
      setServiceStatus(result.success ? "restarted" : "restart failed");
    } catch (restartError) {
      setError(restartError instanceof Error ? restartError.message : "Could not restart service");
    } finally {
      setIsRestarting(false);
    }
  }

  async function handleLoadLogs() {
    if (!token || !deployableApp) return;
    setNotice(null);
    setError(null);
    setIsLoadingLogs(true);
    try {
      const result = await getAppServiceLogs(token, deployableApp.id);
      setServiceLogs(result.logs);
      setNotice("Recent service logs loaded");
    } catch (logsError) {
      setError(logsError instanceof Error ? logsError.message : "Could not load service logs");
    } finally {
      setIsLoadingLogs(false);
    }
  }

  if (isLoading) {
    return <p className="muted">Loading app...</p>;
  }

  if (!deployableApp) {
    return <p className="form-error">{error ?? "App not found"}</p>;
  }

  const serverName = servers.find((server) => server.id === deployableApp.server_id)?.name ?? "Unknown server";
  const hasAppService = Boolean(deployableApp.service_name);
  const canRestart = Boolean(deployableApp.restart_command || deployableApp.service_name);

  const appNames = new Map([[deployableApp.id, deployableApp.name]]);

  return (
    <section className="detail-layout">
      <section className="detail-panel">
        <button className="link-button" type="button" onClick={() => navigateTo("/apps")}>
          Back to apps
        </button>
        <div className="detail-header">
          <div>
            <p className="eyebrow">App operations</p>
            <h2>{deployableApp.name}</h2>
            <p>{serverName} · {deployableApp.branch} · {deployableApp.app_path}</p>
          </div>
          <StatusBadge label={deployableApp.service_name ?? "no service"} />
        </div>
        <section className="operation-banner">
          <div>
            <h3>Deploy current app workflow</h3>
            <p>Runs the configured deploy command on the server and streams logs into deployment history.</p>
          </div>
          <button className="primary-inline-button" disabled={isDeploying} type="button" onClick={() => void handleDeploy()}>
            {isDeploying ? "Starting deployment" : "Deploy app"}
          </button>
        </section>
        <section className="nested-section" aria-labelledby="app-overview-title">
          <h2 id="app-overview-title">Overview</h2>
        <dl className="detail-list">
          <div><dt>Repository</dt><dd>{deployableApp.repository_url}</dd></div>
          <div><dt>Current commit</dt><dd><CodeValue value={deployableApp.current_commit} /></dd></div>
          <div><dt>Last successful commit</dt><dd><CodeValue value={deployableApp.last_successful_commit} /></dd></div>
          <div><dt>Healthcheck URL</dt><dd>{deployableApp.healthcheck_url ? <a href={deployableApp.healthcheck_url} target="_blank" rel="noreferrer">{deployableApp.healthcheck_url}</a> : "Not configured"}</dd></div>
          <div><dt>Updated</dt><dd>{formatDateTime(deployableApp.updated_at)}</dd></div>
        </dl>
        </section>
        {notice ? <p className="success-message">{notice}</p> : null}
        {error ? <p className="form-error">{error}</p> : null}
        <section className="nested-section" aria-labelledby="service-controls-title">
          <div className="section-heading">
            <div>
              <h2 id="service-controls-title">Service controls</h2>
              <p className="muted">Operations run against the configured remote server service.</p>
            </div>
            {serviceStatus ? <StatusBadge label={serviceStatus} tone={serviceStatusTone(serviceStatus)} /> : null}
          </div>
          <div className="detail-actions">
            <button className="secondary-button" disabled={isCheckingStatus || !hasAppService} type="button" onClick={() => void handleCheckStatus()}>
              {isCheckingStatus ? "Checking" : "Check status"}
            </button>
            <button className="danger-button" disabled={isRestarting || !canRestart} type="button" onClick={() => void handleRestart()}>
              {isRestarting ? "Restarting" : "Restart service"}
            </button>
            <button className="secondary-button" disabled={isLoadingLogs || !hasAppService} type="button" onClick={() => void handleLoadLogs()}>
              {isLoadingLogs ? "Loading logs" : "View recent logs"}
            </button>
          </div>
          {!hasAppService ? <p className="muted">No app service configured. Static apps can still use a restart command such as an Nginx reload.</p> : null}
          {serviceLogs !== null ? (
            <pre className="service-log-viewer">
              <code>{serviceLogs || "No recent service logs returned."}</code>
            </pre>
          ) : null}
        </section>
        <section className="nested-section" aria-labelledby="app-deployments-title">
          <h2 id="app-deployments-title">Deployment history</h2>
          {deployments.length === 0 ? <EmptyState title="No deployments yet" body="Trigger your first deployment from this app page." /> : null}
          <DeploymentTable deployments={deployments} appNames={appNames} />
        </section>
      </section>
      <aside className="form-panel">
        <h2>Edit app</h2>
        <p className="form-helper">
          Keep secrets on the server by default. Use this form for repository, path, service, and command orchestration.
        </p>
        <AppForm
          form={form}
          isSubmitting={isSaving}
          servers={servers}
          submitLabel="Save app"
          onChange={setForm}
          onSubmit={handleSubmit}
        />
      </aside>
    </section>
  );
}

function AppForm({
  form,
  isSubmitting,
  servers,
  submitLabel,
  onChange,
  onSubmit,
}: {
  form: AppPayload;
  isSubmitting: boolean;
  servers: Server[];
  submitLabel: string;
  onChange: (form: AppPayload) => void;
  onSubmit: (event: FormEvent<HTMLFormElement>) => void;
}) {
  return (
    <form className="resource-form" onSubmit={onSubmit}>
      <label>
        Server
        <select required value={form.server_id} onChange={(event) => onChange({ ...form, server_id: event.target.value })}>
          <option value="">Select server</option>
          {servers.map((server) => (
            <option key={server.id} value={server.id}>{server.name}</option>
          ))}
        </select>
      </label>
      <label>Name<input required value={form.name} onChange={(event) => onChange({ ...form, name: event.target.value })} /></label>
      <label>Repository URL<input required placeholder="git@github.com:org/repo.git" value={form.repository_url} onChange={(event) => onChange({ ...form, repository_url: event.target.value })} /></label>
      <label>Branch<input required placeholder="main" value={form.branch} onChange={(event) => onChange({ ...form, branch: event.target.value })} /></label>
      <label>
        Existing app path
        <input required placeholder="/opt/my-app" value={form.app_path} onChange={(event) => onChange({ ...form, app_path: event.target.value })} />
        <span className="field-helper">Example: /opt/watchdog. Deploy commands run from this directory.</span>
      </label>
      <label>
        systemd service name
        <input placeholder="my-app.service" value={form.service_name ?? ""} onChange={(event) => onChange({ ...form, service_name: event.target.value })} />
        <span className="field-helper">Optional, used for status, restart, and journal logs.</span>
      </label>
      <label>
        Healthcheck URL
        <input placeholder="https://app.example.com/api/v1/health/" value={form.healthcheck_url ?? ""} onChange={(event) => onChange({ ...form, healthcheck_url: event.target.value })} />
        <span className="field-helper">
          Use the public URL DeployDock can reach, for example https://app.example.com/api/v1/health/. For apps behind Nginx,
          make sure the domain or IP routes to the app.
        </span>
        {form.healthcheck_url?.endsWith("/health/") ? (
          <span className="field-warning">Confirm this route exists. Some APIs expose health at /api/v1/health/.</span>
        ) : null}
      </label>
      <label>
        Existing deploy command
        <textarea className="command-textarea" required rows={10} placeholder={`git pull origin main\nsource .venv/bin/activate\npython manage.py migrate\nsudo systemctl restart my-app`} value={form.deploy_command} onChange={(event) => onChange({ ...form, deploy_command: event.target.value })} />
        <span className="field-helper">Runs from the app path. Whitespace and line breaks are preserved.</span>
      </label>
      <label>Restart command<textarea className="command-textarea" rows={4} placeholder="sudo systemctl restart my-app" value={form.restart_command ?? ""} onChange={(event) => onChange({ ...form, restart_command: event.target.value })} /></label>
      <label>
        Container port
        <input
          type="number"
          min={1}
          max={65535}
          placeholder="8080"
          value={form.port ?? ""}
          onChange={(event) => onChange({ ...form, port: event.target.value === "" ? null : Number(event.target.value) })}
        />
        <span className="field-helper">
          The TCP port your app listens on inside its container. Required for agent-driven deployments; ignored by the SSH
          workflow.
        </span>
      </label>
      <label>
        CPU limit
        <input placeholder="1.5" value={form.cpu_limit ?? ""} onChange={(event) => onChange({ ...form, cpu_limit: event.target.value })} />
        <span className="field-helper">Optional, agent deployments only. Docker --cpus value, e.g. 1.5.</span>
      </label>
      <label>
        Memory limit
        <input placeholder="512m" value={form.memory_limit ?? ""} onChange={(event) => onChange({ ...form, memory_limit: event.target.value })} />
        <span className="field-helper">Optional, agent deployments only. Docker --memory value, e.g. 512m or 1g.</span>
      </label>
      <button className="primary-button" disabled={isSubmitting || servers.length === 0} type="submit">
        {isSubmitting ? "Saving" : submitLabel}
      </button>
    </form>
  );
}

function ModeSelector({
  mode,
  onChange,
}: {
  mode: "existing" | "bootstrap";
  onChange: (mode: "existing" | "bootstrap") => void;
}) {
  return (
    <div className="mode-selector" role="group" aria-label="App creation mode">
      <button
        className={mode === "existing" ? "active" : ""}
        type="button"
        onClick={() => onChange("existing")}
      >
        <strong>Connect existing app</strong>
        <span>The app already exists on the server.</span>
      </button>
      <button
        className={mode === "bootstrap" ? "active" : ""}
        type="button"
        onClick={() => onChange("bootstrap")}
      >
        <strong>Bootstrap new app</strong>
        <span>Generate a setup plan from a GitHub repo.</span>
      </button>
    </div>
  );
}

function BootstrapFormPanel({
  form,
  isSubmitting,
  servers,
  onChange,
  onSubmit,
}: {
  form: BootstrapForm;
  isSubmitting: boolean;
  servers: Server[];
  onChange: (form: BootstrapForm) => void;
  onSubmit: (event: FormEvent<HTMLFormElement>) => void;
}) {
  function update(updates: Partial<BootstrapForm>) {
    onChange({ ...form, ...updates } as BootstrapForm);
  }

  function changeStack(stack: BootstrapStack) {
    const nextForm = resetDerivedStackDefaults(createEmptyBootstrapForm(stack, form.server_id));
    onChange(applyBootstrapDefaults({
      ...nextForm,
      app_name: form.app_name,
      repository_url: form.repository_url,
      branch: form.branch,
      domain_or_ip: form.domain_or_ip,
      app_path: form.app_path,
    } as BootstrapForm));
  }

  function updateAppName(appName: string) {
    const oldSlug = slugify(form.app_name) || "example-app";
    const nextSlug = slugify(appName) || "example-app";
    const updates: Partial<BootstrapForm> = {
      app_name: appName,
      app_path: form.app_path === `/opt/${oldSlug}` ? `/opt/${nextSlug}` : form.app_path,
    };

    if (form.stack === "django") {
      Object.assign(updates, {
        systemd_service_name: form.systemd_service_name === oldSlug ? nextSlug : form.systemd_service_name,
        celery_service_name: form.celery_service_name === `${oldSlug}-celery` ? `${nextSlug}-celery` : form.celery_service_name,
        static_files_directory:
          form.static_files_directory === `/opt/${oldSlug}/staticfiles`
            ? `/opt/${nextSlug}/staticfiles`
            : form.static_files_directory,
      });
    }
    if (form.stack === "fastapi" || form.stack === "go") {
      Object.assign(updates, {
        systemd_service_name: form.systemd_service_name === oldSlug ? nextSlug : form.systemd_service_name,
      });
    }
    if (form.stack === "go") {
      Object.assign(updates, {
        binary_name: form.binary_name === oldSlug ? nextSlug : form.binary_name,
        build_command: form.build_command === `go build -o bin/${oldSlug} ./cmd/server` ? `go build -o bin/${nextSlug} ./cmd/server` : form.build_command,
        run_command: form.run_command === `${form.app_path}/bin/${oldSlug}` ? `${updates.app_path ?? form.app_path}/bin/${nextSlug}` : form.run_command,
      });
    }
    if (form.stack === "static") {
      Object.assign(updates, {
        nginx_site_name: form.nginx_site_name === oldSlug ? nextSlug : form.nginx_site_name,
      });
    }

    update(updates);
  }

  return (
    <>
      <p className="form-helper">
        Bootstrap mode helps you prepare a new VPS-hosted app for DeployDock. It generates setup commands and config files,
        but you stay in control of what runs on your server.
      </p>
      <p className="field-warning">
        Bootstrap Mode generates a setup plan only. Review commands before running them on your server.
      </p>
      <form className="resource-form" onSubmit={onSubmit}>
        <label>
          Choose stack
          <select value={form.stack} onChange={(event) => changeStack(event.target.value as BootstrapStack)}>
            <option value="django">{stackLabels.django}</option>
            <option value="fastapi">{stackLabels.fastapi}</option>
            <option value="go">{stackLabels.go}</option>
            <option value="static">{stackLabels.static}</option>
          </select>
          <span className="field-helper">{stackDescriptions[form.stack]}</span>
        </label>
        <label>
          Server
          <select required value={form.server_id} onChange={(event) => update({ server_id: event.target.value })}>
            <option value="">Select server</option>
            {servers.map((server) => (
              <option key={server.id} value={server.id}>{server.name} ({server.username})</option>
            ))}
          </select>
        </label>
        <label>App name<input required value={form.app_name} onChange={(event) => updateAppName(event.target.value)} /></label>
        <label>Repository URL<input required placeholder="git@github.com:org/repo.git" value={form.repository_url} onChange={(event) => update({ repository_url: event.target.value })} /></label>
        <label>Branch<input required value={form.branch} onChange={(event) => update({ branch: event.target.value })} /></label>
        <label>Domain or server IP<input required placeholder="app.example.com" value={form.domain_or_ip} onChange={(event) => update({ domain_or_ip: event.target.value })} /></label>
        <label>
          App path
          <input required value={form.app_path} onChange={(event) => update({ app_path: event.target.value })} />
          <span className="field-helper">Default: /opt/&lt;slugified-app-name&gt;. Review ownership before running setup commands.</span>
        </label>
        <label>Healthcheck path<input required value={form.healthcheck_path} onChange={(event) => update({ healthcheck_path: event.target.value })} /></label>

        {form.stack === "django" ? <DjangoBootstrapFields form={form} update={update} /> : null}
        {form.stack === "fastapi" ? <FastApiBootstrapFields form={form} update={update} /> : null}
        {form.stack === "go" ? <GoBootstrapFields form={form} update={update} /> : null}
        {form.stack === "static" ? <StaticBootstrapFields form={form} update={update} /> : null}

        <button className="secondary-button" type="button" onClick={() => onChange(applyBootstrapDefaults(form))}>
          Apply recommended defaults
        </button>
        <button className="primary-button" disabled={isSubmitting || servers.length === 0} type="submit">
          {isSubmitting ? "Saving" : "Save app to DeployDock"}
        </button>
      </form>
    </>
  );
}

function resetDerivedStackDefaults(form: BootstrapForm): BootstrapForm {
  if (form.stack === "django") {
    return { ...form, systemd_service_name: "", celery_service_name: "", static_files_directory: "" };
  }
  if (form.stack === "fastapi") {
    return { ...form, systemd_service_name: "", environment_file_path: "" };
  }
  if (form.stack === "go") {
    return { ...form, binary_name: "", build_command: "", run_command: "", systemd_service_name: "", environment_file_path: "" };
  }
  return { ...form, nginx_site_name: "" };
}

function DjangoBootstrapFields({ form, update }: { form: Extract<BootstrapForm, { stack: "django" }>; update: (updates: Partial<BootstrapForm>) => void }) {
  return (
    <>
      <label>Python version label<input required value={form.python_version_label} onChange={(event) => update({ python_version_label: event.target.value })} /></label>
      <label>Virtualenv path/name<input required value={form.virtualenv_path} onChange={(event) => update({ virtualenv_path: event.target.value })} /></label>
      <label>Django settings module<input placeholder="config.settings.production" value={form.django_settings_module} onChange={(event) => update({ django_settings_module: event.target.value })} /></label>
      <label>
        WSGI application
        <input required value={form.wsgi_application} onChange={(event) => update({ wsgi_application: event.target.value })} />
        <span className="field-helper">Example: config.wsgi:application. Adjust this for your Django project layout.</span>
      </label>
      <label>systemd service name<input required value={form.systemd_service_name} onChange={(event) => update({ systemd_service_name: event.target.value })} /></label>
      <label>
        Gunicorn bind
        <input required value={form.gunicorn_bind} onChange={(event) => update({ gunicorn_bind: event.target.value })} />
        <span className="field-helper">Default placeholder: 127.0.0.1:8010. Change it if another app already uses that port.</span>
      </label>
      <label>Static files directory<input value={form.static_files_directory} onChange={(event) => update({ static_files_directory: event.target.value })} /></label>
      <label>Environment mode<input required value={form.environment_mode} onChange={(event) => update({ environment_mode: event.target.value })} /></label>
      <label>Requirements file<input required value={form.requirements_file} onChange={(event) => update({ requirements_file: event.target.value })} /></label>
      <label>Optional post-migrate command<input placeholder="seed_roles" value={form.post_migrate_command} onChange={(event) => update({ post_migrate_command: event.target.value })} /></label>
      <div className="toggle-group">
        <label><input type="checkbox" checked={form.use_postgresql} onChange={(event) => update({ use_postgresql: event.target.checked })} /> Use PostgreSQL</label>
        <label><input type="checkbox" checked={form.use_redis} onChange={(event) => update({ use_redis: event.target.checked })} /> Use Redis</label>
        <label><input type="checkbox" checked={form.use_celery} onChange={(event) => update({ use_celery: event.target.checked })} /> Use Celery worker</label>
        <label><input type="checkbox" checked={form.serve_static_files} onChange={(event) => update({ serve_static_files: event.target.checked })} /> Serve static files through Nginx</label>
      </div>
      {form.use_celery ? (
        <>
          <label>Celery app module<input required value={form.celery_app_module} onChange={(event) => update({ celery_app_module: event.target.value })} /></label>
          <label>Celery service name<input required value={form.celery_service_name} onChange={(event) => update({ celery_service_name: event.target.value })} /></label>
        </>
      ) : null}
    </>
  );
}

function FastApiBootstrapFields({ form, update }: { form: Extract<BootstrapForm, { stack: "fastapi" }>; update: (updates: Partial<BootstrapForm>) => void }) {
  return (
    <>
      <label>Python version label<input required value={form.python_version_label} onChange={(event) => update({ python_version_label: event.target.value })} /></label>
      <label>Virtualenv name/path<input required value={form.virtualenv_path} onChange={(event) => update({ virtualenv_path: event.target.value })} /></label>
      <label>Requirements file<input required value={form.requirements_file} onChange={(event) => update({ requirements_file: event.target.value })} /></label>
      <label>ASGI app import path<input required value={form.asgi_app} onChange={(event) => update({ asgi_app: event.target.value })} /></label>
      <label>systemd service name<input required value={form.systemd_service_name} onChange={(event) => update({ systemd_service_name: event.target.value })} /></label>
      <label>Bind host<input required value={form.bind_host} onChange={(event) => update({ bind_host: event.target.value })} /></label>
      <label>Bind port<input required value={form.bind_port} onChange={(event) => update({ bind_port: event.target.value })} /></label>
      <label>Environment file path<input required value={form.environment_file_path} onChange={(event) => update({ environment_file_path: event.target.value })} /></label>
      <label>
        Start command mode
        <select value={form.start_command_mode} onChange={(event) => update({ start_command_mode: event.target.value as "gunicorn" | "uvicorn" })}>
          <option value="gunicorn">Gunicorn + Uvicorn worker</option>
          <option value="uvicorn">Pure Uvicorn</option>
        </select>
      </label>
      <label>Migration command<input placeholder="alembic upgrade head" value={form.migration_command} onChange={(event) => update({ migration_command: event.target.value })} /></label>
      <div className="toggle-group">
        <label><input type="checkbox" checked={form.use_postgresql} onChange={(event) => update({ use_postgresql: event.target.checked })} /> Use PostgreSQL</label>
        <label><input type="checkbox" checked={form.use_redis} onChange={(event) => update({ use_redis: event.target.checked })} /> Use Redis</label>
      </div>
    </>
  );
}

function GoBootstrapFields({ form, update }: { form: Extract<BootstrapForm, { stack: "go" }>; update: (updates: Partial<BootstrapForm>) => void }) {
  return (
    <>
      <label>Go binary name<input required value={form.binary_name} onChange={(event) => update({ binary_name: event.target.value })} /></label>
      <label>Build command<textarea className="command-textarea" required rows={3} value={form.build_command} onChange={(event) => update({ build_command: event.target.value })} /></label>
      <label>Run command or binary path<input required value={form.run_command} onChange={(event) => update({ run_command: event.target.value })} /></label>
      <label>systemd service name<input required value={form.systemd_service_name} onChange={(event) => update({ systemd_service_name: event.target.value })} /></label>
      <label>Bind host<input required value={form.bind_host} onChange={(event) => update({ bind_host: event.target.value })} /></label>
      <label>Bind port<input required value={form.bind_port} onChange={(event) => update({ bind_port: event.target.value })} /></label>
      <label>Environment file path<input required value={form.environment_file_path} onChange={(event) => update({ environment_file_path: event.target.value })} /></label>
      <div className="toggle-group">
        <label><input type="checkbox" checked={form.use_nginx} onChange={(event) => update({ use_nginx: event.target.checked })} /> Use Nginx reverse proxy</label>
      </div>
    </>
  );
}

function StaticBootstrapFields({ form, update }: { form: Extract<BootstrapForm, { stack: "static" }>; update: (updates: Partial<BootstrapForm>) => void }) {
  return (
    <>
      <label>
        Package manager
        <select value={form.package_manager} onChange={(event) => update({ package_manager: event.target.value as "npm" | "yarn" | "pnpm" })}>
          <option value="npm">npm</option>
          <option value="yarn">yarn</option>
          <option value="pnpm">pnpm</option>
        </select>
      </label>
      <label>Install command<input required value={form.install_command} onChange={(event) => update({ install_command: event.target.value })} /></label>
      <label>Build command<input required value={form.build_command} onChange={(event) => update({ build_command: event.target.value })} /></label>
      <label>Build output directory<input required value={form.build_output_dir} onChange={(event) => update({ build_output_dir: event.target.value })} /></label>
      <label>Node version label<input required value={form.node_version_label} onChange={(event) => update({ node_version_label: event.target.value })} /></label>
      <label>Nginx site name<input required value={form.nginx_site_name} onChange={(event) => update({ nginx_site_name: event.target.value })} /></label>
      <div className="toggle-group">
        <label><input type="checkbox" checked={form.spa_fallback} onChange={(event) => update({ spa_fallback: event.target.checked })} /> SPA fallback</label>
      </div>
    </>
  );
}

function BootstrapPlanPreview({
  sections,
  appPayload,
  stackLabel,
  stackDescription,
}: {
  sections: BootstrapPlanSection[];
  appPayload: AppPayload;
  stackLabel: string;
  stackDescription: string;
}) {
  return (
    <section className="nested-section bootstrap-plan" aria-labelledby="bootstrap-plan-title">
      <div className="section-heading">
        <div>
          <p className="eyebrow">Bootstrap new app</p>
          <h2 id="bootstrap-plan-title">{stackLabel} setup plan</h2>
          <p className="muted">
            {stackDescription} Bootstrap Mode generates a setup plan only. Review commands before running them on your server.
          </p>
        </div>
      </div>
      <div className="bootstrap-summary">
        <div><span>Name</span><strong>{appPayload.name || "Not set"}</strong></div>
        <div><span>App path</span><strong>{appPayload.app_path}</strong></div>
        <div><span>Service</span><strong>{appPayload.service_name || "No app service configured"}</strong></div>
        <div><span>Healthcheck</span><strong>{appPayload.healthcheck_url}</strong></div>
      </div>
      <div className="plan-section-list">
        {sections.map((section) => (
          <PlanSection key={section.id} section={section} />
        ))}
      </div>
    </section>
  );
}

function PlanSection({ section }: { section: BootstrapPlanSection }) {
  const [copyLabel, setCopyLabel] = useState("Copy");

  async function handleCopy() {
    try {
      await navigator.clipboard.writeText(section.content);
      setCopyLabel("Copied");
      window.setTimeout(() => setCopyLabel("Copy"), 1500);
    } catch {
      setCopyLabel("Copy failed");
      window.setTimeout(() => setCopyLabel("Copy"), 1500);
    }
  }

  return (
    <article className="plan-section">
      <div className="plan-section-heading">
        <div>
          <h3>{section.title}</h3>
          {section.helper ? <p>{section.helper}</p> : null}
        </div>
        <button className="secondary-button" type="button" onClick={() => void handleCopy()}>
          {copyLabel}
        </button>
      </div>
      <pre className="command-snippet">
        <code>{section.content}</code>
      </pre>
    </article>
  );
}

async function loadAppWorkspace(
  token: string,
  setApps: (apps: DeployableApp[]) => void,
  setServers: (servers: Server[]) => void,
  setForm: (form: AppPayload) => void,
  setBootstrapForm: (form: BootstrapForm) => void,
  setError: (error: string | null) => void,
  setIsLoading: (isLoading: boolean) => void,
) {
  try {
    const [loadedApps, loadedServers] = await Promise.all([listApps(token), listServers(token)]);
    setApps(loadedApps);
    setServers(loadedServers);
    setForm({ ...emptyAppForm, server_id: loadedServers[0]?.id ?? "" });
    setBootstrapForm(createEmptyBootstrapForm("django", loadedServers[0]?.id ?? ""));
    setError(null);
  } catch (loadError) {
    setError(loadError instanceof Error ? loadError.message : "Could not load apps");
  } finally {
    setIsLoading(false);
  }
}

function appToForm(deployableApp: DeployableApp): AppPayload {
  return {
    name: deployableApp.name,
    server_id: deployableApp.server_id,
    repository_url: deployableApp.repository_url,
    branch: deployableApp.branch,
    app_path: deployableApp.app_path,
    service_name: deployableApp.service_name ?? "",
    deploy_command: deployableApp.deploy_command,
    restart_command: deployableApp.restart_command ?? "",
    healthcheck_url: deployableApp.healthcheck_url ?? "",
    port: deployableApp.port ?? null,
    cpu_limit: deployableApp.cpu_limit ?? "",
    memory_limit: deployableApp.memory_limit ?? "",
  };
}

function serviceStatusTone(status: string) {
  if (status === "active" || status === "restarted") return "success";
  if (status === "failed" || status === "restart failed" || status === "unknown") return "danger";
  if (status === "inactive") return "warning";
  return "neutral";
}

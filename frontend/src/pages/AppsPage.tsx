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
import { StatusBadge } from "../components/common";
import { useAuth } from "../hooks/useAuth";
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
};

export function AppsPage() {
  const { token } = useAuth();
  const [apps, setApps] = useState<DeployableApp[]>([]);
  const [servers, setServers] = useState<Server[]>([]);
  const [form, setForm] = useState<AppPayload>(emptyAppForm);
  const [error, setError] = useState<string | null>(null);
  const [isLoading, setIsLoading] = useState(true);
  const [isSubmitting, setIsSubmitting] = useState(false);

  useEffect(() => {
    if (!token) return;
    void loadAppWorkspace(token, setApps, setServers, setForm, setError, setIsLoading);
  }, [token]);

  const serverNames = useMemo(() => new Map(servers.map((server) => [server.id, server.name])), [servers]);

  async function handleSubmit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    if (!token) return;
    setError(null);
    setIsSubmitting(true);
    try {
      const created = await createApp(token, form);
      setApps((current) => [created, ...current]);
      setForm({ ...emptyAppForm, server_id: servers[0]?.id ?? "" });
    } catch (submitError) {
      setError(submitError instanceof Error ? submitError.message : "Could not create app");
    } finally {
      setIsSubmitting(false);
    }
  }

  async function handleDelete(appId: string) {
    if (!token) return;
    setError(null);
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
        {error ? <p className="form-error">{error}</p> : null}
        {isLoading ? <p className="muted">Loading apps...</p> : null}
        {!isLoading && apps.length === 0 ? (
          <div className="empty-panel">
            <h2>No apps yet</h2>
            <p>Register an application after adding at least one server.</p>
          </div>
        ) : null}
        <div className="resource-list">
          {apps.map((deployableApp) => (
            <article className="resource-row" key={deployableApp.id}>
              <div>
                <button className="link-button title-link" type="button" onClick={() => navigateTo(`/apps/${deployableApp.id}`)}>
                  {deployableApp.name}
                </button>
                <p>{serverNames.get(deployableApp.server_id) ?? "Unknown server"} · {deployableApp.branch} · {deployableApp.app_path}</p>
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
      </section>
      <aside className="form-panel" aria-labelledby="add-app-title">
        <h2 id="add-app-title">Add app</h2>
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
    try {
      const updated = await updateApp(token, deployableApp.id, form);
      setDeployableApp(updated);
      setForm(appToForm(updated));
      setNotice("App updated");
    } catch (submitError) {
      setError(submitError instanceof Error ? submitError.message : "Could not update app");
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

  const appNames = new Map([[deployableApp.id, deployableApp.name]]);

  return (
    <section className="detail-layout">
      <section className="detail-panel">
        <button className="link-button" type="button" onClick={() => navigateTo("/apps")}>
          Back to apps
        </button>
        <div className="detail-header">
          <div>
            <h2>{deployableApp.name}</h2>
            <p>{serverName} · {deployableApp.branch} · {deployableApp.app_path}</p>
          </div>
          <StatusBadge label={deployableApp.service_name ?? "no service"} />
        </div>
        <dl className="detail-list">
          <div><dt>Repository</dt><dd>{deployableApp.repository_url}</dd></div>
          <div><dt>Current commit</dt><dd>{deployableApp.current_commit ?? "Not deployed yet"}</dd></div>
          <div><dt>Last successful commit</dt><dd>{deployableApp.last_successful_commit ?? "Not deployed yet"}</dd></div>
          <div><dt>Healthcheck</dt><dd>{deployableApp.healthcheck_url ?? "Not configured"}</dd></div>
        </dl>
        {notice ? <p className="success-message">{notice}</p> : null}
        {error ? <p className="form-error">{error}</p> : null}
        <div className="detail-actions">
          <button className="primary-inline-button" disabled={isDeploying} type="button" onClick={() => void handleDeploy()}>
            {isDeploying ? "Starting deployment" : "Deploy"}
          </button>
        </div>
        <section className="nested-section" aria-labelledby="service-controls-title">
          <div className="section-heading">
            <div>
              <h2 id="service-controls-title">Service controls</h2>
              <p className="muted">Operations run against the configured remote server service.</p>
            </div>
            {serviceStatus ? <StatusBadge label={serviceStatus} tone={serviceStatusTone(serviceStatus)} /> : null}
          </div>
          <div className="detail-actions">
            <button className="secondary-button" disabled={isCheckingStatus} type="button" onClick={() => void handleCheckStatus()}>
              {isCheckingStatus ? "Checking" : "Check status"}
            </button>
            <button className="danger-button" disabled={isRestarting} type="button" onClick={() => void handleRestart()}>
              {isRestarting ? "Restarting" : "Restart service"}
            </button>
            <button className="secondary-button" disabled={isLoadingLogs} type="button" onClick={() => void handleLoadLogs()}>
              {isLoadingLogs ? "Loading logs" : "View recent logs"}
            </button>
          </div>
          {serviceLogs !== null ? (
            <pre className="service-log-viewer">
              <code>{serviceLogs || "No recent service logs returned."}</code>
            </pre>
          ) : null}
        </section>
        <section className="nested-section" aria-labelledby="app-deployments-title">
          <h2 id="app-deployments-title">Deployment history</h2>
          {deployments.length === 0 ? <p className="muted">No deployments for this app yet.</p> : null}
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
          isSubmitting={false}
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
      <label>Repository URL<input required value={form.repository_url} onChange={(event) => onChange({ ...form, repository_url: event.target.value })} /></label>
      <label>Branch<input required value={form.branch} onChange={(event) => onChange({ ...form, branch: event.target.value })} /></label>
      <label>
        Existing app path
        <input required value={form.app_path} onChange={(event) => onChange({ ...form, app_path: event.target.value })} />
        <span className="field-helper">Example: /opt/watchdog. Deploy commands run from this directory.</span>
      </label>
      <label>
        systemd service name
        <input value={form.service_name ?? ""} onChange={(event) => onChange({ ...form, service_name: event.target.value })} />
        <span className="field-helper">Optional, used for status, restart, and journal logs.</span>
      </label>
      <label>
        Healthcheck URL
        <input value={form.healthcheck_url ?? ""} onChange={(event) => onChange({ ...form, healthcheck_url: event.target.value })} />
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
        <textarea required rows={8} value={form.deploy_command} onChange={(event) => onChange({ ...form, deploy_command: event.target.value })} />
        <span className="field-helper">Example: git pull, install dependencies, run migrations, then restart the service.</span>
      </label>
      <label>Restart command<textarea rows={4} value={form.restart_command ?? ""} onChange={(event) => onChange({ ...form, restart_command: event.target.value })} /></label>
      <button className="primary-button" disabled={isSubmitting || servers.length === 0} type="submit">
        {isSubmitting ? "Saving" : submitLabel}
      </button>
    </form>
  );
}

async function loadAppWorkspace(
  token: string,
  setApps: (apps: DeployableApp[]) => void,
  setServers: (servers: Server[]) => void,
  setForm: (form: AppPayload) => void,
  setError: (error: string | null) => void,
  setIsLoading: (isLoading: boolean) => void,
) {
  try {
    const [loadedApps, loadedServers] = await Promise.all([listApps(token), listServers(token)]);
    setApps(loadedApps);
    setServers(loadedServers);
    setForm({ ...emptyAppForm, server_id: loadedServers[0]?.id ?? "" });
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
  };
}

function serviceStatusTone(status: string) {
  if (status === "active" || status === "restarted") return "success";
  if (status === "failed" || status === "restart failed" || status === "unknown") return "danger";
  if (status === "inactive") return "warning";
  return "neutral";
}

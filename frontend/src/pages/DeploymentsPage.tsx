import { useEffect, useMemo, useState } from "react";

import { cancelDeployment, getDeployment, listAppDeployments, triggerDeployment, triggerRollback } from "../api/deployments";
import { listApps } from "../api/apps";
import { CodeValue, EmptyState, formatDateTime, formatDuration, humanizeToken, shortSha, StatusBadge } from "../components/common";
import { useAuth } from "../hooks/useAuth";
import { useDeploymentStream } from "../hooks/useDeploymentStream";
import { navigateTo } from "../routes";
import { ACTIVE_DEPLOYMENT_STATUSES } from "../types/deployment";
import type { Deployment, DeploymentDetail, DeploymentLog, DeploymentStatus } from "../types/deployment";
import type { DeployableApp } from "../types/app";

export function DeploymentsPage() {
  const { token } = useAuth();
  const [apps, setApps] = useState<DeployableApp[]>([]);
  const [deployments, setDeployments] = useState<Deployment[]>([]);
  const [error, setError] = useState<string | null>(null);
  const [isLoading, setIsLoading] = useState(true);

  useEffect(() => {
    if (!token) return;
    setIsLoading(true);
    loadDeployments(token)
      .then(({ loadedApps, loadedDeployments }) => {
        setApps(loadedApps);
        setDeployments(loadedDeployments);
        setError(null);
      })
      .catch((loadError: unknown) => setError(loadError instanceof Error ? loadError.message : "Could not load deployments"))
      .finally(() => setIsLoading(false));
  }, [token]);

  const appNames = useMemo(() => new Map(apps.map((app) => [app.id, app.name])), [apps]);

  return (
    <section className="resource-main" aria-labelledby="deployments-title">
      <div className="section-heading">
        <div>
          <p className="eyebrow">Release history</p>
          <h2 id="deployments-title">Deployments</h2>
        </div>
      </div>
      {error ? <p className="form-error">{error}</p> : null}
      {isLoading ? <p className="muted">Loading deployments...</p> : null}
      {!isLoading && deployments.length === 0 ? (
        <EmptyState title="No deployments yet" body="Trigger your first deployment from an app page." />
      ) : null}
      <DeploymentTable deployments={deployments} appNames={appNames} />
    </section>
  );
}

export function DeploymentDetailPage({ deploymentId }: { deploymentId: string }) {
  const { token } = useAuth();
  const [deployment, setDeployment] = useState<DeploymentDetail | null>(null);
  const [appName, setAppName] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [notice, setNotice] = useState<string | null>(null);
  const [isLoading, setIsLoading] = useState(true);
  const [isRollingBack, setIsRollingBack] = useState(false);
  const [isRedeploying, setIsRedeploying] = useState(false);
  const [isCanceling, setIsCanceling] = useState(false);
  const [autoScroll, setAutoScroll] = useState(true);
  const isRunning = isDeploymentActive(deployment?.status);
  const stream = useDeploymentStream(token, deploymentId, Boolean(isRunning));
  const logs = stream.logs.length > 0 ? stream.logs : deployment?.logs ?? [];
  const displayStatus = stream.status ?? deployment?.status ?? null;

  useEffect(() => {
    if (!token) return;
    setIsLoading(true);
    Promise.all([getDeployment(token, deploymentId), listApps(token)])
      .then(([loadedDeployment, loadedApps]) => {
        setDeployment(loadedDeployment);
        setAppName(loadedApps.find((app) => app.id === loadedDeployment.app_id)?.name ?? null);
        setError(null);
      })
      .catch((loadError: unknown) => setError(loadError instanceof Error ? loadError.message : "Could not load deployment"))
      .finally(() => setIsLoading(false));
  }, [deploymentId, token]);

  useEffect(() => {
    if (!token || !stream.status) return;
    void getDeployment(token, deploymentId).then(setDeployment).catch(() => undefined);
  }, [deploymentId, stream.status, token]);

  useEffect(() => {
    if (!autoScroll) return;
    document.getElementById("deployment-log-end")?.scrollIntoView({ block: "nearest" });
  }, [autoScroll, logs.length]);

  async function handleRollback() {
    if (!token || !deployment) return;
    const confirmed = window.confirm(
      "Rollback checks out a previous Git commit and restarts the app. It does not rollback database migrations. Continue?",
    );
    if (!confirmed) return;
    setNotice(null);
    setError(null);
    setIsRollingBack(true);
    try {
      const rollbackDeployment = await triggerRollback(token, deployment.id);
      setNotice("Rollback started");
      navigateTo(`/deployments/${rollbackDeployment.id}`);
    } catch (rollbackError) {
      setError(rollbackError instanceof Error ? rollbackError.message : "Could not start rollback");
    } finally {
      setIsRollingBack(false);
    }
  }

  async function handleRedeploy() {
    if (!token || !deployment) return;
    setNotice(null);
    setError(null);
    setIsRedeploying(true);
    try {
      const nextDeployment = await triggerDeployment(token, deployment.app_id);
      setNotice("Deployment started");
      navigateTo(`/deployments/${nextDeployment.id}`);
    } catch (redeployError) {
      setError(redeployError instanceof Error ? redeployError.message : "Could not start deployment");
    } finally {
      setIsRedeploying(false);
    }
  }

  async function handleCancel() {
    if (!token || !deployment) return;
    const confirmed = window.confirm(
      "Cancel this deployment? The current command may still finish on the server, but its result will be discarded.",
    );
    if (!confirmed) return;
    setNotice(null);
    setError(null);
    setIsCanceling(true);
    try {
      const canceledDeployment = await cancelDeployment(token, deployment.id);
      // The cancel response carries no logs; keep the ones already loaded.
      setDeployment({ ...canceledDeployment, logs: deployment.logs });
      setNotice("Deployment canceled");
    } catch (cancelError) {
      setError(cancelError instanceof Error ? cancelError.message : "Could not cancel deployment");
    } finally {
      setIsCanceling(false);
    }
  }

  async function handleCopyLogs() {
    const text = logs.map((log) => `[${log.stream}] ${log.line}`).join("\n");
    await navigator.clipboard?.writeText(text);
    setNotice("Logs copied");
  }

  if (isLoading) {
    return <p className="muted">Loading deployment...</p>;
  }

  if (!deployment) {
    return <p className="form-error">{error ?? "Deployment not found"}</p>;
  }

  return (
    <section className="detail-layout wide-detail">
      <section className="detail-panel">
        <button className="link-button" type="button" onClick={() => navigateTo("/deployments")}>
          Back to deployments
        </button>
        <div className="detail-header">
          <div>
            <p className="eyebrow">Release</p>
            <h2>{appName ?? "Deployment"} {deployment.kind === "rollback" ? "rollback" : "deploy"}</h2>
            <p>{deployment.id}</p>
          </div>
          {displayStatus ? <StatusBadge label={displayStatus} tone={deploymentStatusTone(displayStatus)} /> : null}
        </div>
        {notice ? <p className="success-message">{notice}</p> : null}
        {error ? <p className="form-error">{error}</p> : null}
        {stream.error ? <p className="form-error">{stream.error}</p> : null}
        {isRunning ? (
          <div className="row-actions">
            <button className="danger-button" type="button" disabled={isCanceling} onClick={() => void handleCancel()}>
              {isCanceling ? "Canceling..." : "Cancel deployment"}
            </button>
          </div>
        ) : null}
        <dl className="detail-list">
          <div><dt>App</dt><dd>{appName ?? deployment.app_id}</dd></div>
          <div><dt>Kind</dt><dd>{humanizeToken(deployment.kind)}</dd></div>
          <div><dt>Started</dt><dd>{formatDateTime(deployment.started_at)}</dd></div>
          <div><dt>Finished</dt><dd>{formatDateTime(deployment.finished_at)}</dd></div>
          <div><dt>Duration</dt><dd>{formatDuration(deployment.duration_seconds)}</dd></div>
          <div><dt>Commit</dt><dd><CodeValue value={deployment.commit_sha} /></dd></div>
          <div><dt>Previous commit</dt><dd><CodeValue value={deployment.previous_commit_sha} /></dd></div>
          <div><dt>Exit code</dt><dd>{deployment.exit_code ?? "Not finished"}</dd></div>
          <div><dt>Error</dt><dd>{deploymentErrorSummary(deployment)}</dd></div>
        </dl>
        {deployment.error_message ? <p className="metadata-note">Full error output remains in the logs panel.</p> : null}
        <section className="deploy-action-panel" aria-labelledby="redeploy-title">
          <h2 id="redeploy-title">Deploy again</h2>
          <p>{redeployHelperText(deployment.status)}</p>
          <button
            className="primary-inline-button"
            disabled={isRedeploying || deployment.status === "pending" || deployment.status === "running"}
            type="button"
            onClick={() => void handleRedeploy()}
          >
            {isRedeploying ? "Starting deployment" : "Run deploy again"}
          </button>
        </section>
        <section className="rollback-panel" aria-labelledby="rollback-title">
          <h2 id="rollback-title">Rollback</h2>
          <p>
            Rollback reverts code to a previous Git commit and restarts the app. It does not rollback database migrations.
          </p>
          <button
            className="danger-button"
            disabled={isRollingBack || deployment.status === "pending" || deployment.status === "running"}
            type="button"
            onClick={() => void handleRollback()}
          >
            {isRollingBack ? "Starting rollback" : "Start rollback"}
          </button>
        </section>
      </section>
      <section className="log-panel" aria-labelledby="deployment-logs-title">
        <div className="section-heading">
          <h2 id="deployment-logs-title">Logs</h2>
          <div className="row-actions">
            <button className="secondary-button" type="button" onClick={() => void handleCopyLogs()} disabled={logs.length === 0}>
              Copy logs
            </button>
            <button className="secondary-button" type="button" onClick={() => setAutoScroll((current) => !current)}>
              {autoScroll ? "Pause scroll" : "Resume scroll"}
            </button>
          </div>
        </div>
        <DeploymentLogViewer logs={logs} />
      </section>
    </section>
  );
}

export function DeploymentTable({
  deployments,
  appNames,
}: {
  deployments: Deployment[];
  appNames: Map<string, string>;
}) {
  if (deployments.length === 0) return null;

  return (
    <div className="deployment-table" role="table">
      <div className="deployment-table-row heading" role="row">
        <span>App</span>
        <span>Status</span>
        <span>Kind</span>
        <span>Commit</span>
        <span>Started</span>
        <span>Duration</span>
        <span>Action</span>
      </div>
      {deployments.map((deployment) => (
        <button
          className="deployment-table-row"
          key={deployment.id}
          role="row"
          type="button"
          onClick={() => navigateTo(`/deployments/${deployment.id}`)}
        >
          <span>{appNames.get(deployment.app_id) ?? deployment.app_id}</span>
          <StatusBadge label={deployment.status} tone={deploymentStatusTone(deployment.status)} />
          <span>{humanizeToken(deployment.kind)}</span>
          <span title={deployment.commit_sha ?? undefined}>{shortSha(deployment.commit_sha)}</span>
          <span>{formatDateTime(deployment.started_at)}</span>
          <span>{formatDuration(deployment.duration_seconds)}</span>
          <span className="row-link">View details</span>
        </button>
      ))}
    </div>
  );
}

export function DeploymentLogViewer({ logs }: { logs: DeploymentLog[] }) {
  return (
    <pre className="log-viewer">
      {logs.length === 0 ? <code className="log-line system">Waiting for deployment logs...</code> : null}
      {logs.map((log) => {
        const key = log.id ?? `${log.sequence}-${log.stream}-${log.line}`;
        return (
          <code className={`log-line ${log.stream}`} key={key}>
            <span>{log.stream}</span>
            {log.line}
          </code>
        );
      })}
      <span id="deployment-log-end" />
    </pre>
  );
}

export function deploymentStatusTone(status: DeploymentStatus) {
  if (status === "success") return "success";
  if (status === "failed" || status === "canceled") return "danger";
  if (ACTIVE_DEPLOYMENT_STATUSES.includes(status)) return "warning";
  return "neutral";
}

export function isDeploymentActive(status: DeploymentStatus | null | undefined) {
  return status !== null && status !== undefined && ACTIVE_DEPLOYMENT_STATUSES.includes(status);
}

async function loadDeployments(token: string) {
  const loadedApps = await listApps(token);
  const deploymentGroups = await Promise.all(loadedApps.map((app) => listAppDeployments(token, app.id)));
  const loadedDeployments = deploymentGroups.flat().sort((left, right) => {
    return new Date(right.created_at).getTime() - new Date(left.created_at).getTime();
  });
  return { loadedApps, loadedDeployments };
}

function deploymentErrorSummary(deployment: DeploymentDetail) {
  if (!deployment.error_message) return "None";
  if (deployment.status === "failed") return "Deployment failed. See full logs for details.";
  if (deployment.error_message.length <= 96) return deployment.error_message;
  return `${deployment.error_message.slice(0, 96)}...`;
}

function redeployHelperText(status: DeploymentStatus) {
  if (status === "failed") return "Fix the issue, then run deploy again.";
  if (status === "success") return "Run another deployment for this app.";
  if (status === "canceled") return "Run a fresh deployment for this app.";
  return "A deployment is already in progress.";
}

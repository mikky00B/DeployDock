import { useEffect, useState, type ReactNode } from "react";

import { getDashboard } from "../api/dashboard";
import { StatusBadge } from "../components/common";
import { useAuth } from "../hooks/useAuth";
import { navigateTo } from "../routes";
import type { Dashboard } from "../types/dashboard";
import { deploymentStatusTone } from "./DeploymentsPage";

export function DashboardPage() {
  const { token, user } = useAuth();
  const [dashboard, setDashboard] = useState<Dashboard | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [isLoading, setIsLoading] = useState(true);

  useEffect(() => {
    if (!token) return;
    setIsLoading(true);
    getDashboard(token)
      .then((loadedDashboard) => {
        setDashboard(loadedDashboard);
        setError(null);
      })
      .catch((loadError: unknown) => setError(loadError instanceof Error ? loadError.message : "Could not load dashboard"))
      .finally(() => setIsLoading(false));
  }, [token]);

  if (isLoading) {
    return <DashboardSkeleton userLabel={user?.full_name || user?.email || "Account"} />;
  }

  if (!dashboard) {
    return <p className="form-error">{error ?? "Dashboard unavailable"}</p>;
  }

  return (
    <section className="dashboard-layout">
      <section className="workspace-grid">
        <SummaryCard
          label="Latest deployment"
          value={dashboard.summary.latest_deployment_status ?? "None"}
          helper={dashboard.summary.latest_deployment_status ? "Most recent result" : "No deployments yet"}
          tone={dashboard.summary.latest_deployment_status ? deploymentStatusTone(dashboard.summary.latest_deployment_status) : "neutral"}
        />
        <SummaryCard label="Servers" value={String(dashboard.summary.total_servers)} helper={`${dashboard.summary.connected_servers} connected`} />
        <SummaryCard label="Apps" value={String(dashboard.summary.total_apps)} helper={`${dashboard.summary.deployed_apps} deployed`} />
        <SummaryCard label="Recent failures" value={String(dashboard.summary.recent_failures)} helper="in last 7 days" tone={dashboard.summary.recent_failures > 0 ? "danger" : "success"} />
      </section>

      <section className="dashboard-panels">
        <DashboardPanel title="Recent deployments" emptyText="Deploy from an app detail page to populate release history.">
          {dashboard.recent_deployments.map((deployment) => (
            <button className="activity-row" key={deployment.id} type="button" onClick={() => navigateTo(`/deployments/${deployment.id}`)}>
              <div>
                <strong>{deployment.kind}</strong>
                <span>{deployment.commit_sha ?? "Unknown commit"} · {formatDate(deployment.created_at)}</span>
              </div>
              <StatusBadge label={deployment.status} tone={deploymentStatusTone(deployment.status)} />
              <span className="row-link">View details</span>
            </button>
          ))}
        </DashboardPanel>

        <DashboardPanel title="Recent audit events" emptyText="Important actions such as service restarts and rollbacks will appear here.">
          {dashboard.recent_audit_logs.map((event) => (
            <article className="activity-row static" key={event.id}>
              <div>
                <strong>{event.action}</strong>
                <span>{event.entity_type} · {formatDate(event.created_at)}</span>
              </div>
            </article>
          ))}
        </DashboardPanel>

        <DashboardPanel title="Servers" emptyText="Add a server to begin connecting DeployDock to your infrastructure.">
          {dashboard.recent_servers.map((server) => (
            <button className="activity-row" key={server.id} type="button" onClick={() => navigateTo("/servers")}>
              <div>
                <strong>{server.name}</strong>
                <span>{server.host}</span>
              </div>
              <StatusBadge label={server.status} tone={server.status === "connected" ? "success" : server.status === "unreachable" ? "danger" : "neutral"} />
            </button>
          ))}
        </DashboardPanel>

        <DashboardPanel title="Apps" emptyText="Register an app after adding a server.">
          {dashboard.recent_apps.map((app) => (
            <button className="activity-row" key={app.id} type="button" onClick={() => navigateTo(`/apps/${app.id}`)}>
              <div>
                <strong>{app.name}</strong>
                <span>{app.service_name ?? "No service"} · {app.last_successful_commit ?? "Not deployed"}</span>
              </div>
            </button>
          ))}
        </DashboardPanel>
      </section>
    </section>
  );
}

function SummaryCard({
  label,
  value,
  helper,
  tone = "neutral",
}: {
  label: string;
  value: string;
  helper?: string;
  tone?: "neutral" | "success" | "danger" | "warning";
}) {
  return (
    <article className={`summary-panel ${tone}`}>
      <span className="summary-label">{label}</span>
      <strong>{value}</strong>
      {helper ? <p>{helper}</p> : null}
    </article>
  );
}

function DashboardPanel({ title, emptyText, children }: { title: string; emptyText: string; children: ReactNode }) {
  const hasChildren = Array.isArray(children) ? children.length > 0 : Boolean(children);

  return (
    <section className="dashboard-panel">
      <h2>{title}</h2>
      {hasChildren ? <div className="activity-list">{children}</div> : <p className="muted">{emptyText}</p>}
    </section>
  );
}

function DashboardSkeleton({ userLabel }: { userLabel: string }) {
  return (
    <section className="dashboard-layout">
      <section className="workspace-grid">
        <SummaryCard label="Signed in as" value={userLabel} />
        <SummaryCard label="Latest deployment" value="..." helper="Loading" />
        <SummaryCard label="Apps" value="..." helper="Loading" />
        <SummaryCard label="Recent failures" value="..." helper="Loading" />
      </section>
      <section className="dashboard-panels">
        <section className="dashboard-panel"><h2>Recent deployments</h2><p className="muted">Loading deployments...</p></section>
        <section className="dashboard-panel"><h2>Recent audit events</h2><p className="muted">Loading audit events...</p></section>
      </section>
    </section>
  );
}

function formatDate(value: string) {
  return new Date(value).toLocaleString();
}

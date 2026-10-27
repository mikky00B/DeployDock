import { Fragment, useEffect, useState, type FormEvent } from "react";

import { createAgentRegistrationToken } from "../api/agents";
import { apiClient } from "../api/client";

import {
  createServer,
  deleteServer,
  getServer,
  listServers,
  repinServerHostKey,
  testServerConnection,
  updateServer,
} from "../api/servers";
import { EmptyState, copyToClipboard, formatDateTime, StatusBadge } from "../components/common";
import { useAuth } from "../hooks/useAuth";
import { navigateTo } from "../routes";
import type { Server, ServerStatus } from "../types/server";

const emptyServerForm = {
  name: "",
  host: "",
  port: "22",
  username: "",
  private_key: "",
};

export function ServersPage() {
  const { token } = useAuth();
  const [servers, setServers] = useState<Server[]>([]);
  const [form, setForm] = useState(emptyServerForm);
  const [createdPublicKey, setCreatedPublicKey] = useState<string | null>(null);
  const [createdUsername, setCreatedUsername] = useState<string | null>(null);
  const [notice, setNotice] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [isLoading, setIsLoading] = useState(true);
  const [isSubmitting, setIsSubmitting] = useState(false);
  const [testingServerId, setTestingServerId] = useState<string | null>(null);
  const [mintingServerId, setMintingServerId] = useState<string | null>(null);
  const [deletingId, setDeletingId] = useState<string | null>(null);
  const [reloadKey, setReloadKey] = useState(0);
  const [agentToken, setAgentToken] = useState<{ serverId: string; token: string } | null>(null);

  async function handleMintAgentToken(serverId: string) {
    if (!token) return;
    setError(null);
    setNotice(null);
    setMintingServerId(serverId);
    try {
      const minted = await createAgentRegistrationToken(token, serverId);
      setAgentToken({ serverId, token: minted.token });
    } catch (tokenError) {
      setError(tokenError instanceof Error ? tokenError.message : "Could not mint an agent registration token");
    } finally {
      setMintingServerId(null);
    }
  }

  useEffect(() => {
    if (!token) return;
    let cancelled = false;
    setIsLoading(true);
    void loadServers(token, setServers, setError, setIsLoading, () => cancelled);
    return () => {
      cancelled = true;
    };
  }, [token, reloadKey]);

  async function handleSubmit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    if (!token) return;
    setIsSubmitting(true);
    setError(null);
    setNotice(null);
    setCreatedPublicKey(null);
    setCreatedUsername(null);
    try {
      const created = await createServer(token, {
        ...form,
        port: Number(form.port),
        private_key: form.private_key || undefined,
      });
      setServers((current) => [created, ...current]);
      setCreatedPublicKey(created.public_ssh_key);
      setCreatedUsername(created.username);
      setNotice("Server added. Copy the generated public key to the target server, then test the connection.");
      setForm(emptyServerForm);
    } catch (submitError) {
      setError(submitError instanceof Error ? submitError.message : "Could not create server");
    } finally {
      setIsSubmitting(false);
    }
  }

  async function handleDelete(server: Server) {
    if (!token) return;
    const confirmed = window.confirm(
      `Delete server "${server.name}"? Apps registered on it stop being deployable; the server itself is never modified.`,
    );
    if (!confirmed) return;
    setError(null);
    setNotice(null);
    setDeletingId(server.id);
    try {
      await deleteServer(token, server.id);
      setServers((current) => current.filter((s) => s.id !== server.id));
    } catch (deleteError) {
      setError(deleteError instanceof Error ? deleteError.message : "Could not delete server");
    } finally {
      setDeletingId(null);
    }
  }

  async function handleTest(serverId: string) {
    if (!token) return;
    setError(null);
    setNotice(null);
    setTestingServerId(serverId);
    try {
      const result = await testServerConnection(token, serverId);
      const refreshed = await listServers(token);
      setServers(refreshed);
      if (result.success) {
        setNotice(result.message);
      } else {
        setError(result.message);
      }
    } catch (testError) {
      setError(testError instanceof Error ? testError.message : "Could not test connection");
    } finally {
      setTestingServerId(null);
    }
  }

  return (
    <section className="resource-layout">
      <section className="resource-main" aria-labelledby="servers-title">
        <div className="section-heading">
          <div>
            <p className="eyebrow">Infrastructure</p>
            <h2 id="servers-title">Servers</h2>
          </div>
        </div>
        {notice ? <p className="success-message" role="status">{notice}</p> : null}
        {error ? <p className="form-error" role="alert">{error}</p> : null}
        {isLoading ? <p className="muted">Loading servers...</p> : null}
        {error && !isLoading && servers.length === 0 ? (
          <button
            className="secondary-button"
            type="button"
            onClick={() => {
              setError(null);
              setReloadKey((key) => key + 1);
            }}
          >
            Retry
          </button>
        ) : null}
        {!isLoading && servers.length === 0 && !error ? (
          <EmptyState title="No servers yet" body="Connect your first VPS to start deploying existing server apps." />
        ) : null}
        <div className="resource-list">
          {servers.map((server) => (
            <Fragment key={server.id}>
              <article className="resource-row">
                <div>
                  <a
                    className="link-button title-link"
                    href={`/servers/${server.id}`}
                    onClick={(event) => {
                      event.preventDefault();
                      navigateTo(`/servers/${server.id}`);
                    }}
                  >
                    {server.name}
                  </a>
                  <p>{server.username}@{server.host}:{server.port}</p>
                  {server.known_host_key_fingerprint ? null : (
                    <p className="field-helper">Host key not pinned — test the connection to pin it.</p>
                  )}
                </div>
                <StatusBadge label={server.status} tone={serverStatusTone(server.status)} />
                <div className="row-actions">
                  <button
                    className="secondary-button"
                    disabled={mintingServerId === server.id}
                    type="button"
                    onClick={() => void handleMintAgentToken(server.id)}
                  >
                    {mintingServerId === server.id ? "Minting" : "Agent"}
                  </button>
                  <button
                    className="secondary-button"
                    disabled={testingServerId === server.id}
                    type="button"
                    onClick={() => void handleTest(server.id)}
                  >
                    {testingServerId === server.id ? "Testing" : "Test"}
                  </button>
                  <button
                    className="danger-button"
                    disabled={deletingId === server.id}
                    type="button"
                    onClick={() => void handleDelete(server)}
                  >
                    {deletingId === server.id ? "Deleting" : "Delete"}
                  </button>
                </div>
              </article>
              {agentToken?.serverId === server.id ? (
                <AgentTokenPanel token={agentToken.token} serverName={server.name} />
              ) : null}
            </Fragment>
          ))}
        </div>
      </section>

      <aside className="form-panel" aria-labelledby="add-server-title">
        <h2 id="add-server-title">Add server</h2>
        <p className="form-helper">
          Add an existing VPS or cloud server. Use a dedicated non-root deploy user. DeployDock generates a unique
          ed25519 keypair for this server unless you choose advanced manual key upload.
        </p>
        {createdPublicKey ? (
          <PublicKeyPanel publicKey={createdPublicKey} username={createdUsername ?? "deploy"} />
        ) : null}
        <ServerForm
          form={form}
          isSubmitting={isSubmitting}
          privateKeyRequired={false}
          submitLabel="Add server"
          onChange={setForm}
          onSubmit={handleSubmit}
        />
      </aside>
    </section>
  );
}

export function ServerDetailPage({ serverId }: { serverId: string }) {
  const { token } = useAuth();
  const [server, setServer] = useState<Server | null>(null);
  const [form, setForm] = useState(emptyServerForm);
  const [notice, setNotice] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [isLoading, setIsLoading] = useState(true);
  const [isTesting, setIsTesting] = useState(false);
  const [isRepinning, setIsRepinning] = useState(false);
  const [isSaving, setIsSaving] = useState(false);
  const [reloadKey, setReloadKey] = useState(0);

  useEffect(() => {
    if (!token) return;
    let cancelled = false;
    setIsLoading(true);
    getServer(token, serverId)
      .then((loadedServer) => {
        if (cancelled) return;
        setServer(loadedServer);
        setForm({
          name: loadedServer.name,
          host: loadedServer.host,
          port: String(loadedServer.port),
          username: loadedServer.username,
          private_key: "",
        });
        setError(null);
      })
      .catch((loadError: unknown) => {
        if (!cancelled) setError(loadError instanceof Error ? loadError.message : "Could not load server");
      })
      .finally(() => {
        if (!cancelled) setIsLoading(false);
      });
    return () => {
      cancelled = true;
    };
  }, [serverId, token, reloadKey]);

  async function handleSubmit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    if (!token || !server) return;
    setNotice(null);
    setError(null);
    setIsSaving(true);
    try {
      const updated = await updateServer(token, server.id, { ...form, port: Number(form.port) });
      setServer(updated);
      setForm((current) => ({ ...current, private_key: "" }));
      setNotice("Server updated");
    } catch (submitError) {
      setError(submitError instanceof Error ? submitError.message : "Could not update server");
    } finally {
      setIsSaving(false);
    }
  }

  async function handleTest() {
    if (!token || !server) return;
    setNotice(null);
    setError(null);
    setIsTesting(true);
    try {
      const wasUnpinned = server.known_host_key_fingerprint === null;
      const result = await testServerConnection(token, server.id);
      const refreshed = await getServer(token, server.id);
      setServer(refreshed);
      if (result.success && wasUnpinned && result.host_key_fingerprint) {
        setNotice(
          `${result.message}. Host key pinned: ${result.host_key_fingerprint} — verify this against the server itself.`,
        );
      } else if (result.success) {
        setNotice(result.message);
      } else {
        setError(result.message);
      }
    } catch (testError) {
      setError(testError instanceof Error ? testError.message : "Could not test connection");
    } finally {
      setIsTesting(false);
    }
  }

  async function handleRepin() {
    if (!token || !server) return;
    setNotice(null);
    setError(null);
    setIsRepinning(true);
    try {
      const result = await repinServerHostKey(token, server.id);
      const refreshed = await getServer(token, server.id);
      setServer(refreshed);
      setNotice(
        result.previous_fingerprint && result.previous_fingerprint !== result.fingerprint
          ? `Host key replaced. Was ${result.previous_fingerprint}, now ${result.fingerprint}. Verify it against the server itself.`
          : `Host key pinned: ${result.fingerprint}. Verify it against the server itself.`,
      );
    } catch (repinError) {
      setError(repinError instanceof Error ? repinError.message : "Could not re-pin host key");
    } finally {
      setIsRepinning(false);
    }
  }

  if (isLoading) {
    return <p className="muted">Loading server...</p>;
  }

  if (!server) {
    return (
      <section className="detail-layout">
        <section className="detail-panel">
          <a className="link-button" href="/servers" onClick={(event) => { event.preventDefault(); navigateTo("/servers"); }}>
            Back to servers
          </a>
          <p className="form-error" role="alert">{error ?? "Server not found"}</p>
          {error ? (
            <button
              className="secondary-button"
              type="button"
              onClick={() => {
                setError(null);
                setIsLoading(true);
                setReloadKey((key) => key + 1);
              }}
            >
              Retry
            </button>
          ) : null}
        </section>
      </section>
    );
  }

  return (
    <section className="detail-layout">
      <section className="detail-panel">
        <a className="link-button" href="/servers" onClick={(event) => { event.preventDefault(); navigateTo("/servers"); }}>
          Back to servers
        </a>
        <div className="detail-header">
          <div>
            <p className="eyebrow">Server</p>
            <h2>{server.name}</h2>
            <p>{server.username}@{server.host}:{server.port}</p>
          </div>
          <StatusBadge label={server.status} tone={serverStatusTone(server.status)} />
        </div>
        <dl className="detail-list">
          <div><dt>Public key</dt><dd>{server.public_ssh_key ? <PublicKeyBlock publicKey={server.public_ssh_key} /> : "Manual key uploaded"}</dd></div>
          <div><dt>Key fingerprint</dt><dd>{server.private_key_fingerprint ?? "Not available"}</dd></div>
          <div>
            <dt>Host key</dt>
            <dd>
              {server.known_host_key_fingerprint ? (
                <>
                  <code className="inline-code">{server.known_host_key_fingerprint}</code>
                  <span className="field-helper">
                    Pinned {formatDateTime(server.known_host_key_pinned_at)}. Compare it against
                    <code className="inline-code">ssh-keyscan {server.host}</code> run on a machine you trust.
                  </span>
                </>
              ) : (
                <span className="field-helper">
                  Not pinned yet. Test the connection to pin the host key this server presents.
                </span>
              )}
            </dd>
          </div>
          <div><dt>Last checked</dt><dd>{server.last_connection_check_at ? formatDateTime(server.last_connection_check_at) : "Never"}</dd></div>
          <div><dt>Last error</dt><dd>{server.last_connection_error ?? "None"}</dd></div>
        </dl>
        {notice ? <p className="success-message" role="status">{notice}</p> : null}
        {error ? <p className="form-error" role="alert">{error}</p> : null}
        <div className="row-actions">
          <button className="secondary-button" disabled={isTesting} type="button" onClick={() => void handleTest()}>
            {isTesting ? "Testing connection" : "Test connection"}
          </button>
          {server.known_host_key_fingerprint ? (
            <button className="danger-button" disabled={isRepinning} type="button" onClick={() => void handleRepin()}>
              {isRepinning ? "Re-pinning host key" : "Re-pin host key"}
            </button>
          ) : null}
        </div>
        {server.known_host_key_fingerprint ? (
          <p className="field-helper">
            Only re-pin after you rebuilt this server or rotated its host key on purpose. If the host key changed
            unexpectedly, treat it as an interception attempt and investigate before re-pinning.
          </p>
        ) : null}
      </section>
      <aside className="form-panel">
        <h2>Edit server</h2>
        <p className="form-helper">
          Leave private key blank to keep the current encrypted key. Pasting a key here is the advanced manual option.
        </p>
        <ServerForm
          form={form}
          isSubmitting={isSaving}
          privateKeyRequired={false}
          submitLabel="Save server"
          onChange={setForm}
          onSubmit={handleSubmit}
        />
      </aside>
    </section>
  );
}

function ServerForm({
  form,
  isSubmitting,
  privateKeyRequired,
  submitLabel,
  onChange,
  onSubmit,
}: {
  form: typeof emptyServerForm;
  isSubmitting: boolean;
  privateKeyRequired: boolean;
  submitLabel: string;
  onChange: (form: typeof emptyServerForm) => void;
  onSubmit: (event: FormEvent<HTMLFormElement>) => void;
}) {
  return (
    <form className="resource-form" onSubmit={onSubmit}>
      <label>Name<input required placeholder="Production VPS" value={form.name} onChange={(event) => onChange({ ...form, name: event.target.value })} /></label>
      <label>Host<input required placeholder="203.0.113.10 or deploy.example.com" value={form.host} onChange={(event) => onChange({ ...form, host: event.target.value })} /></label>
      <label>Port<input min={1} max={65535} required type="number" value={form.port} onChange={(event) => onChange({ ...form, port: event.target.value })} /></label>
      <label>
        Deploy username
        <input required value={form.username} onChange={(event) => onChange({ ...form, username: event.target.value })} />
        <span className="field-helper">Use a dedicated non-root user such as deploy, not root.</span>
      </label>
      <label>
        Advanced: paste an existing private key
        <textarea
          required={privateKeyRequired}
          value={form.private_key}
          onChange={(event) => onChange({ ...form, private_key: event.target.value })}
          rows={7}
        />
        <span className="field-helper">Advanced/manual mode. Recommended: leave blank so DeployDock generates a unique keypair for this server.</span>
      </label>
      <button className="primary-button" disabled={isSubmitting} type="submit">
        {isSubmitting ? "Saving" : submitLabel}
      </button>
    </form>
  );
}

function PublicKeyPanel({ publicKey, username }: { publicKey: string; username: string }) {
  const sshDirectory = `/home/${username}/.ssh`;
  const authorizedKeysPath = `${sshDirectory}/authorized_keys`;

  return (
    <section className="key-panel" aria-label="Generated public key">
      <h3>Generated public key</h3>
      <p>
        Use a dedicated non-root deploy user. Add this public key to {authorizedKeysPath} on the target server before
        testing the connection.
      </p>
      <PublicKeyBlock publicKey={publicKey} />
      <pre className="command-snippet">
        <code>{`mkdir -p ${sshDirectory}
echo '${publicKey}' >> ${authorizedKeysPath}
chmod 700 ${sshDirectory}
chmod 600 ${authorizedKeysPath}`}</code>
      </pre>
    </section>
  );
}

function PublicKeyBlock({ publicKey }: { publicKey: string }) {
  const [copyState, setCopyState] = useState<"copied" | "failed" | null>(null);

  async function handleCopy() {
    const copied = await copyToClipboard(publicKey);
    setCopyState(copied ? "copied" : "failed");
    window.setTimeout(() => setCopyState(null), 1500);
  }

  return (
    <div className="public-key-block">
      <code>{publicKey}</code>
      <button className="secondary-button" type="button" onClick={() => void handleCopy()}>
        {copyState === "copied" ? "Copied" : copyState === "failed" ? "Copy failed" : "Copy"}
      </button>
    </div>
  );
}

function AgentTokenPanel({ token, serverName }: { token: string; serverName: string }) {
  const command = `sudo ./deploydock-agent register --server ${apiClient.baseUrl || window.location.origin} --token ${token}`;
  const [copied, setCopied] = useState<string | null>(null);

  async function copy(value: string, label: string) {
    const succeeded = await copyToClipboard(value);
    setCopied(succeeded ? label : `${label}-failed`);
    window.setTimeout(() => setCopied(null), 1500);
  }

  return (
    <section className="key-panel" aria-label="Agent registration token">
      <h3>Register an agent on this server</h3>
      <p>
        One-time token, expires in 15 minutes. Build <code className="inline-code">deploydock-agent</code> from the
        repository (<code className="inline-code">go build -o deploydock-agent ./go/cmd/deploydock-agent</code>), copy
        it to the server, then run:
      </p>
      <div className="public-key-block">
        <code>{token}</code>
        <button className="secondary-button" type="button" onClick={() => void copy(token, "token")}>
          {copied === "token" ? "Copied" : copied === "token-failed" ? "Copy failed" : "Copy token"}
        </button>
      </div>
      <pre className="command-snippet">
        <code>{command}</code>
      </pre>
      <button className="secondary-button" type="button" onClick={() => void copy(command, "command")}>
        {copied === "command" ? "Copied" : copied === "command-failed" ? "Copy failed" : "Copy command"}
      </button>
      <p className="field-helper">
        Adjust --server if this DeployDock URL is not reachable from the server. After registering,{" "}
        <code className="inline-code">sudo ./deploydock-agent run</code> starts heartbeats and agent-driven deploys.
      </p>
      <p className="field-helper">
        Prefer your AI agent? Run <code className="inline-code">deploydock mcp setup</code> on your machine, then say{" "}
        <i>"deploy to {serverName}"</i> — the agent handles the rest.
      </p>
    </section>
  );
}

async function loadServers(
  token: string,
  setServers: (servers: Server[]) => void,
  setError: (error: string | null) => void,
  setIsLoading: (isLoading: boolean) => void,
  isCancelled: () => boolean = () => false,
) {
  try {
    const loaded = await listServers(token);
    if (isCancelled()) return;
    setServers(loaded);
    setError(null);
  } catch (loadError) {
    if (isCancelled()) return;
    setError(loadError instanceof Error ? loadError.message : "Could not load servers");
  } finally {
    if (!isCancelled()) setIsLoading(false);
  }
}

function serverStatusTone(status: ServerStatus) {
  if (status === "connected") return "success";
  if (status === "unreachable") return "danger";
  return "neutral";
}

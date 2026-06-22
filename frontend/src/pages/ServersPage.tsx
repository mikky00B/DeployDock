import { useEffect, useState, type FormEvent } from "react";

import { createServer, deleteServer, getServer, listServers, testServerConnection, updateServer } from "../api/servers";
import { StatusBadge } from "../components/common";
import { useAuth } from "../hooks/useAuth";
import { navigateTo } from "../routes";
import type { Server, ServerStatus } from "../types/server";

const emptyServerForm = {
  name: "",
  host: "",
  port: 22,
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

  useEffect(() => {
    if (!token) return;
    void loadServers(token, setServers, setError, setIsLoading);
  }, [token]);

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

  async function handleDelete(serverId: string) {
    if (!token) return;
    setError(null);
    setNotice(null);
    try {
      await deleteServer(token, serverId);
      setServers((current) => current.filter((server) => server.id !== serverId));
    } catch (deleteError) {
      setError(deleteError instanceof Error ? deleteError.message : "Could not delete server");
    }
  }

  async function handleTest(serverId: string) {
    if (!token) return;
    setError(null);
    setNotice(null);
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
        {notice ? <p className="success-message">{notice}</p> : null}
        {error ? <p className="form-error">{error}</p> : null}
        {isLoading ? <p className="muted">Loading servers...</p> : null}
        {!isLoading && servers.length === 0 ? (
          <div className="empty-panel">
            <h2>No servers yet</h2>
            <p>Add the VPS or cloud server that already runs your applications.</p>
          </div>
        ) : null}
        <div className="resource-list">
          {servers.map((server) => (
            <article className="resource-row" key={server.id}>
              <div>
                <button className="link-button title-link" type="button" onClick={() => navigateTo(`/servers/${server.id}`)}>
                  {server.name}
                </button>
                <p>{server.username}@{server.host}:{server.port}</p>
              </div>
              <StatusBadge label={server.status} tone={serverStatusTone(server.status)} />
              <div className="row-actions">
                <button className="secondary-button" type="button" onClick={() => void handleTest(server.id)}>
                  Test
                </button>
                <button className="danger-button" type="button" onClick={() => void handleDelete(server.id)}>
                  Delete
                </button>
              </div>
            </article>
          ))}
        </div>
      </section>

      <aside className="form-panel" aria-labelledby="add-server-title">
        <h2 id="add-server-title">Add server</h2>
        <p className="form-helper">
          Add an existing VPS or cloud server. Use a dedicated non-root deploy user; DeployDock will generate a unique
          ed25519 keypair for this server unless you choose the manual private-key option.
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

  useEffect(() => {
    if (!token) return;
    setIsLoading(true);
    getServer(token, serverId)
      .then((loadedServer) => {
        setServer(loadedServer);
        setForm({
          name: loadedServer.name,
          host: loadedServer.host,
          port: loadedServer.port,
          username: loadedServer.username,
          private_key: "",
        });
        setError(null);
      })
      .catch((loadError: unknown) => setError(loadError instanceof Error ? loadError.message : "Could not load server"))
      .finally(() => setIsLoading(false));
  }, [serverId, token]);

  async function handleSubmit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    if (!token || !server) return;
    setNotice(null);
    setError(null);
    try {
      const updated = await updateServer(token, server.id, { ...form, port: Number(form.port) });
      setServer(updated);
      setForm((current) => ({ ...current, private_key: "" }));
      setNotice("Server updated");
    } catch (submitError) {
      setError(submitError instanceof Error ? submitError.message : "Could not update server");
    }
  }

  async function handleTest() {
    if (!token || !server) return;
    setNotice(null);
    setError(null);
    try {
      const result = await testServerConnection(token, server.id);
      const refreshed = await getServer(token, server.id);
      setServer(refreshed);
      setNotice(result.message);
    } catch (testError) {
      setError(testError instanceof Error ? testError.message : "Could not test connection");
    }
  }

  if (isLoading) {
    return <p className="muted">Loading server...</p>;
  }

  if (!server) {
    return <p className="form-error">{error ?? "Server not found"}</p>;
  }

  return (
    <section className="detail-layout">
      <section className="detail-panel">
        <button className="link-button" type="button" onClick={() => navigateTo("/servers")}>
          Back to servers
        </button>
        <div className="detail-header">
          <div>
            <h2>{server.name}</h2>
            <p>{server.username}@{server.host}:{server.port}</p>
          </div>
          <StatusBadge label={server.status} tone={serverStatusTone(server.status)} />
        </div>
        <dl className="detail-list">
          <div><dt>Public key</dt><dd>{server.public_ssh_key ? <PublicKeyBlock publicKey={server.public_ssh_key} /> : "Manual key uploaded"}</dd></div>
          <div><dt>Fingerprint</dt><dd>{server.private_key_fingerprint ?? "Not available"}</dd></div>
          <div><dt>Last checked</dt><dd>{formatDate(server.last_connection_check_at)}</dd></div>
          <div><dt>Last error</dt><dd>{server.last_connection_error ?? "None"}</dd></div>
        </dl>
        {notice ? <p className="success-message">{notice}</p> : null}
        {error ? <p className="form-error">{error}</p> : null}
        <button className="secondary-button" type="button" onClick={() => void handleTest()}>
          Test connection
        </button>
      </section>
      <aside className="form-panel">
        <h2>Edit server</h2>
        <p className="form-helper">
          Leave private key blank to keep the current encrypted key. Pasting a key here is the advanced manual option.
        </p>
        <ServerForm
          form={form}
          isSubmitting={false}
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
      <label>Name<input required value={form.name} onChange={(event) => onChange({ ...form, name: event.target.value })} /></label>
      <label>Host<input required value={form.host} onChange={(event) => onChange({ ...form, host: event.target.value })} /></label>
      <label>Port<input min={1} max={65535} required type="number" value={form.port} onChange={(event) => onChange({ ...form, port: Number(event.target.value) })} /></label>
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
        <span className="field-helper">Recommended: leave blank so DeployDock generates a unique keypair for this server.</span>
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
      <p>Add this public key to the target server deploy user before testing the connection.</p>
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
  return (
    <div className="public-key-block">
      <code>{publicKey}</code>
      <button className="secondary-button" type="button" onClick={() => void navigator.clipboard?.writeText(publicKey)}>
        Copy
      </button>
    </div>
  );
}

async function loadServers(
  token: string,
  setServers: (servers: Server[]) => void,
  setError: (error: string | null) => void,
  setIsLoading: (isLoading: boolean) => void,
) {
  try {
    setServers(await listServers(token));
    setError(null);
  } catch (loadError) {
    setError(loadError instanceof Error ? loadError.message : "Could not load servers");
  } finally {
    setIsLoading(false);
  }
}

function serverStatusTone(status: ServerStatus) {
  if (status === "connected") return "success";
  if (status === "unreachable") return "danger";
  return "neutral";
}

function formatDate(value: string | null) {
  return value ? new Date(value).toLocaleString() : "Never";
}

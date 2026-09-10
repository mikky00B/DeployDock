import { navigateTo } from "../routes";

const serverSteps = [
  "Create a dedicated non-root deploy user on the target VPS.",
  "Add the server in DeployDock with its host, SSH port, and deploy username.",
  "Copy the generated public key into the deploy user's authorized_keys file.",
  "Run Test from the Servers page before registering apps.",
];

const appSteps = [
  "Choose Existing app when the app already lives on the server.",
  "Choose Bootstrap when you want DeployDock to generate setup commands first.",
  "Keep production secrets in server-side env files.",
  "Save a deploy command that exits non-zero when the release should fail.",
  "Add a public healthcheck URL when the app exposes one.",
];

const commandExamples = [
  {
    title: "Django or FastAPI",
    command: `set -e
git pull origin main
source .venv/bin/activate
pip install -r requirements.txt
alembic upgrade head
sudo systemctl restart my-app`,
  },
  {
    title: "Static site",
    command: `set -e
git pull origin main
npm ci
npm run build
sudo rsync -a --delete dist/ /var/www/my-app/
sudo nginx -t
sudo systemctl reload nginx`,
  },
];

export function DocsPage() {
  return (
    <section className="docs-layout">
      <section className="docs-hero" aria-labelledby="docs-title">
        <div>
          <p className="eyebrow">Operator guide</p>
          <h2 id="docs-title">Deploy existing VPS apps without changing your runtime</h2>
          <p>
            DeployDock connects to your servers over SSH, runs the commands you configure, streams logs, records deployment
            history, and leaves your app structure, proxy, SSL, and secrets under your control.
          </p>
        </div>
        <div className="docs-actions">
          <button className="primary-inline-button" type="button" onClick={() => navigateTo("/servers")}>
            Add server
          </button>
          <button className="secondary-button" type="button" onClick={() => navigateTo("/apps")}>
            Register app
          </button>
        </div>
      </section>

      <section className="docs-grid">
        <GuideCard title="1. Server onboarding" items={serverSteps} />
        <GuideCard title="2. App onboarding" items={appSteps} />
        <section className="docs-card">
          <h3>3. Sudo permissions</h3>
          <p>
            Grant only the commands each app needs. Prefer exact service names and binary paths instead of broad sudo
            access.
          </p>
          <pre className="command-snippet">
            <code>{`deploy ALL=(root) NOPASSWD: /bin/systemctl restart my-app
deploy ALL=(root) NOPASSWD: /bin/systemctl reload nginx
deploy ALL=(root) NOPASSWD: /usr/sbin/nginx -t`}</code>
          </pre>
        </section>
        <section className="docs-card">
          <h3>4. Release checks</h3>
          <p>
            A deployment succeeds when the command exits cleanly. A healthcheck URL gives DeployDock a second signal after
            the command completes.
          </p>
          <div className="docs-callout">
            Use a real public URL such as https://app.example.com/api/v1/health/ when the app is behind Nginx.
          </div>
        </section>
      </section>

      <section className="docs-section" aria-labelledby="command-patterns-title">
        <div className="section-heading">
          <div>
            <p className="eyebrow">Command patterns</p>
            <h2 id="command-patterns-title">Deploy commands should be explicit and repeatable</h2>
          </div>
        </div>
        <div className="docs-command-grid">
          {commandExamples.map((example) => (
            <article className="plan-section" key={example.title}>
              <div className="plan-section-heading">
                <h3>{example.title}</h3>
              </div>
              <pre className="command-snippet">
                <code>{example.command}</code>
              </pre>
            </article>
          ))}
        </div>
      </section>

      <section className="docs-section" aria-labelledby="guardrails-title">
        <div className="section-heading">
          <div>
            <p className="eyebrow">Guardrails</p>
            <h2 id="guardrails-title">Production checklist</h2>
          </div>
        </div>
        <div className="docs-check-grid">
          <CheckItem title="Keys" body="Use generated per-server keys or rotate manually uploaded keys on a schedule." />
          <CheckItem title="Secrets" body="Keep app secrets in server env files, not in deploy commands." />
          <CheckItem title="Services" body="Store systemd service names so status, restart, and journal logs work." />
          <CheckItem title="Rollback" body="Confirm the repository history and app migrations support rollback before relying on it." />
        </div>
      </section>
    </section>
  );
}

function GuideCard({ title, items }: { title: string; items: string[] }) {
  return (
    <section className="docs-card">
      <h3>{title}</h3>
      <ol className="docs-list">
        {items.map((item) => (
          <li key={item}>{item}</li>
        ))}
      </ol>
    </section>
  );
}

function CheckItem({ title, body }: { title: string; body: string }) {
  return (
    <article className="docs-check-item">
      <strong>{title}</strong>
      <p>{body}</p>
    </article>
  );
}

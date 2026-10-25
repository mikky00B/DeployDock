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

      <section className="docs-section" aria-labelledby="cli-title">
        <div className="section-heading">
          <div>
            <p className="eyebrow">Command line interface</p>
            <h2 id="cli-title">Operate DeployDock from your terminal</h2>
          </div>
        </div>
        <p className="form-helper" style={{ maxWidth: 720, marginBottom: 22 }}>
          The <code className="inline-code">deploydock</code> CLI talks to the control plane over its API — it never
          SSHes into your servers directly. Everything the dashboard can do, the CLI can script: projects, deploys, live
          logs, and rollbacks.
        </p>

        <div className="docs-command-grid">
          <article className="plan-section">
            <div className="plan-section-heading">
              <h3>Install</h3>
            </div>
            <p>
              The CLI ships in this repository and builds with any Go 1.22+ toolchain. On the machine you develop from:
            </p>
            <pre className="command-snippet">
              <code>{`git clone https://github.com/mikky00B/DeployDock.git
cd DeployDock

# Linux / macOS
go build -o deploydock ./go/cmd/deploydock

# Windows (PowerShell)
go build -o deploydock.exe ./go/cmd/deploydock

./deploydock version`}</code>
            </pre>
            <p>Move the binary somewhere on your <code className="inline-code">PATH</code> (for example <code className="inline-code">/usr/local/bin</code>).</p>
          </article>

          <article className="plan-section">
            <div className="plan-section-heading">
              <h3>Sign in</h3>
            </div>
            <p>
              Credentials are stored in <code className="inline-code">~/.config/deploydock/config.yaml</code> with
              owner-only permissions.
            </p>
            <pre className="command-snippet">
              <code>{`deploydock login --url http://127.0.0.1:8000
# Email: you@example.com
# Password: ********

deploydock whoami
deploydock logout`}</code>
            </pre>
            <p>
              For CI, skip the prompts with flags or environment variables
              (<code className="inline-code">DEPLOYDOCK_URL</code>, <code className="inline-code">DEPLOYDOCK_EMAIL</code>,{" "}
              <code className="inline-code">DEPLOYDOCK_PASSWORD</code>).
            </p>
          </article>

          <article className="plan-section">
            <div className="plan-section-heading">
              <h3>Projects</h3>
            </div>
            <pre className="command-snippet">
              <code>{`deploydock projects

deploydock project create \\
  --name watchdog \\
  --repo https://github.com/you/watchdog.git \\
  --deploy-command "make build" \\
  --port 8080 --health-path /health

deploydock project inspect watchdog
deploydock project delete watchdog`}</code>
            </pre>
            <p>
              <code className="inline-code">--server</code> is optional when exactly one server is registered; pass its
              id when you have several.
            </p>
          </article>

          <article className="plan-section">
            <div className="plan-section-heading">
              <h3>Deploy, logs, rollback</h3>
            </div>
            <pre className="command-snippet">
              <code>{`deploydock deploy watchdog
# Deploying watchdog...
#
# ✓ Stage started: clone
# Cloned in 1.2s
# ✓ SUCCESS

deploydock status --json
deploydock logs watchdog
deploydock rollback watchdog`}</code>
            </pre>
            <p>
              <code className="inline-code">deploy</code> streams the deployment live until it finishes.{" "}
              <code className="inline-code">rollback</code> re-deploys the last successful release; pass{" "}
              <code className="inline-code">--to DEPLOYMENT_ID</code> to target an older one.
            </p>
          </article>

          <article className="plan-section">
            <div className="plan-section-heading">
              <h3>Initialize a project</h3>
            </div>
            <p>
              Run <code className="inline-code">deploydock init</code> inside an app with a Dockerfile to generate a
              starting <code className="inline-code">deploydock.yaml</code>:
            </p>
            <pre className="command-snippet">
              <code>{`name: watchdog

build:
  type: docker
  dockerfile: Dockerfile

deploy:
  port: 8080

health:
  path: /health`}</code>
            </pre>
            <p>
              <code className="inline-code">deploydock deploy</code> with no arguments uses the{" "}
              <code className="inline-code">name</code> from this file.
            </p>
          </article>

          <article className="plan-section">
            <div className="plan-section-heading">
              <h3>Install the agent on a VPS</h3>
            </div>
            <p>
              The agent executes deployments on the server itself: Docker builds, health checks, nginx. Build it from
              the same repository and register it against a server you already added:
            </p>
            <pre className="command-snippet">
              <code>{`go build -o deploydock-agent ./go/cmd/deploydock-agent

# 1. Mint a registration token (from your dashboard account):
curl -X POST http://127.0.0.1:8000/api/v1/agents/registration-tokens \\
  -H "Authorization: Bearer $DEPLOYDOCK_TOKEN" \\
  -H "Content-Type: application/json" -d '{}'

# 2. On the VPS, register and run (outbound-only, no open ports):
sudo ./deploydock-agent register \\
  --server http://your-deploydock:8000 \\
  --token dck_rt_...
sudo ./deploydock-agent run

# 3. Verify:
./deploydock-agent doctor`}</code>
            </pre>
          </article>
          <article className="plan-section">
            <div className="plan-section-heading">
              <h3>Operate from your AI agent</h3>
            </div>
            <p>
              DeployDock ships a built-in MCP server. One command registers it with Claude Code, Cursor, and Codex;
              after that your agent can list apps, deploy, stream logs, and roll back by name.
            </p>
            <pre className="command-snippet">
              <code>{`deploydock mcp setup

# then, from your agent:
#   "list my DeployDock apps"
#   "deploy watchdog and follow the logs"
#   "roll back watchdog to the previous release"`}</code>
            </pre>
            <p>
              The MCP server is the CLI binary itself (<code className="inline-code">deploydock mcp serve</code>) and
              uses your stored credentials — nothing else to install.
            </p>
          </article>
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

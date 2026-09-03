import { useEffect, useRef, useState } from "react";

import { navigateTo } from "../routes";

const LOG_LINES: Array<[string, string, string]> = [
  ["17:04:02", "info", "fetching 4e0c4d3 from origin/main"],
  ["17:04:03", "ok", "✓ 214 files changed · 8.2 KiB"],
  ["17:04:04", "info", "pnpm install --frozen-lockfile"],
  ["17:04:16", "ok", "✓ 812 packages · 12.4s"],
  ["17:04:17", "info", "pnpm build"],
  ["17:04:22", "info", "compiling next · optimizing…"],
  ["17:04:54", "ok", "✓ build succeeded · 38.1s"],
  ["17:04:55", "info", "writing systemd unit web.service"],
  ["17:04:56", "info", "reloading daemon · restarting web"],
  ["17:04:57", "ok", "✓ service up · pid 24118"],
  ["17:04:58", "info", "health check GET /_health"],
  ["17:04:59", "ok", "✓ 200 OK · 41ms"],
  ["17:05:00", "ok", "✓ deploy e0c4d3 · promoted to live"],
  ["17:05:02", "info", "draining previous release · gracefully"],
  ["17:05:04", "warn", "note: postgres pool restarted (2 conns)"],
  ["17:05:06", "ok", "✓ web is live · 54.2s total"],
];

function useHeroLog() {
  const [lines, setLines] = useState<Array<[string, string, string]>>(() => LOG_LINES.slice(0, 8));
  const indexRef = useRef(0);
  const reduced = useRef(
    typeof window !== "undefined" &&
      window.matchMedia &&
      window.matchMedia("(prefers-reduced-motion: reduce)").matches,
  );

  useEffect(() => {
    if (reduced.current) return;
    const id = setInterval(() => {
      const i = indexRef.current % LOG_LINES.length;
      indexRef.current += 1;
      setLines((prev) => {
        const next = [...prev, LOG_LINES[i]];
        return next.length > 14 ? next.slice(next.length - 14) : next;
      });
    }, 1400);
    return () => clearInterval(id);
  }, []);

  return lines;
}

function BrandMark() {
  return <div className="brand-mark" aria-hidden="true" />;
}

function GitHubIcon({ size = 14 }: { size?: number }) {
  return (
    <svg width={size} height={size} viewBox="0 0 24 24" fill="currentColor">
      <path d="M12 .5C5.65.5.5 5.65.5 12c0 5.08 3.29 9.39 7.86 10.91.58.1.79-.25.79-.55v-2.14c-3.2.7-3.87-1.36-3.87-1.36-.53-1.34-1.29-1.7-1.29-1.7-1.05-.72.08-.7.08-.7 1.16.08 1.77 1.19 1.77 1.19 1.03 1.77 2.71 1.26 3.37.96.1-.75.4-1.26.73-1.55-2.55-.29-5.24-1.28-5.24-5.68 0-1.25.45-2.28 1.18-3.08-.12-.29-.51-1.47.11-3.06 0 0 .97-.31 3.18 1.18a11.02 11.02 0 0 1 5.79 0c2.21-1.49 3.18-1.18 3.18-1.18.62 1.59.23 2.77.11 3.06.74.8 1.18 1.83 1.18 3.08 0 4.41-2.69 5.38-5.25 5.66.41.36.78 1.06.78 2.14v3.18c0 .31.21.66.8.55C20.21 21.39 23.5 17.08 23.5 12 23.5 5.65 18.35.5 12 .5z" />
    </svg>
  );
}

function DownloadIcon({ size = 14 }: { size?: number }) {
  return (
    <svg width={size} height={size} viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2.4" strokeLinecap="round" strokeLinejoin="round">
      <path d="M12 3v14" />
      <path d="m6 11 6 6 6-6" />
      <path d="M5 21h14" />
    </svg>
  );
}

function CheckIcon({ size = 12, strokeWidth = 3 }: { size?: number; strokeWidth?: number }) {
  return (
    <svg width={size} height={size} viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth={strokeWidth} strokeLinecap="round" strokeLinejoin="round">
      <polyline points="20 6 9 17 4 12" />
    </svg>
  );
}

function PlusIcon({ size = 18 }: { size?: number }) {
  return (
    <svg width={size} height={size} viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round">
      <line x1="12" y1="5" x2="12" y2="19" />
      <line x1="5" y1="12" x2="19" y2="12" />
    </svg>
  );
}

function AppsIcon() {
  return (
    <svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
      <rect x="3" y="4" width="18" height="6" rx="1.5" />
      <rect x="3" y="14" width="18" height="6" rx="1.5" />
      <line x1="7" y1="7" x2="7.01" y2="7" />
      <line x1="7" y1="17" x2="7.01" y2="17" />
    </svg>
  );
}

function BoltIcon() {
  return (
    <svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
      <polygon points="13 2 3 14 12 14 11 22 21 10 12 10 13 2" />
    </svg>
  );
}

function BarsIcon() {
  return (
    <svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
      <path d="M4 6h16" />
      <path d="M4 12h10" />
      <path d="M4 18h16" />
      <circle cx="19" cy="12" r="1.5" fill="currentColor" />
    </svg>
  );
}

function RefreshIcon() {
  return (
    <svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
      <path d="M22 12A10 10 0 1 1 12 2" />
      <polyline points="22 4 12 14 9 11" />
    </svg>
  );
}

function RollbackIcon() {
  return (
    <svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
      <polyline points="1 4 1 10 7 10" />
      <path d="M3.51 15a9 9 0 1 0 2.13-9.36L1 10" />
    </svg>
  );
}

function GridIcon() {
  return (
    <svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
      <path d="M4 4h16v16H4z" />
      <path d="M4 10h16" />
      <path d="M10 4v16" />
    </svg>
  );
}

const FEATURES: Array<{ icon: () => React.ReactNode; title: string; body: string }> = [
  { icon: AppsIcon, title: "Any VPS, over SSH", body: "Bring your own servers from any provider. Ubuntu, Debian, or anywhere systemd runs." },
  { icon: BoltIcon, title: "One-click deploys", body: "Trigger from the dashboard, on git push, or via API. Cancel mid-deploy without leaving broken state." },
  { icon: BarsIcon, title: "Live log streaming", body: "Tail deploy output and app logs in real time. Filter by level, search, and pin failed runs." },
  { icon: RefreshIcon, title: "Service status & restart", body: "See what's running and what's not. Restart a service, run a health check, or SSH from the panel." },
  { icon: RollbackIcon, title: "One-click rollback", body: "Every release is a checkpoint. Ship broke? Roll back to the last known-good in seconds." },
  { icon: GridIcon, title: "Multi-app, multi-server", body: "Group apps by server or environment. Staging on one box, prod on another — one dashboard." },
];

const FAQ_ITEMS: Array<[string, string]> = [
  [
    "Is this a PaaS? Do I have to migrate my apps?",
    "No. DeployDock is a control panel, not a runtime. If your app runs today on a bare VPS under systemd or Docker, it will keep running exactly the same way — DeployDock just gives you a UI on top.",
  ],
  [
    "What kinds of apps does it support?",
    "Anything that runs as a long-lived process on Linux — Node, Python, Go, Rust, PHP, Ruby, static sites, background workers, Docker containers. If you can define a build command and a start command, it works.",
  ],
  [
    "Does it need root on my server?",
    "The agent runs as a non-root user by default. It only escalates when a specific action needs it (e.g. writing a systemd unit), and every escalation is auditable.",
  ],
  [
    "How does rollback work?",
    "Every release is a snapshot on disk with its own systemd unit. Rolling back swaps the active symlink and restarts — typically under 3 seconds. Your last N releases are kept (configurable).",
  ],
  [
    "Is it really free?",
    "Yes. DeployDock is MIT-licensed and self-hosted. There's no cloud version, no per-seat pricing, and no telemetry. You pay for your VPS; that's it.",
  ],
];

function FaqList() {
  const [open, setOpen] = useState<Record<number, boolean>>({ 0: true });

  function toggle(i: number) {
    setOpen((prev) => ({ ...prev, [i]: !prev[i] }));
  }

  return (
    <div className="faq-list">
      {FAQ_ITEMS.map(([q, a], i) => (
        <div className="faq-item" data-open={open[i] ? "true" : "false"} key={q}>
          <button
            className="faq-q"
            onClick={() => toggle(i)}
            aria-expanded={open[i] ? "true" : "false"}
            aria-controls={`faq-answer-${i}`}
          >
            {q}
            <PlusIcon />
          </button>
          <div className="faq-a" id={`faq-answer-${i}`} role="region">
            {a}
          </div>
        </div>
      ))}
    </div>
  );
}

type AppRow = {
  icon: string;
  name: string;
  meta: string;
  status: "ok" | "dep" | "warn";
  statusLabel: string;
  active?: boolean;
};

const APPS: AppRow[] = [
  { icon: "AP", name: "api-gateway", meta: "node · main@a71f", status: "ok", statusLabel: "running" },
  { icon: "WB", name: "web", meta: "next · main@e0c4", status: "dep", statusLabel: "deploying", active: true },
  { icon: "WK", name: "worker", meta: "python · main@22b1", status: "ok", statusLabel: "running" },
  { icon: "DB", name: "postgres", meta: "service · —", status: "warn", statusLabel: "restarted" },
];

const FACTS: Array<[string, string]> = [
  ["license", "MIT"],
  ["runs on", "Linux + systemd"],
  ["install size", "~ 28 MB"],
  ["deps", "none (single binary)"],
  ["telemetry", "off by default"],
];

export function LandingPage() {
  const logLines = useHeroLog();
  const [copied, setCopied] = useState(false);
  const copyTimer = useRef<number | undefined>(undefined);

  useEffect(() => () => window.clearTimeout(copyTimer.current), []);

  function copyInstall() {
    navigator.clipboard?.writeText("curl -sSL deploydock.sh/install | sh").catch(() => {});
    setCopied(true);
    window.clearTimeout(copyTimer.current);
    copyTimer.current = window.setTimeout(() => setCopied(false), 2000);
  }

  return (
    <div className="landing">
      <nav className="nav">
        <div className="wrap nav-inner">
          <div className="brand">
            <BrandMark />
            <span className="brand-name">DeployDock</span>
          </div>
          <div className="nav-links">
            <a href="#features">Features</a>
            <a href="#how">How it works</a>
            <a href="#cli">CLI</a>
            <a href="#faq">FAQ</a>
            <a href="#docs">Docs</a>
          </div>
          <div className="nav-cta">
            <a className="btn btn-ghost btn-sm" href="#github" aria-label="GitHub">
              <GitHubIcon />
              <span>GitHub</span>
            </a>
            <button className="btn btn-primary btn-sm" onClick={() => navigateTo("/login")}>
              Install
            </button>
          </div>
        </div>
      </nav>

      <section className="hero">
        <div className="hero-glow" />
        <div className="wrap hero-grid">
          <div>
            <span className="eyebrow">
              <span className="dot" /> v0.9 · public beta
            </span>
            <h1 className="headline">
              Deploy to your <em>own servers</em>. Without the yak-shaving.
            </h1>
            <p className="subhead">
              DeployDock is a self-hosted control panel for the VPS you already run. Connect a server, register an
              app, and get one-click deploys, streaming logs, and one-click rollback — without migrating to a new
              runtime.
            </p>
            <div className="hero-ctas">
              <button className="btn btn-primary" onClick={() => navigateTo("/login")}>
                <DownloadIcon />
                Install DeployDock
              </button>
              <a className="btn btn-ghost" href="#github">
                <GitHubIcon />
                Star on GitHub
                <span className="mono" style={{ color: "var(--fg-3)", fontSize: 12, marginLeft: 4 }}>
                  2.4k
                </span>
              </a>
            </div>
            <div className="install-line" onClick={copyInstall} role="button" tabIndex={0}>
              <span className="prompt">$</span>
              <span>curl -sSL deploydock.sh/install | sh</span>
              <span className="copy">{copied ? "COPIED ✓" : "COPY"}</span>
            </div>
          </div>

          <div className="product" aria-hidden="true">
            <div className="product-chrome">
              <div className="tls">
                <span />
                <span />
                <span />
              </div>
              <div className="url">dock.local · /apps</div>
            </div>
            <div className="product-body">
              <div className="apps">
                <div className="apps-head">
                  <span className="apps-title">Applications · 4</span>
                  <span className="apps-title mono" style={{ textTransform: "none" }}>
                    nyc-1.vps
                  </span>
                </div>
                {APPS.map((app) => (
                  <div className={`app${app.active ? " active" : ""}`} key={app.name}>
                    <div className="app-icon">{app.icon}</div>
                    <div className="app-name">
                      <b>{app.name}</b>
                      <span>{app.meta}</span>
                    </div>
                    <div className={`status ${app.status}`}>
                      <span className="sdot" />
                      {app.statusLabel}
                    </div>
                  </div>
                ))}
              </div>
              <div className="logs">
                <div className="logs-head">
                  <span className="logs-title">Deploy log · web</span>
                  <span className="logs-tag">
                    <span className="live" /> LIVE
                  </span>
                </div>
                <div className="log-stream">
                  {logLines.map(([t, lvl, msg], i) => (
                    <div className="log-line" key={`${t}-${i}`}>
                      <span className="t">{t}</span>
                      <span className={`lvl ${lvl}`}>{lvl.padEnd(4).toUpperCase()}</span>
                      <span>{msg}</span>
                    </div>
                  ))}
                </div>
              </div>
            </div>
          </div>
        </div>
      </section>

      <section className="wrap logos">
        <div>Trusted by developers self-hosting on</div>
        <div className="logos-row">
          <div className="logo-item">Hetzner</div>
          <div className="logo-item">DigitalOcean</div>
          <div className="logo-item">Vultr</div>
          <div className="logo-item">Linode</div>
          <div className="logo-item">OVH</div>
          <div className="logo-item">Scaleway</div>
        </div>
      </section>

      <section className="section" id="how">
        <div className="wrap">
          <div className="section-head">
            <div className="section-tag">// how it works</div>
            <h2 className="section-title">Three steps. No new runtime.</h2>
            <p className="section-sub">
              DeployDock wraps your existing setup — systemd, Docker, nginx, whatever you&apos;re already running. It
              automates; it doesn&apos;t replace.
            </p>
          </div>
          <div className="steps">
            <div className="step">
              <div className="step-num">STEP 01</div>
              <h3 className="step-title">Connect your server</h3>
              <p className="step-body">
                Point DeployDock at any VPS over SSH. It installs a lightweight agent — no daemon, no vendor lock-in,
                no reformatting.
              </p>
              <div className="step-visual">
                <span className="comment"># from the panel</span>
                <br />
                <span className="kw">dock</span> server add{" "}
                <span style={{ color: "var(--fg)" }}>root@nyc-1.vps</span>
                <br />
                <span className="comment"># ✓ agent installed in 4.1s</span>
              </div>
            </div>
            <div className="step">
              <div className="step-num">STEP 02</div>
              <h3 className="step-title">Register your app</h3>
              <p className="step-body">
                Point it at a Git repo, set a build &amp; start command, pick a target server. DeployDock generates
                the systemd unit for you.
              </p>
              <div className="step-visual">
                repo: <span style={{ color: "var(--fg)" }}>github.com/you/web</span>
                <br />
                build: <span className="kw">pnpm build</span>
                <br />
                start: <span className="kw">pnpm start</span>
                <br />
                port: <span style={{ color: "var(--fg)" }}>3000</span>
              </div>
            </div>
            <div className="step">
              <div className="step-num">STEP 03</div>
              <h3 className="step-title">Deploy, stream, rollback</h3>
              <p className="step-body">
                Trigger deploys from the dashboard or on push. Watch logs stream live. If something breaks, one-click
                rollback to the last good release.
              </p>
              <div className="step-visual">
                <span className="comment"># release timeline</span>
                <br />
                <span className="kw">✓</span> e0c4d3 <span className="comment">— 2m ago (current)</span>
                <br />
                <span className="kw">✓</span> a71f22 <span className="comment">— 3h ago</span>
                <br />
                <span style={{ color: "var(--err)" }}>✗</span> 9b3fa1{" "}
                <span className="comment">— failed, rolled back</span>
              </div>
            </div>
          </div>
        </div>
      </section>

      <section className="section" id="features">
        <div className="wrap">
          <div className="section-head">
            <div className="section-tag">// capabilities</div>
            <h2 className="section-title">Everything you&apos;d script yourself, in one panel.</h2>
            <p className="section-sub">
              Built for the shape of infrastructure you already have. No rewriting your app for someone else&apos;s
              runtime.
            </p>
          </div>
          <div className="features">
            {FEATURES.map((f) => {
              const Icon = f.icon;
              return (
                <div className="feature" key={f.title}>
                  <div className="feature-icon">
                    <Icon />
                  </div>
                  <h3>{f.title}</h3>
                  <p>{f.body}</p>
                </div>
              );
            })}
          </div>
        </div>
      </section>

      <section className="section" id="cli">
        <div className="wrap cli-wrap">
          <div>
            <div className="section-tag">// prefers-the-terminal</div>
            <h2 className="section-title" style={{ marginTop: 12 }}>
              The panel is optional.
            </h2>
            <p className="section-sub" style={{ marginBottom: 32 }}>
              Everything DeployDock can do, the CLI can do too. Deploys, logs, rollbacks — scriptable from CI or your
              laptop.
            </p>
            <div className="cli-points">
              <div className="cli-point">
                <div className="cli-point-check">
                  <CheckIcon />
                </div>
                <div>
                  <h4>Scriptable everything</h4>
                  <p>Every dashboard action is a CLI command. Wire it into your CI, cron, or a Makefile.</p>
                </div>
              </div>
              <div className="cli-point">
                <div className="cli-point-check">
                  <CheckIcon />
                </div>
                <div>
                  <h4>Piped log streams</h4>
                  <p>
                    <code className="mono" style={{ color: "var(--fg)" }}>
                      dock logs web -f
                    </code>{" "}
                    in one pane, deploys running in another. Works over SSH the way you&apos;d expect.
                  </p>
                </div>
              </div>
              <div className="cli-point">
                <div className="cli-point-check">
                  <CheckIcon />
                </div>
                <div>
                  <h4>Config as code</h4>
                  <p>
                    Commit{" "}
                    <code className="mono" style={{ color: "var(--fg)" }}>
                      dock.yaml
                    </code>{" "}
                    to your repo. Reproducible setups across servers, branches, and clones.
                  </p>
                </div>
              </div>
            </div>
          </div>
          <div className="terminal">
            <div className="terminal-chrome">
              <div className="tls">
                <span />
                <span />
                <span />
              </div>
              <div className="url">~/projects/web · zsh</div>
            </div>
            <div className="terminal-body">
              <div>
                <span className="tprompt">$</span> dock deploy web
              </div>
              <div>
                <span className="tcomment"># target: nyc-1.vps · branch: main</span>
              </div>
              <div>→ fetching 4e0c4d3…</div>
              <div>
                → pnpm install <span className="tcomment"># 12.4s</span>
              </div>
              <div>
                → pnpm build <span className="tcomment"># 38.1s</span>
              </div>
              <div>→ handing off to systemd</div>
              <div>
                → health check <span className="tok">✓ 200 OK</span>
              </div>
              <div>
                <span className="tok">✓</span> deployed in 54.2s ·{" "}
                <a style={{ color: "var(--accent)", textDecoration: "underline" }}>e0c4d3</a>
              </div>
              <div>&nbsp;</div>
              <div>
                <span className="tprompt">$</span> dock logs web -f
              </div>
              <div>
                <span className="tcomment">17:04:12</span> info server listening on :3000
              </div>
              <div>
                <span className="tcomment">17:04:14</span> info connected to postgres
              </div>
              <div>
                <span className="tcomment">17:04:22</span> <span className="tok">200</span> GET /api/users 42ms
              </div>
              <div>
                <span className="tcomment">17:04:23</span> <span className="tok">200</span> GET /pricing 18ms
                <span className="cursor" />
              </div>
            </div>
          </div>
        </div>
      </section>

      <section className="section" id="selfhost">
        <div className="wrap">
          <div className="callout">
            <div>
              <div className="section-tag" style={{ color: "var(--accent)" }}>
                // self-hosted, MIT
              </div>
              <h2>Free. Open source. Yours.</h2>
              <p>
                Runs on the same hardware you&apos;re already paying for. No seat pricing, no build-minute pricing, no
                vendor account holding your infrastructure hostage.
              </p>
              <div style={{ marginTop: 28, display: "flex", gap: 10, flexWrap: "wrap" }}>
                <button className="btn btn-primary" onClick={() => navigateTo("/login")}>
                  <DownloadIcon />
                  Install DeployDock
                </button>
                <a className="btn btn-ghost" href="#docs">
                  Read the docs →
                </a>
              </div>
            </div>
            <div className="callout-facts">
              {FACTS.map(([k, v]) => (
                <div className="callout-fact" key={k}>
                  <span className="k">{k}</span>
                  <span className="v">{v}</span>
                </div>
              ))}
            </div>
          </div>
        </div>
      </section>

      <section className="section" id="faq">
        <div className="wrap" style={{ maxWidth: 820, margin: "0 auto" }}>
          <div className="section-head">
            <div className="section-tag">// questions</div>
            <h2 className="section-title">Frequently asked.</h2>
          </div>
          <FaqList />
        </div>
      </section>

      <section className="final-cta">
        <div className="wrap">
          <h2>Own your deploys.</h2>
          <p>Install DeployDock on any VPS in under 60 seconds. Bring your servers; keep your workflow.</p>
          <div style={{ display: "flex", gap: 12, justifyContent: "center", flexWrap: "wrap" }}>
            <button className="btn btn-primary" onClick={() => navigateTo("/login")}>
              Install DeployDock
            </button>
            <a className="btn btn-ghost" href="#github">
              View on GitHub
            </a>
          </div>
        </div>
      </section>

      <footer className="footer">
        <div className="wrap footer-inner">
          <div className="footer-brand">
            <div className="brand">
              <BrandMark />
              <span className="brand-name">DeployDock</span>
            </div>
            <p>Self-hosted deployment control for developers who already run their own servers.</p>
          </div>
          <div className="footer-cols">
            <div className="footer-col">
              <h5>Product</h5>
              <a href="#features">Features</a>
              <a href="#how">How it works</a>
              <a href="#cli">CLI</a>
              <a href="#faq">FAQ</a>
            </div>
            <div className="footer-col">
              <h5>Developers</h5>
              <a href="#docs">Documentation</a>
              <a href="#docs">Install guide</a>
              <a href="#docs">CLI reference</a>
              <a href="#docs">Changelog</a>
            </div>
            <div className="footer-col">
              <h5>Community</h5>
              <a href="#github">GitHub</a>
              <a href="#discord">Discord</a>
              <a href="#issues">Issues</a>
              <a href="#security">Security</a>
            </div>
          </div>
        </div>
        <div className="wrap footer-bottom">
          <div>© 2026 DeployDock · MIT License</div>
          <div>v0.9.2 · git@e0c4d3</div>
        </div>
      </footer>
    </div>
  );
}

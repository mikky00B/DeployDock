# Competitive & AI-Trend Research — InstaCloud, Aeroplane, and the 2026 Agent Wave

**Date:** October 2026
**Scope:** Deep-dive on two reference projects ([InstaCloud](https://www.instacloud.com/), [Aeroplane](https://aeroplane.run/)), the 2026 AI-agentic trend line, and what DeployDock should learn from each. Findings are mapped to our existing roadmap (see `SPEC_PROGRESS.md`) rather than replacing it.

---

## 1. Executive summary

Three takeaways that should shape DeployDock's next moves:

1. **The market split we sit inside is real and both halves are winning.** InstaCloud is *agent-native but cloud-only* (you deploy on their infrastructure, agents operate it). Aeroplane is *self-hosted but agentless* (your VPS, human-operated). **DeployDock's architecture — self-hosted, with an execution agent and a command queue — already owns the intersection: "the agent-operable, self-hosted deployment platform." Nobody in this comparison occupies that position. Our job is to say it out loud and build the two features that prove it.**
2. **The 2026 trend is "agents operate, humans approve."** InstaCloud's whole product is an activity feed where agents propose infrastructure actions and humans approve (or auto-approve) them. Our command-queue + audit-log architecture is naturally suited to the same model — we just don't expose it as a product surface yet.
3. **Machine-readability is now a distribution channel.** InstaCloud ships an `llms.txt` index for coding agents; Dokploy already generates one. An MCP server + `llms.txt` would make DeployDock operable directly from Claude Code / Cursor, which is where a growing share of deployments originate.

---

## 2. InstaCloud — agent-native serverless cloud

**Product:** "Agent-Native Serverless Cloud" by InsForge, Inc. (Y Combinator–backed). Positioning: *"Agents Don't Just Write Code. They Operate the Infrastructure"* — with humans reviewing and approving critical changes. Target: developers using AI coding agents who want infrastructure handled from provisioning to production.

### 2.1 How it works

- **Agent wiring is a first-class install step:** `npx insta@latest agent setup` installs the CLI *and* configures coding agents on the machine (Claude Code, Cursor, Codex, "or any agent the setup wired"). There is also a shell installer (`curl -fsSL https://agents.instacloud.com | sh`).
- **Prompt-driven deployment:** a developer says *"Deploy this app on InstaCloud with a Postgres database wired in"*, does a one-time login, and the agent drives the rest — resulting in "a running app on its own URL, with its database connection injected."
- **Primitives agents operate on:** real Postgres, S3-compatible buckets, and containers running in **microVMs** on the hosted platform.
- **Approval workflow (the trust model):** the dashboard shows an agent activity feed with **"Auto-approved"** and **"Pending…"** actions — e.g. "Fixed high usage alert", "Recommend to deploy a Redis service". Humans approve or delegate; critical changes are gated.
- **Instant branching:** clone whole environments so agents can work in parallel, reproduce incidents, and test changes without touching production.
- **Agent Directory** and templated deploys ("deploy hermes agent from template").
- **Docs are agent-readable:** an `llms.txt` index at docs.instacloud.com exists specifically so coding agents can discover documentation pages.

### 2.2 Pricing model

Usage-based with a monthly credit, not per-seat:

| Tier | Price | Notes |
|---|---|---|
| Free | $0/mo | $10 usage credit/month; up to 4 vCPU / 4 GB / 1 GB volume per service; projects pause when credit runs out |
| Pro | $20/mo minimum | $20 usage credit; up to 8 vCPU / 8 GB / 10 GB volume; vertical scaling and replicas |
| Team | $499/mo | Usage billed on top; 100 services/env; SOC 2, SSO; HIPAA as paid add-on; dedicated Slack |
| Enterprise | custom | SLAs, BAAs, security reviews |

Compute is metered per second ($0.00000772/vCPU-sec, $0.00000386/GB-sec, $0.05/GB egress).

### 2.3 What to learn from InstaCloud

- **The approval-gate pattern is the answer to "isn't an agent operating prod scary?"** Actions are proposed, shown in a feed, and either auto-approved (low-risk, pre-authorized classes) or queued for human approval. DeployDock already has the hard parts: a command queue, an audit log, and an agent that executes structured commands rather than arbitrary shell. What's missing is the *feed + approval* product surface.
- **`agent setup` is the growth loop.** One command wires every coding agent on the developer's machine to the platform. After that, deploying is a sentence, not a form.
- **Instant branching is the agent-scale feature.** Agents generate lots of parallel attempts; cheap isolated environments make that safe. Our "Instant Branching" equivalent would be per-agent temporary environments/ports on the VPS.
- **`llms.txt` is cheap distribution.** It makes the docs discoverable to the agents that are increasingly the ones "reading" them.
- **Do not copy:** the closed, cloud-only model (usage billing, microVMs) — that's a different business; our identity is self-hosted MIT.

---

## 3. Aeroplane — self-hosted deployment control plane (direct competitor)

**Product:** open-source ([github.com/xt42io/aeroplane](https://github.com/xt42io/aeroplane), Apache-2.0, ~281 stars, 1,300+ commits) self-hosted control plane: *"Deploy apps and databases on your own server."* Railway-like workflows, 100% free, control plane stays on infrastructure you own. Target: small teams and personal infrastructure.

### 3.1 How it works technically

- **Install:** one-liner on a fresh Ubuntu/Debian host — `curl -fsSL https://get.aeroplane.run | sh` — creating `/opt/aeroplane` and three services: the control plane (systemd, port 4310), a BuildKit builder, and Caddy on host ports 80/443.
- **Stack (single language, deliberately simple):** TypeScript throughout — React + Vite dashboard, Hono on Node.js control plane, SQLite + Drizzle, Docker Engine API, Caddy, **Railpack + BuildKit** for builds.
- **Builds:** Railpack (auto-detects the stack and generates a container build) executed through BuildKit — *users do not need to write a Dockerfile*. Raw Docker images are also supported directly.
- **Routing & HTTPS:** Caddy handles all routes and **certificates automatically**; a wildcard root domain (`*.pilot.example.com`) auto-generates a URL per service; custom domains work once DNS points at the VPS.
- **Deploy lifecycle:** queued → building → running, with **aborted** and **`superseded`** states, plus a global concurrency limit for concurrent deployments.
- **Databases:** Postgres/Redis/MongoDB provisioned and managed, with data browsing/editing, and backups to **disk, Cloudflare R2, or both** on daily/weekly/monthly schedules with restore/download.
- **GitHub integration via a GitHub App** (Contents: Read, Metadata: Read, subscribed to the Push webhook) — no manual webhook-secret plumbing.
- **Browser onboarding wizard:** owner account, dashboard domain, GitHub connection, backup target — or restore from a **`.aeroplane` encrypted migration bundle** (instance-to-instance migration).
- **Provider migration (the growth feature):** "Migrate from Railway" imports projects via API token — recreates services, maps env vars, deploys databases first, then pulls Postgres/Redis data. A Vercel importer exists too.

### 3.2 What to learn from Aeroplane

- **Railpack/buildpack-style builds are the single biggest UX gap between them and us.** Our agent requires the user to supply a Dockerfile plus a container port. Aeroplane detects the stack and builds. For the "I have an app, deploy it" user, that's the difference between 2 minutes and an afternoon.
- **Caddy > nginx for this product.** Caddy issues and renews certificates automatically and takes tiny config files. Our agent already hides proxying behind the `ProxyManager` interface (nginx implementation + no-op fallback) — a Caddy implementation slots straight in and gives us automatic HTTPS that our nginx path can't match without certbot work.
- **`superseded` is a state we're missing.** When a queued deployment is made obsolete by a newer push, running stale code is wasteful and confusing. Aeroplane marks it superseded. Our 12-state pipeline plus queue makes this a natural addition.
- **GitHub App > manual webhook secrets.** Their flow installs an app with a Push webhook pointed at the control plane — no per-app secret minting, no HMAC plumbing for the user to manage. Our webhook system works, but it's the manual era of the same idea.
- **Wildcard root domain = instant URLs.** Every service gets `name.pilot.example.com` without the user touching DNS. Our domain verification feature handles custom domains, but we have no zero-config default URL story.
- **Onboarding wizard + one-liner installer** — we promised an install script on the landing page that doesn't exist yet; Aeroplane's is a real one that prepares the host.
- **Migration imports are a growth weapon.** "Migrate from Railway/Vercel" captures users fleeing vendor lock-in with their config and data — and those are exactly the users our landing page speaks to.
- **Cautionary note:** SQLite as the control-plane database is fine for a single host, but it caps multi-server ambitions; our FastAPI + Postgres control plane is the stronger foundation for the same product.

---

## 4. Head-to-head against DeployDock (October 2026)

| Capability | InstaCloud | Aeroplane | DeployDock (today) |
|---|---|---|---|
| Self-hosted, open control plane | ✗ (cloud only) | ✓ | ✓ |
| Execution agent on the VPS | ✓ (their infra) | ✗ (control plane runs everything locally) | ✓ (Go agent, outbound-only) |
| Command queue + audit trail | ✓ (agent feed) | partial | ✓ |
| Deploys without a Dockerfile | ✓ | ✓ (Railpack) | ✗ (SSH path: your own commands; agent path: Dockerfile required) |
| Zero-downtime health-gated switch | ✓ | ✓ | ✓ (agent path) |
| Automatic HTTPS | ✓ (hosted) | ✓ (Caddy) | ✗ (nginx, manual certs; certbot hook only) |
| Native databases (Postgres/Redis) | ✓ (managed) | ✓ (managed + backups) | ✗ (explicit non-goal for MVP, spec §52) |
| GitHub push-to-deploy | ✓ | ✓ (GitHub App) | ✓ (manual webhook secret) |
| Env vars per environment | ✓ | ✓ | ✓ (encrypted, masked) |
| Domains | ✓ | ✓ + wildcard auto-URLs | ✓ (DNS verification; no auto-URL) |
| Backups | ✓ (managed) | ✓ (disk/R2, scheduled) | ✗ (spec §53 future) |
| Deployment cancel | ✓ | ✓ (abort) | ✓ |
| Obsolete-deploy handling | n/a | `superseded` state | ✗ (queued runs even if stale) |
| AI-agent operability | ✓✓ (core product) | ✗ | partial (API + queue exist; no agent wiring, no MCP) |
| `llms.txt` docs | ✓ | ✗ | ✗ |
| One-line installer | ✓ | ✓ | ✗ (docs say `git clone`) |
| Provider migration import | ✗ | ✓ (Railway/Vercel) | ✗ |
| Pricing | usage + tiers | free (self-hosted) | free (self-hosted, MIT) |

---

## 5. Where AI is in 2026 — the trend line that matters for DeployDock

1. **Agentic DevOps is the defining 2026 pattern.** Analysts describe AI agents autonomously *planning, executing, and optimizing* DevOps workflows; the AI-agents-for-IT-operations market is growing at roughly 29% CAGR, with autonomous incident resolution as the flagship use case. The tools that win are the ones agents can *operate*, not just read.
2. **MCP (Model Context Protocol) is the integration standard.** Google Cloud, Databricks, Northflank, and TrueFoundry all ship MCP-server guidance/infrastructure; Claude Code and Cursor are the primary clients. A platform without an MCP surface is invisible to this workflow.
3. **The "vibe coding" wave needs a landing spot.** A 2026 content genre is now "where do I deploy AI-generated apps" (Vercel vs Railway vs Render comparisons). Agents generate the app; the question is who runs it. Self-hosted platforms are largely absent from those answers because most aren't agent-operable.
4. **Human-approval gates are the trust model.** InstaCloud's auto-approved vs pending-action feed is the emerging UX for letting agents touch production without surrendering control.
5. **`llms.txt` adoption is real.** Machine-readable doc indexes for agents are being added across docs platforms, and competitors (Dokploy) already generate one.

---

## 6. What DeployDock should do — prioritized recommendations

Mapped to our existing phases in `SPEC_PROGRESS.md`. Items marked ★ are new scope this research adds.

### Quick wins (days, high leverage)

| # | Action | Why | Effort |
|---|---|---|---|
| 1 | **`llms.txt`** index for our `docs/` + a machine-readable endpoint | Instant agent discoverability; competitor Dokploy already ships one | ~1 hour |
| 2 | **MCP server** (`deploydock-mcp`, Go or Python) exposing: `list_servers`, `list_apps`, `deploy_app`, `get_status`, `get_logs`, `rollback`, `list_deployments` | This is the single highest-impact AI move: Claude Code/Cursor can then deploy/operate DeployDock directly. Our control-plane API + command queue already implement everything an MCP tool needs — this is an adapter, not a feature | 2–4 days |
| 3 | **`deploydock agent setup`** command in the CLI — wires Claude Code/Cursor/Codex config to the control plane (URL, token, MCP registration) | InstaCloud's growth loop; our CLI is the natural place | 1–2 days |
| 4 | Make the **Agent button flow prompt-driven**: after registration, show the exact sentence an agent can be given ("Deploy watchdog to nyc-1") | Bridges the gap between human UI and agent operation | hours |

### Near-term product (weeks — fold into Phase 5)

| # | Action | Why | Effort |
|---|---|---|---|
| 5 | **Dockerfile templates + auto-generation** in the agent engine: if the workspace has no Dockerfile, generate one from detected stack (our bootstrap planner already knows Django/FastAPI/Go/static), then build | Closes the biggest gap vs Aeroplane's Railpack builds; users shouldn't need a Dockerfile | 1 week |
| 6 | **Caddy `ProxyManager` implementation** alongside nginx (the interface exists): automatic Let's Encrypt certs, tiny per-app config blocks | Automatic HTTPS with near-zero work — our nginx path can't do this without certbot plumbing | 3–5 days |
| 7 | **`superseded` deployment state**: when a queued deployment is obsoleted by a newer successful push for the same environment, mark it superseded instead of running stale code | Aeroplane-validated state; our pipeline + queue make it cheap | 2–3 days |
| 8 | **One-line installer** (`get.deploydock.tech` script or a documented compose one-liner on the landing page) | Our landing page already implies this exists; Aeroplane proves it's table stakes | 1–2 days |

### Strategic (next quarter)

| # | Action | Why | Effort |
|---|---|---|---|
| 9 | **Agent activity feed + approval gates** in the dashboard: render the command queue and audit log as InstaCloud-style "proposed / auto-approved / pending" actions; add an approval requirement flag for risky agent-driven operations | The trust model that makes agent-operated infrastructure sellable; we already store every input needed | 1–2 weeks |
| 10 | **GitHub App integration** (Contents: Read + Metadata + Push webhook) replacing manual per-app webhook secrets | Modern standard; removes our webhook-secret minting UX entirely | 3–5 days |
| 11 | **Wildcard root domain → auto URLs** per app in the agent's proxy config | Zero-config URLs; our domain verification already covers custom domains | 2–3 days |
| 12 | **Provider migration importer** (start with Railway: services, env vars, domains) | Captures lock-in refugees with config and data; strongest growth lever either competitor has validated | 1–2 weeks |
| 13 | **Positioning update**: landing page headline direction — *"DeployDock: the self-hosted deployment platform your AI agent can operate"* (agent-native + self-hosted, the intersection nobody occupies) | Both competitors validate each half; nobody owns the combination | copywriting |

### Deliberately not copied

- **InstaCloud's hosted/usage-billing model** — different business; our MIT self-hosted identity is the differentiator.
- **Aeroplane's SQLite control plane** — fine for one host; our Postgres control plane is what makes multi-server (spec §56) credible later.
- **Managed databases** — both competitors offer them; remains spec §52 non-goal until the core is rock-solid.

---

## 7. Sources

- [InstaCloud — product site](https://www.instacloud.com/) · [pricing](https://www.instacloud.com/pricing) · [docs](https://docs.instacloud.com/)
- [Aeroplane — product site](https://aeroplane.run/) · [docs](https://aeroplane.run/docs) · [GitHub (xt42io/aeroplane)](https://github.com/xt42io/aeroplane)
- [Agentic AI in DevOps — DeployFlow (Mar 2026)](https://deployflow.co)
- [The Rise of Agentic DevOps — AdaSci (Jan 2026)](https://adasci.org)
- [AI Agents for IT Operations Market — DataM Intelligence (Aug 2026)](https://www.datamintelligence.com)
- [What is MCP — Google Cloud](https://cloud.google.com/discover/what-is-model-context-protocol) · [MCP Server Architecture — Zuplo (May 2026)](https://zuplo.com) · [Deploying MCP servers — Northflank](https://northflank.com)
- [llms.txt implementations — Mintlify (Mar 2026)](https://www.mintlify.com) · [Dokploy llms.txt — SiteSpeak](https://sitespeak.ai)
- [Deploying AI-generated apps in 2026 — Zoho Catalyst (Sep 2026)](https://catalyst.zoho.com)

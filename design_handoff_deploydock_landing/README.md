# Handoff: DeployDock Landing Page

## Overview

The marketing landing page for **DeployDock** — a self-hosted deployment control panel for developers and small teams who already run apps on VPS servers. The page's job is to convert two audiences: (a) individual developers who want a Heroku-like UI on top of their existing VPS, and (b) small teams who want a shared dashboard for deploys/logs/rollbacks without migrating to a PaaS.

Primary CTA: **Install DeployDock** (self-hosted install). Secondary CTA: **View / Star on GitHub**.

## About the Design Files

The files in this bundle are **design references created in HTML** — a working prototype that shows the intended look, layout, motion, and interactive behavior. **They are not production code to copy directly.**

Your task is to **recreate these designs in the target codebase's existing environment**, using its established patterns and libraries (Next.js + Tailwind, Astro, Nuxt, plain HTML template, etc.). If no environment exists yet, choose the most appropriate stack for a marketing page — **Next.js (App Router) + Tailwind CSS** is the recommended default; the design tokens map cleanly to Tailwind's config.

Do not ship the raw HTML. In particular:
- The Tweaks panel (`tweaks_panel.jsx` and everything under `#tweaks-root`) is a **design-time affordance only** — it exists so the designer/PM can toggle theme, accent color, and hero copy inside the design tool. **Remove it from production.**
- The Babel-in-browser React setup is for the prototype only. Use the target codebase's build pipeline.
- The `window.genspark`/`window.claude` reference (if any) is design-tool tooling — strip it.

## Fidelity

**High-fidelity (hifi).** The prototype specifies final colors, typography, spacing, motion, and interactions. Recreate pixel-perfectly. All design tokens are enumerated in the "Design Tokens" section below and can be lifted verbatim.

## Screens / Views

This is a single long-scroll landing page with a sticky nav. Section order top-to-bottom:

1. Sticky nav
2. Hero (headline + CTAs + live product mock)
3. Logo cloud (VPS provider names)
4. How it works (3 steps)
5. Feature grid (6 tiles)
6. CLI showcase (terminal + benefit list)
7. Self-host callout (MIT / open source)
8. FAQ (5 items, accordion)
9. Final CTA
10. Footer

Detailed spec per section below.

---

### 1. Sticky Nav

- **Purpose:** Anchor navigation + persistent Install CTA.
- **Layout:** Full-width, `position: sticky; top: 0; z-index: 30`. Height **62px**. `backdrop-filter: blur(14px)` over a semi-transparent bg (`color-mix(in oklab, var(--bg) 78%, transparent)`). Bottom border `1px solid var(--line-soft)`.
- **Inner container:** `max-width: 1240px`, horizontal padding `32px` desktop / `20px` mobile, flex row `justify-content: space-between`.
- **Left — Brand:**
  - 26×26 `border-radius: 7px` square filled with `--accent`. Contains a small "dock" glyph drawn with two horizontal bars + three vertical strokes (see `.brand-mark::before` / `::after` in the CSS). Inner shadow: `inset 0 1px 0 color-mix(in oklab, white 25%, transparent)`, outer ring: `0 0 0 1px color-mix(in oklab, var(--accent) 40%, transparent)`.
  - Wordmark "DeployDock", Inter Tight 600, 15px, letter-spacing -0.01em, gap 10px from mark.
- **Center — Links:** `Features · How it works · CLI · FAQ · Docs`. Inter Tight 400, 14px, color `--fg-2`, hover → `--fg`. Gap 28px. Hidden below 780px.
- **Right — CTA cluster:** GitHub icon button (ghost 34px) + primary "Install" button (34px). Gap 10px.

### 2. Hero

- **Purpose:** State the value prop and expose the primary CTA + a "this is real software" product mock.
- **Section padding:** `88px 0 40px`. Position relative (contains ambient glow).
- **Ambient glow:** Absolutely positioned 700×700 radial gradient, top -100px right -100px, `filter: blur(20px)`, color `color-mix(in oklab, var(--accent) 22%, transparent)`. Behind content (`z-index: -1`).
- **Grid:** 2 columns `1.05fr 1fr`, gap 56px, `align-items: center`. Collapses to single column below 980px (gap 40px).
- **Left column:**
  - **Eyebrow pill:** `v0.9 · public beta` preceded by a 6px green (`--ok`) dot with glow. JetBrains Mono 12px, `--fg-2`, padding 5px 10px, `border-radius: 999px`, bg `--bg-2`, border `1px solid --line`.
  - **Headline (`h1`):** `clamp(40px, 5.6vw, 68px)`, line-height 1.02, letter-spacing -0.035em, weight 600, `text-wrap: balance`. Copy: *"Deploy to your own servers. Without the yak-shaving."* The words **"own servers"** are wrapped in `<em>` (styled `font-style: normal; color: var(--accent);`).
  - **Subhead:** 18px, `--fg-2`, `max-width: 540px`, `text-wrap: pretty`. Copy: *"DeployDock is a self-hosted control panel for the VPS you already run. Connect a server, register an app, and get one-click deploys, streaming logs, and one-click rollback — without migrating to a new runtime."*
  - **CTA row (margin-top 28px, gap 10px):**
    - Primary button "Install DeployDock" with a download-arrow icon (14×14).
    - Ghost button "Star on GitHub" with GitHub octocat icon + count "2.4k" in JetBrains Mono 12px, color `--fg-3`.
  - **Install command box (margin-top 22px):** Inline-flex pill. Padding 10px 14px, bg `--bg-2`, border `1px solid --line`, `border-radius: 8px`. Content: green `$` prompt (color `--accent`) · `curl -sSL deploydock.sh/install | sh` in JetBrains Mono 13px · "COPY" hint in `--fg-3` 11px. Cursor pointer; click copies to clipboard. Hover → border `--fg-3`.
- **Right column — Product mock ("live dashboard"):**
  - Card: `border-radius: 14px`, bg `--bg-2`, border `1px solid --line`. Multi-layer shadow: `0 40px 80px -40px rgba(0,0,0,0.6)` + accent inner ring `0 0 0 1px color-mix(in oklab, var(--accent) 8%, transparent)`.
  - **Chrome bar:** padding 12px 14px, bottom border `--line-soft`, bg `color-mix(in oklab, var(--bg-3) 60%, transparent)`. Contains: 3 traffic-light dots (red/yellow/green, `oklch(0.68 0.18 25)` / `oklch(0.80 0.16 85)` / `oklch(0.72 0.15 155)`), centered URL "dock.local · /apps" in JetBrains Mono 11px `--fg-3`.
  - **Body grid:** 2 columns `1.15fr 1fr`, min-height 380px. Collapses to 1 column below 620px.
  - **Left pane — Apps list:**
    - Padding 16px, right border `--line-soft`, vertical flex gap 8px.
    - Header row: "Applications · 4" (uppercase, letter-spacing 0.08em, 12px `--fg-3`) + right-aligned "nyc-1.vps" in JetBrains Mono.
    - **App row template:** Grid `22px 1fr auto`, gap 10px, padding 10px 12px, `border-radius: 8px`, bg `--bg`, border `1px solid --line-soft`. Hover → border `--line`. Active state (`.app.active`) → border `color-mix(in oklab, var(--accent) 55%, var(--line))`, bg `color-mix(in oklab, var(--accent) 6%, var(--bg))`.
    - Icon square: 22×22, `border-radius: 5px`, bg `--bg-3`, contains 2-letter monogram in JetBrains Mono 10px 600.
    - Name column: Bold app name (500 weight, letter-spacing -0.01em) over 11px JetBrains Mono meta line (`--fg-3`).
    - Status pill (right): Inline-flex, gap 6px, JetBrains Mono 10.5px, padding 3px 8px, `border-radius: 999px`, bg `--bg-2`, border `1px solid --line-soft`. Contains 6×6 status dot + label.
      - `ok` — green dot `--ok`, 6px glow.
      - `warn` — amber dot `--warn`, 6px glow.
      - `err` — red dot `--err`, 6px glow.
      - `dep` (deploying) — accent-color dot with **1.1s pulse animation** (`@keyframes pulse`, 0-60% expanding box-shadow to transparent).
    - **Rows shown (in this exact order):**
      1. `api-gateway` — `AP` icon — `node · main@a71f` — status `ok · running`
      2. `web` — `WB` icon — `next · main@e0c4` — status `deploying` (accent pulse) — **active row**
      3. `worker` — `WK` icon — `python · main@22b1` — status `ok · running`
      4. `postgres` — `DB` icon — `service · —` — status `warn · restarted`
  - **Right pane — Log stream:**
    - Padding 14px 16px. Background: radial gradient from top-right in accent (10%) over `--bg-2`.
    - Header: "Deploy log · web" (uppercase 12px `--fg-3`) + "LIVE" tag with pulsing red 6px dot (`--err`, 1.4s pulse).
    - **Stream area:** JetBrains Mono 11.5px, line-height 1.65, color `--fg-2`. Bottom 60px fade to `--bg-2` via `::after` gradient.
    - Each line: `<time>` in `--fg-3` · fixed-width 42px `<level>` label · message. Level colors: `info` `--fg-2`, `ok` `--ok`, `warn` `--warn`, `err` `--err`.
    - **Behavior:** New line pushed every **1400ms**. Cap the DOM at 14 lines (drop oldest). Seed with 8 lines on load. Cycle through this exact sequence (loop):
      ```
      17:04:02 INFO  fetching 4e0c4d3 from origin/main
      17:04:03 OK    ✓ 214 files changed · 8.2 KiB
      17:04:04 INFO  pnpm install --frozen-lockfile
      17:04:16 OK    ✓ 812 packages · 12.4s
      17:04:17 INFO  pnpm build
      17:04:22 INFO  compiling next · optimizing…
      17:04:54 OK    ✓ build succeeded · 38.1s
      17:04:55 INFO  writing systemd unit web.service
      17:04:56 INFO  reloading daemon · restarting web
      17:04:57 OK    ✓ service up · pid 24118
      17:04:58 INFO  health check GET /_health
      17:04:59 OK    ✓ 200 OK · 41ms
      17:05:00 OK    ✓ deploy e0c4d3 · promoted to live
      17:05:02 INFO  draining previous release · gracefully
      17:05:04 WARN  note: postgres pool restarted (2 conns)
      17:05:06 OK    ✓ web is live · 54.2s total
      ```

### 3. Logo Cloud

- Padding `40px 0 24px`. Centered.
- Caption: "Trusted by developers self-hosting on" — JetBrains Mono 12px uppercase, letter-spacing 0.08em, color `--fg-3`.
- Grid: 6 columns (3 columns below 780px), gap 20px, opacity 0.75.
- Each cell: Inter Tight 600, 15px, letter-spacing -0.01em, color `--fg-2`, centered, padding 8px 0.
- **Names (left to right):** Hetzner · DigitalOcean · Vultr · Linode · OVH · Scaleway.
- These are **plain-text wordmarks**, not real logos. If licensing/legal for real logos is cleared, swap to SVG marks; otherwise keep the type-only treatment.

### 4. How It Works

- Section: `padding: 88px 0`, top border `1px solid --line-soft`.
- Section head (max-width 640px, margin-bottom 48px):
  - Tag: `// how it works` — JetBrains Mono 12px uppercase, color `--accent`, letter-spacing 0.08em.
  - Title: `clamp(28px, 3.4vw, 42px)`, letter-spacing -0.03em, weight 600, `text-wrap: balance`. Copy: *"Three steps. No new runtime."*
  - Sub: 17px, `--fg-2`, max-width 560px. Copy: *"DeployDock wraps your existing setup — systemd, Docker, nginx, whatever you're already running. It automates; it doesn't replace."*
- **Step grid:** 3 columns, gap 24px. Collapses to 1 column below 860px.
- **Step card:** Border `1px solid --line-soft`, `border-radius: 12px`, padding 24px, bg `--bg-2`.
  - Step number ("STEP 01" / "STEP 02" / "STEP 03") — JetBrains Mono 12px, `--accent`, letter-spacing 0.05em.
  - Title: 20px, weight 600, letter-spacing -0.02em, margin `14px 0 8px`.
  - Body: 14.5px, `--fg-2`, line-height 1.6.
  - **Mini terminal visual** (margin-top 20px, padding 12px, `border-radius: 8px`, bg `--bg`, border `1px solid --line-soft`, JetBrains Mono 11.5px, min-height 88px):
    - Step 01: `# from the panel` (color `--fg-3`) / `dock server add root@nyc-1.vps` (keyword `dock` in `--accent`) / `# ✓ agent installed in 4.1s`
    - Step 02: 4 lines — `repo: github.com/you/web`, `build: pnpm build`, `start: pnpm start`, `port: 3000` (values in `--fg`, `pnpm build`/`pnpm start` in `--accent`)
    - Step 03: `# release timeline` / `✓ e0c4d3 — 2m ago (current)` / `✓ a71f22 — 3h ago` / `✗ 9b3fa1 — failed, rolled back` (✓ in `--accent`, ✗ in `--err`, comments in `--fg-3`)
- **Step titles + copy (verbatim):**
  1. **Connect your server** — "Point DeployDock at any VPS over SSH. It installs a lightweight agent — no daemon, no vendor lock-in, no reformatting."
  2. **Register your app** — "Point it at a Git repo, set a build & start command, pick a target server. DeployDock generates the systemd unit for you."
  3. **Deploy, stream, rollback** — "Trigger deploys from the dashboard or on push. Watch logs stream live. If something breaks, one-click rollback to the last good release."

### 5. Feature Grid

- Section head:
  - Tag: `// capabilities`
  - Title: *"Everything you'd script yourself, in one panel."*
  - Sub: *"Built for the shape of infrastructure you already have. No rewriting your app for someone else's runtime."*
- **Grid:** 3 columns (2 cols ≤860px, 1 col ≤560px). Gap 1px, wrapped in a container with `bg: --line-soft`, border `1px solid --line-soft`, `border-radius: 12px`, `overflow: hidden` — creates crisp hairline dividers between tiles.
- **Feature tile:** Bg `--bg`, padding `28px 24px`, min-height 200px, flex column gap 10px. Hover → bg `--bg-2`.
  - **Icon frame:** 34×34, `border-radius: 8px`, bg `color-mix(in oklab, var(--accent) 14%, var(--bg-2))`, border `1px solid color-mix(in oklab, var(--accent) 30%, var(--line))`, icon color `--accent`, 18×18 stroke icon inside. Margin-bottom 8px.
  - Title: 16px, weight 600, letter-spacing -0.015em.
  - Body: 14px, `--fg-2`, line-height 1.55.
- **Tile list (verbatim; icons noted):**
  1. **Any VPS, over SSH** (icon: two stacked server racks with LEDs) — "Bring your own servers from any provider. Ubuntu, Debian, or anywhere systemd runs."
  2. **One-click deploys** (icon: lightning bolt) — "Trigger from the dashboard, on git push, or via API. Cancel mid-deploy without leaving broken state."
  3. **Live log streaming** (icon: 3 horizontal bars + trailing dot) — "Tail deploy output and app logs in real time. Filter by level, search, and pin failed runs."
  4. **Service status & restart** (icon: refresh arc + checkmark) — "See what's running and what's not. Restart a service, run a health check, or SSH from the panel."
  5. **One-click rollback** (icon: counter-clockwise arrow) — "Every release is a checkpoint. Ship broke? Roll back to the last known-good in seconds."
  6. **Multi-app, multi-server** (icon: 2×2 grid) — "Group apps by server or environment. Staging on one box, prod on another — one dashboard."

### 6. CLI Showcase

- **Grid:** 2 columns `1fr 1.15fr`, gap 56px, `align-items: center`. Collapses to 1 column below 980px.
- **Left — Copy + benefit list:**
  - Tag: `// prefers-the-terminal`
  - Title: *"The panel is optional."*
  - Sub: *"Everything DeployDock can do, the CLI can do too. Deploys, logs, rollbacks — scriptable from CI or your laptop."*
  - **3 benefit rows** (`display: flex; gap: 14px`, spacing 18px between):
    - 22×22 circular check badge: bg `color-mix(in oklab, var(--accent) 15%, var(--bg-2))`, border `1px solid color-mix(in oklab, var(--accent) 40%, var(--line))`, accent-color check icon.
    - Heading: 15px, weight 600, letter-spacing -0.01em.
    - Body: 14px, `--fg-2`, line-height 1.55.
    - Copy:
      1. **Scriptable everything** — "Every dashboard action is a CLI command. Wire it into your CI, cron, or a Makefile."
      2. **Piped log streams** — "`dock logs web -f` in one pane, deploys running in another. Works over SSH the way you'd expect."
      3. **Config as code** — "Commit `dock.yaml` to your repo. Reproducible setups across servers, branches, and clones."
- **Right — Terminal card:**
  - `border-radius: 12px`, border `1px solid --line`, bg `oklch(0.13 0.008 250)` (always dark, even in light theme — bg is `oklch(0.16 …)` in light). Shadow `0 30px 60px -30px rgba(0,0,0,0.6)`.
  - Chrome: padding 10px 14px, bg `oklch(0.16 …)`, bottom border `oklch(0.24 …)`. 3 traffic-light dots + centered URL "~/projects/web · zsh" (color `oklch(0.55 …)`).
  - Body: padding 20px 22px, JetBrains Mono 13px, color `oklch(0.85 …)`, line-height 1.75, min-height 320px.
  - **Static content** (styled tokens: `$` prompt in `--accent`, `#` comments in `oklch(0.5 …)`, `✓ 200 OK` / status codes in `--ok`, warnings in `--warn`):
    ```
    $ dock deploy web
    # target: nyc-1.vps · branch: main
    → fetching 4e0c4d3…
    → pnpm install  # 12.4s
    → pnpm build    # 38.1s
    → handing off to systemd
    → health check ✓ 200 OK
    ✓ deployed in 54.2s · e0c4d3   (link, accent + underline)

    $ dock logs web -f
    17:04:12 info  server listening on :3000
    17:04:14 info  connected to postgres
    17:04:22 200   GET /api/users 42ms
    17:04:23 200   GET /pricing 18ms█     (blinking accent cursor)
    ```
  - Cursor animation: `.cursor` — 7×14 accent block, `animation: blink 1s steps(2) infinite` (50% opacity 0).

### 7. Self-Host Callout

- Wrapped in `.wrap`. Card:
  - Padding 48px (32px ≤860px), `border-radius: 16px`, border `1px solid --line`.
  - **Background:** radial gradient from top-right `color-mix(in oklab, var(--accent) 22%, transparent)` → transparent 55%, over `--bg-2`.
  - Grid 2 col `1.4fr 1fr`, gap 40px, collapses to 1 col ≤860px.
- **Left:**
  - Tag: `// self-hosted, MIT` in accent color.
  - `h2` (24-34px clamp): *"Free. Open source. Yours."*
  - Body: 16px `--fg-2`. *"Runs on the same hardware you're already paying for. No seat pricing, no build-minute pricing, no vendor account holding your infrastructure hostage."*
  - CTA row (margin-top 28px): primary "Install DeployDock" + ghost "Read the docs →"
- **Right — Fact list:** Each row `display: flex; justify-content: space-between`, padding-bottom 12px, bottom border `1px dashed --line` (last row: no border). Key column: JetBrains Mono 13px `--fg-3`. Value column: 13px 500 `--fg`. Rows:
  - `license` → **MIT**
  - `runs on` → **Linux + systemd**
  - `install size` → **~ 28 MB**
  - `deps` → **none (single binary)**
  - `telemetry` → **off by default**

### 8. FAQ

- Container max-width 820px, centered.
- Section head: tag `// questions`, title *"Frequently asked."*
- **List:** each item padding `22px 0`, top border `1px solid --line-soft` (last item also bottom border).
- **Question row:** flex row `justify-content: space-between`, gap 20px, 17px 500, letter-spacing -0.015em. Right side: 18×18 plus icon in `--fg-3`; on open, rotates 45° (into ×) and changes to `--accent`. Transition 0.2s.
- **Answer:** collapsed `max-height: 0; overflow: hidden`. Open state: `max-height: 240px; margin-top: 12px`. 15px, `--fg-2`, line-height 1.6. Transition `max-height .3s ease, margin-top .3s ease`.
- **First item open by default.** Only one item can be open at a time is **not** required — current behavior allows independent toggles.
- **Items (verbatim):**
  1. **Is this a PaaS? Do I have to migrate my apps?** — "No. DeployDock is a control panel, not a runtime. If your app runs today on a bare VPS under systemd or Docker, it will keep running exactly the same way — DeployDock just gives you a UI on top."
  2. **What kinds of apps does it support?** — "Anything that runs as a long-lived process on Linux — Node, Python, Go, Rust, PHP, Ruby, static sites, background workers, Docker containers. If you can define a build command and a start command, it works."
  3. **Does it need root on my server?** — "The agent runs as a non-root user by default. It only escalates when a specific action needs it (e.g. writing a systemd unit), and every escalation is auditable."
  4. **How does rollback work?** — "Every release is a snapshot on disk with its own systemd unit. Rolling back swaps the active symlink and restarts — typically under 3 seconds. Your last N releases are kept (configurable)."
  5. **Is it really free?** — "Yes. DeployDock is MIT-licensed and self-hosted. There's no cloud version, no per-seat pricing, and no telemetry. You pay for your VPS; that's it."

### 9. Final CTA

- Padding `96px 0`, top border `1px solid --line-soft`, centered.
- **Background wash:** radial gradient `50% 80% at 50% 0%` — `color-mix(in oklab, var(--accent) 12%, transparent)` → transparent.
- Headline: `clamp(36px, 5vw, 60px)`, letter-spacing -0.035em, weight 600, `text-wrap: balance`. Copy: *"Own your deploys."*
- Sub: 18px, `--fg-2`, max-width 520px, margin `0 auto 32px`. Copy: *"Install DeployDock on any VPS in under 60 seconds. Bring your servers; keep your workflow."*
- CTA row: primary "Install DeployDock" + ghost "View on GitHub", centered, gap 12px.

### 10. Footer

- Top border `1px solid --line-soft`, padding `40px 0 60px`.
- **Top row:** flex justify-between, wrap.
  - **Left brand block** (max-width 320px): brand mark + wordmark + tagline paragraph in 13px `--fg-3` — *"Self-hosted deployment control for developers who already run their own servers."*
  - **Right — 3 link columns** (grid 3 auto, gap 48px; 2×2 grid ≤620px, gap 24px). Column headers: JetBrains Mono 11px uppercase, letter-spacing 0.08em, `--fg-3`, weight 500, margin-bottom 12px. Links: 13.5px `--fg-2`, margin-bottom 8px, hover → `--fg`.
    - **Product:** Features · How it works · CLI · FAQ
    - **Developers:** Documentation · Install guide · CLI reference · Changelog
    - **Community:** GitHub · Discord · Issues · Security
- **Bottom bar** (margin-top 40px, padding-top 20px, top border `--line-soft`): flex justify-between wrap, JetBrains Mono 11px `--fg-3`.
  - Left: `© 2026 DeployDock · MIT License`
  - Right: `v0.9.2 · git@e0c4d3`

---

## Interactions & Behavior

- **Nav links** are anchor links to section IDs (`#features`, `#how`, `#cli`, `#faq`, `#docs`). Smooth scroll optional (browser default is fine).
- **Sticky nav** stays pinned; backdrop blur activates over content.
- **Install command box** — click copies `curl -sSL deploydock.sh/install | sh` to clipboard. Show a brief "Copied ✓" state (300ms) — the prototype uses raw `navigator.clipboard.writeText`; add a toast/inline confirmation in production.
- **Hero log stream** — see section 2 for exact seed/loop/interval/cap.
- **Deploying-status pulse** on `.app.active .status.dep .sdot` — 1.1s ease-in-out infinite, expanding box-shadow from `0 0 0 0` to `0 0 0 5px` transparent accent.
- **Live tag pulse** on `.logs-tag .live` — same `@keyframes pulse`, 1.4s interval, red (`--err`).
- **Terminal cursor** — 1s steps(2) infinite blink.
- **FAQ accordion** — click a `.faq-q` button to toggle `data-open` on the `.faq-item`. Independent toggles (multiple can be open). Answer height transitions 300ms ease; icon rotates 45° (plus → ×) and swaps to accent.
- **Feature tile hover** — bg lifts to `--bg-2`, 150ms transition.
- **Button hover** — primary: `filter: brightness(1.05)`. Ghost: bg `--bg-2`, border `--fg-3`. All buttons: 80ms `transform: translateY(1px)` on `:active`.
- **All transitions** use `ease` or `ease-in-out`; keep `prefers-reduced-motion` in mind — disable log stream + pulse animations when reduced-motion is set.

## Responsive Behavior

Breakpoints used (max-width):
- **980px** — hero grid → 1 col; CLI grid → 1 col.
- **860px** — how-it-works steps → 1 col; features → 2 cols; callout → 1 col; footer cols → 2×2.
- **780px** — nav links hidden; logo cloud → 3 cols; footer minor tweaks.
- **700px** — `.wrap` horizontal padding drops to 20px.
- **620px** — hero product body → 1 col.
- **560px** — features grid → 1 col.

Container `max-width: 1240px`. Horizontal padding 32px desktop / 20px on smallest.

## State Management

Minimal — everything is presentational except:
- **Hero log stream:** `useEffect` (or a component-mount hook) that seeds 8 lines, then pushes one line every 1400ms with a bounded array (cap 14). Clear the interval on unmount.
- **FAQ open state:** array of booleans or a single "which open" index. In the prototype each item toggles independently.
- **Install-command copy state:** transient boolean for "just copied" toast.

No data fetching. No routing state.

## Design Tokens

### Colors (dark theme — default)

| Token | Value | Purpose |
|---|---|---|
| `--bg` | `oklch(0.16 0.008 250)` | Page background |
| `--bg-2` | `oklch(0.19 0.008 250)` | Card / raised surface |
| `--bg-3` | `oklch(0.22 0.008 250)` | Nested surface / chrome |
| `--line` | `oklch(0.28 0.008 250)` | Strong hairline |
| `--line-soft` | `oklch(0.24 0.008 250)` | Subtle hairline |
| `--fg` | `oklch(0.96 0.005 250)` | Primary text |
| `--fg-2` | `oklch(0.78 0.008 250)` | Secondary text |
| `--fg-3` | `oklch(0.58 0.008 250)` | Muted / metadata |
| `--accent` | `oklch(0.74 0.14 220)` (~`#3ea0ff`) | Brand accent |
| `--accent-ink` | `oklch(0.18 0.03 240)` (dark) / `white` (light) | Text on accent |
| `--ok` | `oklch(0.76 0.14 155)` | Success state |
| `--warn` | `oklch(0.80 0.14 75)` | Warning state |
| `--err` | `oklch(0.70 0.19 25)` | Error / live indicator |

### Colors (light theme override)

| Token | Value |
|---|---|
| `--bg` | `oklch(0.985 0.003 90)` |
| `--bg-2` | `oklch(0.965 0.004 90)` |
| `--bg-3` | `oklch(0.94 0.005 90)` |
| `--line` | `oklch(0.88 0.006 90)` |
| `--line-soft` | `oklch(0.92 0.005 90)` |
| `--fg` | `oklch(0.20 0.01 250)` |
| `--fg-2` | `oklch(0.38 0.008 250)` |
| `--fg-3` | `oklch(0.55 0.008 250)` |
| `--ok` | `oklch(0.55 0.13 155)` |
| `--warn` | `oklch(0.62 0.14 75)` |
| `--err` | `oklch(0.55 0.19 25)` |
| `--accent-ink` | `white` |

**Accent variations** offered in the design (tweaks) — all mapped by hex:
- Electric blue `#3ea0ff` (default)
- Teal `#22d3a3`
- Amber `#f5a524`
- Violet `#c084fc`

When implementing the accent picker (if kept in production), pick a foreground for the accent based on luminance: if the accent's relative luminance > 0.55, use dark ink (`#0b1220`), else white. Snippet in the prototype's `hexLuminance` fn.

### Typography

Load from Google Fonts:
- **Inter Tight** — 400, 500, 600, 700 (UI + display).
- **JetBrains Mono** — 400, 500, 600 (code, labels, meta).
- **Instrument Serif** — 400 italic + regular (reserved for a future editorial/light variant; not currently used in the dark hero but loaded).

Body defaults: Inter Tight, `line-height: 1.5`, `-webkit-font-smoothing: antialiased`, `font-feature-settings: "ss01","cv11"`.

**Scale (roughly):**

| Role | Size | Weight | Line height | Tracking |
|---|---|---|---|---|
| H1 hero | `clamp(40px, 5.6vw, 68px)` | 600 | 1.02 | -0.035em |
| H1 final CTA | `clamp(36px, 5vw, 60px)` | 600 | 1.05 | -0.035em |
| H2 section | `clamp(28px, 3.4vw, 42px)` | 600 | 1.1 | -0.03em |
| H2 callout | `clamp(24px, 3vw, 34px)` | 600 | 1.15 | -0.03em |
| H3 step | 20px | 600 | 1.4 | -0.02em |
| H3 feature | 16px | 600 | 1.4 | -0.015em |
| FAQ Q | 17px | 500 | 1.4 | -0.015em |
| Body (subhead) | 18px | 400 | 1.5 | 0 |
| Body (default) | 14–15px | 400 | 1.55–1.6 | 0 |
| Meta / caption | 11–13px mono | 400–500 | 1.5 | 0–0.08em |

### Spacing scale

Not a strict scale — key values used:
- Section vertical padding: **88px** (main), **96px** (final CTA), **40px** (footer top), **44px** (hero bottom fine-tune).
- Grid gaps: **56px** (hero + CLI split), **48px** (footer cols), **24px** (step cards), **20px** (logo cloud), **10-14px** (inline).
- Card padding: **48px** (callout), **28px 24px** (feature tile), **24px** (step), **20px 22px** (terminal body), **16px** (apps pane), **14px 16px** (logs pane), **10-14px** (inline pill / install line).
- Container: `max-width: 1240px`, padding `0 32px` (`0 20px` on ≤700px).

### Border radius

- Large cards: **14px** (product mock), **16px** (callout).
- Standard cards / tiles: **12px** (steps, terminal, feature grid outer).
- Rows / buttons / inputs: **8px**.
- Nested squares: **5-7px** (brand mark 7, app icon 5).
- Full pill: **999px** (status pills, eyebrow).

### Shadows

- Product mock: `0 40px 80px -40px rgba(0,0,0,0.6)` + `0 0 0 1px color-mix(in oklab, var(--accent) 8%, transparent)`.
- Terminal card: `0 30px 60px -30px rgba(0,0,0,0.6)`.
- Primary button glow: `0 8px 24px -8px color-mix(in oklab, var(--accent) 60%, transparent)` + inner `0 1px 0 color-mix(in oklab, white 20%, transparent)`.
- Status dot glow: `0 0 6px <token>` (green/amber/red).

### Motion

- Standard easing: `ease` / `ease-in-out`.
- Standard durations: **80ms** (button press), **150ms** (hover), **200ms** (FAQ icon), **300ms** (FAQ collapse).
- Pulse (`@keyframes pulse`) — 1.1s (deploy dot), 1.4s (live tag).
- Blink cursor — 1s steps(2).

## Assets

- **No image assets.** All iconography is inline SVG (Lucide-style strokes, 2px, round caps/joins). Where the design uses provider "logos" (Hetzner, DigitalOcean, etc.), those are **type-only** wordmarks — no third-party logo files are bundled.
- **Fonts** come from Google Fonts via CDN — see `<link>` tags in the HTML `<head>`. Self-host for production if that matches the codebase's policy.
- **Brand mark** is drawn in pure CSS (two pseudo-elements on `.brand-mark`). If a real SVG logo is delivered later, replace the CSS mark with an inline `<svg>` in the nav + footer.
- **Favicon / OG image** — not yet designed. Ask before shipping to production.

## Files

Bundled in this handoff:

- `Landing Page.html` — the full prototype: HTML, CSS (inline `<style>`), and the log-stream + FAQ + tweaks JS. This is the single source of truth for the visual design.
- `tweaks_panel.jsx` — design-tool tweaks component (theme / accent / hero-copy live editor). **Do not ship** — this is for use inside the design tool only.

## Implementation Notes / Recommendations

- **Recommended stack:** Next.js 14 (App Router) + Tailwind CSS + shadcn-style primitives (Button, etc.). The design tokens above map directly to `tailwind.config.ts` via `theme.extend.colors` + CSS variables. Keep the tokens as CSS custom properties so a `data-theme="light"` attribute swap continues to work.
- **Log stream:** implement as a small client component (`"use client"` in Next). Use a `useEffect` with `setInterval(1400)`, keep an array in state, cap length at 14 with a ring-buffer pattern. Respect `prefers-reduced-motion: reduce` by rendering a static seed and skipping the interval.
- **Semantics:** the hero product mock is decorative — leave `aria-hidden="true"` on it (as in the prototype) so screen readers skip the fake data. Real dashboard screenshots (when available) should replace it and get proper alt text.
- **Icons:** Lucide React (`lucide-react`) is a 1:1 substitute for the inline SVGs. Preferred over hand-rolled SVG for maintenance.
- **Accessibility passes to do before ship:**
  - Focus rings on all interactive elements (buttons, nav links, FAQ triggers, install-command box).
  - FAQ triggers should be `<button aria-expanded="…" aria-controls="…">` and the answer panel should have a matching `id` + `role="region"`.
  - Color contrast: verify `--fg-2` on `--bg` meets AA at 14px+ (should — it's a high-lightness gray). `--fg-3` is intentionally decorative — do not use it for body text.
- **SEO:** add `<meta name="description">`, OG tags, and a `<link rel="canonical">` — none of that is in the prototype.
- **Analytics / real CTAs:** placeholder anchors (`#install`, `#github`, `#docs`) need real destinations wired up.

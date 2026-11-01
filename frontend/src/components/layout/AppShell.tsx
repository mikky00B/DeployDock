import { useState } from "react";

import { navigateTo, type AppRoute } from "../../routes";
import { useAuth } from "../../hooks/useAuth";

type AppShellProps = {
  activeRoute: AppRoute;
  children: React.ReactNode;
};

const navItems: Array<{ route: AppRoute; label: string }> = [
  { route: "/dashboard", label: "Dashboard" },
  { route: "/servers", label: "Servers" },
  { route: "/apps", label: "Apps" },
  { route: "/deployments", label: "Deployments" },
  { route: "/docs", label: "Guide" },
];

export function AppShell({ activeRoute, children }: AppShellProps) {
  const { user, signOut } = useAuth();
  const [isSigningOut, setIsSigningOut] = useState(false);

  async function handleSignOut() {
    setIsSigningOut(true);
    try {
      await signOut();
    } finally {
      setIsSigningOut(false);
    }
  }

  return (
    <main className="app-shell">
      <aside className="sidebar">
        <a className="brand-button" href="/dashboard" onClick={(event) => { event.preventDefault(); navigateTo("/dashboard"); }}>
          <span>DeployDock</span>
          <small>Deployment control panel</small>
        </a>
        <nav aria-label="Primary navigation">
          <p className="nav-group-label">Workspace</p>
          {navItems.map((item) => (
            <a
              aria-current={activeRoute === item.route ? "page" : undefined}
              className={activeRoute === item.route ? "nav-link active" : "nav-link"}
              href={item.route}
              key={item.route}
              onClick={(event) => {
                event.preventDefault();
                navigateTo(item.route);
              }}
            >
              {item.label}
            </a>
          ))}
        </nav>
      </aside>

      <section className="content">
        <header className="topbar">
          <div>
            <p className="eyebrow">DeployDock</p>
            <h1>{routeTitle(activeRoute)}</h1>
          </div>
          <p className="topbar-copy">Self-hosted deployment control for existing VPS apps.</p>
          <div className="account-menu">
            <span>{user?.email}</span>
            <button className="secondary-button" type="button" disabled={isSigningOut} onClick={() => void handleSignOut()}>
              {isSigningOut ? "Signing out" : "Sign out"}
            </button>
          </div>
        </header>
        {children}
      </section>
    </main>
  );
}

function routeTitle(route: AppRoute) {
  if (route === "/servers") return "Servers";
  if (route === "/apps") return "Apps";
  if (route === "/deployments") return "Deployments";
  if (route === "/docs") return "Guide";
  return "Dashboard";
}

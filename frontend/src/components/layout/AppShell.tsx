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
];

export function AppShell({ activeRoute, children }: AppShellProps) {
  const { user, signOut } = useAuth();

  return (
    <main className="app-shell">
      <aside className="sidebar">
        <button className="brand-button" type="button" onClick={() => navigateTo("/dashboard")}>
          <span>DeployDock</span>
          <small>Deployment control panel</small>
        </button>
        <nav aria-label="Primary navigation">
          <p className="nav-group-label">Workspace</p>
          {navItems.map((item) => (
            <button
              className={activeRoute === item.route ? "nav-link active" : "nav-link"}
              key={item.route}
              type="button"
              onClick={() => navigateTo(item.route)}
            >
              {item.label}
            </button>
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
            <button className="secondary-button" type="button" onClick={() => void signOut()}>
              Sign out
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
  return "Dashboard";
}

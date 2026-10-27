import { useEffect, useState } from "react";

import { AppShell } from "./components/layout/AppShell";
import { stashPostAuthRedirect } from "./components/common";
import { AuthProvider, useAuth } from "./hooks/useAuth";
import { AppDetailPage, AppsPage } from "./pages/AppsPage";
import { DashboardPage } from "./pages/DashboardPage";
import { DeploymentDetailPage, DeploymentsPage } from "./pages/DeploymentsPage";
import { DocsPage } from "./pages/DocsPage";
import { LandingPage } from "./pages/LandingPage";
import { LoginPage } from "./pages/LoginPage";
import { RegisterPage } from "./pages/RegisterPage";
import { ServerDetailPage, ServersPage } from "./pages/ServersPage";
import { getCurrentRoute, isKnownPathname, navigateTo, type AppRoute, type RouteState } from "./routes";

const PAGE_TITLES: Record<AppRoute, string> = {
  "/": "DeployDock — Deployment control panel for VPS",
  "/login": "Sign in — DeployDock",
  "/register": "Create account — DeployDock",
  "/dashboard": "Dashboard — DeployDock",
  "/servers": "Servers — DeployDock",
  "/apps": "Apps — DeployDock",
  "/deployments": "Deployments — DeployDock",
  "/docs": "Guide — DeployDock",
};

function App() {
  return (
    <AuthProvider>
      <RouterView />
    </AuthProvider>
  );
}

function RouterView() {
  const [route, setRoute] = useState<RouteState>(() => getCurrentRoute());
  const { user, isLoading } = useAuth();

  useEffect(() => {
    function handleNavigation() {
      setRoute(getCurrentRoute());
    }

    window.addEventListener("popstate", handleNavigation);
    return () => window.removeEventListener("popstate", handleNavigation);
  }, []);

  useEffect(() => {
    if (isLoading) return;

    // The landing page and the guide are public — no auth redirect.
    if (route.route === "/" || route.route === "/docs") return;

    if (!user && route.route !== "/login" && route.route !== "/register") {
      stashPostAuthRedirect();
      navigateTo("/login");
      return;
    }

    if (user && (route.route === "/login" || route.route === "/register")) {
      navigateTo("/dashboard");
    }
  }, [isLoading, route, user]);

  useEffect(() => {
    // Detail routes keep their section title; unknown paths render the
    // dashboard, so normalize the URL to match instead of leaving /foo up.
    if (!isKnownPathname(window.location.pathname)) {
      window.history.replaceState({}, "", "/dashboard");
    }
    document.title = PAGE_TITLES[route.route] ?? "DeployDock";
    window.scrollTo(0, 0);
  }, [route]);

  if (isLoading) {
    return (
      <main className="loading-page">
        <div className="loading-mark">DeployDock</div>
      </main>
    );
  }

  if (route.route === "/") {
    return <LandingPage />;
  }

  if (route.route === "/docs" && !user) {
    return (
      <main style={{ maxWidth: 1080, margin: "0 auto", padding: "32px 24px 64px" }}>
        <h1 className="visually-hidden">DeployDock guide</h1>
        <header style={{ display: "flex", justifyContent: "space-between", alignItems: "center", marginBottom: 28 }}>
          <a
            className="brand-button"
            href="/"
            onClick={(event) => {
              event.preventDefault();
              navigateTo("/");
            }}
            style={{ margin: 0, width: "auto", textAlign: "left" }}
          >
            <span>DeployDock</span>
            <small>Deployment control panel</small>
          </a>
          <a
            className="primary-inline-button"
            href="/login"
            onClick={(event) => {
              event.preventDefault();
              navigateTo("/login");
            }}
          >
            Sign in
          </a>
        </header>
        <DocsPage />
      </main>
    );
  }

  if (!user) {
    return route.route === "/register" ? <RegisterPage /> : <LoginPage />;
  }

  return (
    <AppShell activeRoute={route.route}>
      {route.route === "/dashboard" ? <DashboardPage /> : null}
      {route.route === "/servers" && !route.serverId ? <ServersPage /> : null}
      {route.route === "/servers" && route.serverId ? <ServerDetailPage serverId={route.serverId} /> : null}
      {route.route === "/apps" && !route.appId ? <AppsPage /> : null}
      {route.route === "/apps" && route.appId ? <AppDetailPage appId={route.appId} /> : null}
      {route.route === "/deployments" && !route.deploymentId ? <DeploymentsPage /> : null}
      {route.route === "/deployments" && route.deploymentId ? (
        <DeploymentDetailPage deploymentId={route.deploymentId} />
      ) : null}
      {route.route === "/docs" ? <DocsPage /> : null}
    </AppShell>
  );
}

export default App;

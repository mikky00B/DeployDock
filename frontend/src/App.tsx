import { useEffect, useState } from "react";

import { AppShell } from "./components/layout/AppShell";
import { AuthProvider, useAuth } from "./hooks/useAuth";
import { AppDetailPage, AppsPage } from "./pages/AppsPage";
import { DashboardPage } from "./pages/DashboardPage";
import { DeploymentDetailPage, DeploymentsPage } from "./pages/DeploymentsPage";
import { LoginPage } from "./pages/LoginPage";
import { RegisterPage } from "./pages/RegisterPage";
import { ServerDetailPage, ServersPage } from "./pages/ServersPage";
import { getCurrentRoute, navigateTo, type RouteState } from "./routes";

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

    if (!user && route.route !== "/login" && route.route !== "/register") {
      navigateTo("/login");
      return;
    }

    if (user && (route.route === "/login" || route.route === "/register")) {
      navigateTo("/dashboard");
    }
  }, [isLoading, route, user]);

  if (isLoading) {
    return (
      <main className="loading-page">
        <div className="loading-mark">DeployDock</div>
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
    </AppShell>
  );
}

export default App;

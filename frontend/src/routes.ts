export type AppRoute =
  | "/"
  | "/login"
  | "/register"
  | "/dashboard"
  | "/servers"
  | "/apps"
  | "/deployments";

export type RouteState = {
  route: AppRoute;
  serverId?: string;
  appId?: string;
  deploymentId?: string;
};

const routes: AppRoute[] = ["/", "/login", "/register", "/dashboard", "/servers", "/apps", "/deployments"];

export function getCurrentRoute(): RouteState {
  const pathname = window.location.pathname;
  const serverMatch = pathname.match(/^\/servers\/([^/]+)$/);
  if (serverMatch) {
    return { route: "/servers", serverId: serverMatch[1] };
  }

  const appMatch = pathname.match(/^\/apps\/([^/]+)$/);
  if (appMatch) {
    return { route: "/apps", appId: appMatch[1] };
  }

  const deploymentMatch = pathname.match(/^\/deployments\/([^/]+)$/);
  if (deploymentMatch) {
    return { route: "/deployments", deploymentId: deploymentMatch[1] };
  }

  if (routes.includes(pathname as AppRoute)) {
    return { route: pathname as AppRoute };
  }
  return { route: "/dashboard" };
}

export function navigateTo(path: AppRoute | `/servers/${string}` | `/apps/${string}` | `/deployments/${string}`) {
  window.history.pushState({}, "", path);
  window.dispatchEvent(new PopStateEvent("popstate"));
}

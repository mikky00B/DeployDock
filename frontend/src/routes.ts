export type AppRoute =
  | "/"
  | "/login"
  | "/register"
  | "/dashboard"
  | "/servers"
  | "/apps"
  | "/deployments"
  | "/docs";

export type RouteState = {
  route: AppRoute;
  serverId?: string;
  appId?: string;
  deploymentId?: string;
};

const routes: AppRoute[] = ["/", "/login", "/register", "/dashboard", "/servers", "/apps", "/deployments", "/docs"];

export function isKnownPathname(pathname: string): boolean {
  return (
    routes.includes(pathname as AppRoute) ||
    /^\/servers\/[^/]+$/.test(pathname) ||
    /^\/apps\/[^/]+$/.test(pathname) ||
    /^\/deployments\/[^/]+$/.test(pathname)
  );
}

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

export type NavigateTarget =
  | AppRoute
  | `/servers/${string}`
  | `/apps/${string}`
  | `/deployments/${string}`;

export function navigateTo(path: NavigateTarget) {
  window.history.pushState({}, "", path);
  window.dispatchEvent(new PopStateEvent("popstate"));
}

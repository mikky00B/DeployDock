import type { NavigateTarget } from "../routes";

const POST_AUTH_REDIRECT_KEY = "deploydock.post_auth_redirect";

/** Remember where an unauthenticated visitor was heading so login can return there. */
export function stashPostAuthRedirect() {
  const path = window.location.pathname;
  if (path !== "/login" && path !== "/register") {
    sessionStorage.setItem(POST_AUTH_REDIRECT_KEY, path);
  }
}

/** Returns the stashed destination, or /dashboard when there is none. */
export function popPostAuthRedirect(): NavigateTarget {
  const saved = sessionStorage.getItem(POST_AUTH_REDIRECT_KEY);
  sessionStorage.removeItem(POST_AUTH_REDIRECT_KEY);
  // Only authenticated routes ever get stashed (login/register are excluded),
  // so the saved path is always a valid navigation target.
  return (saved as NavigateTarget | null) ?? "/dashboard";
}

type StatusBadgeProps = {
  label: string;
  tone?: "neutral" | "success" | "danger" | "warning";
};

export function StatusBadge({ label, tone = "neutral" }: StatusBadgeProps) {
  return <span className={`status-badge ${tone}`}>{humanizeToken(label)}</span>;
}

export function EmptyState({ title, body }: { title: string; body: string }) {
  return (
    <div className="empty-panel">
      <h2>{title}</h2>
      <p>{body}</p>
    </div>
  );
}

export function CodeValue({ value }: { value: string | null | undefined }) {
  if (!value) return <span className="muted">Not available</span>;
  return (
    <code className="inline-code" title={value}>
      {shortSha(value)}
    </code>
  );
}

export function shortSha(value: string | null | undefined) {
  if (!value) return "Unknown";
  return value.length > 12 ? value.slice(0, 12) : value;
}

export function formatDateTime(value: string | null | undefined) {
  return value ? new Date(value).toLocaleString() : "Not available";
}

export function formatDuration(seconds: number | null | undefined) {
  if (seconds === null || seconds === undefined) return "Not finished";
  if (seconds < 60) return `${seconds}s`;
  const minutes = Math.floor(seconds / 60);
  const remainingSeconds = seconds % 60;
  return `${minutes}m ${remainingSeconds}s`;
}

export function humanizeToken(value: string) {
  return value
    .split(/[._-]/)
    .filter(Boolean)
    .map((part) => part.charAt(0).toUpperCase() + part.slice(1))
    .join(" ");
}

/**
 * Self-hosted installs often run over plain HTTP, where the async Clipboard API
 * is unavailable, so fall back to a hidden textarea before reporting failure.
 */
export async function copyToClipboard(text: string): Promise<boolean> {
  try {
    if (navigator.clipboard?.writeText) {
      await navigator.clipboard.writeText(text);
      return true;
    }
  } catch {
    // Insecure context or permission denied — try the legacy path below.
  }
  try {
    const textarea = document.createElement("textarea");
    textarea.value = text;
    textarea.setAttribute("readonly", "");
    textarea.style.position = "fixed";
    textarea.style.opacity = "0";
    document.body.appendChild(textarea);
    textarea.select();
    const copied = document.execCommand("copy");
    textarea.remove();
    return copied;
  } catch {
    return false;
  }
}

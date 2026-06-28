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

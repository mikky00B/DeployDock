import { useEffect, useState, type Dispatch, type SetStateAction } from "react";

import { apiClient } from "../api/client";
import {
  ACTIVE_DEPLOYMENT_STATUSES,
  type DeploymentLog,
  type DeploymentStatus,
} from "../types/deployment";

export type StreamState = {
  logs: DeploymentLog[];
  status: DeploymentStatus | null;
  error: string | null;
  /** True between a dropped stream and its next connection attempt. */
  reconnecting: boolean;
};

/** Consecutive stream drops tolerated when not a single frame arrives. */
const MAX_EMPTY_DROPS = 8;
const MAX_BACKOFF_MS = 15_000;

export function useDeploymentStream(token: string | null, deploymentId: string | null, enabled: boolean) {
  const [state, setState] = useState<StreamState>({
    logs: [],
    status: null,
    error: null,
    reconnecting: false,
  });

  useEffect(() => {
    if (!token || !deploymentId || !enabled) return;

    const controller = new AbortController();
    setState({ logs: [], status: null, error: null, reconnecting: false });

    let latestStatus: DeploymentStatus | null = null;
    let emptyDrops = 0;
    let reconnectTimer: number | undefined;
    let disposed = false;

    // handleSseEvent returns a status frame's value synchronously: React may
    // batch the setState updater past the end of the stream, and the reconnect
    // decision must not depend on render timing.
    function scheduleReconnect(): void {
      if (disposed || controller.signal.aborted) return;
      if (latestStatus !== null && !ACTIVE_DEPLOYMENT_STATUSES.includes(latestStatus)) {
        // Terminal status already seen: nothing more will arrive.
        setState((current) => ({ ...current, reconnecting: false }));
        return;
      }
      const backoffMs = Math.min(1000 * 2 ** emptyDrops, MAX_BACKOFF_MS);
      setState((current) => ({ ...current, reconnecting: true, error: null }));
      reconnectTimer = window.setTimeout(() => {
        void connect();
      }, backoffMs);
    }

    async function connect(): Promise<void> {
      let sawFrame = false;
      try {
        const response = await fetch(`${apiClient.baseUrl}/api/v1/deployments/${deploymentId}/stream`, {
          headers: { Authorization: `Bearer ${token}` },
          signal: controller.signal,
        });

        if (!response.ok || !response.body) {
          throw new Error(`Could not open deployment stream (HTTP ${response.status})`);
        }
        setState((current) => ({ ...current, reconnecting: false }));

        const reader = response.body.getReader();
        const decoder = new TextDecoder();
        let buffer = "";

        while (true) {
          const { value, done } = await reader.read();
          if (done) break;
          buffer += decoder.decode(value, { stream: true });
          const events = buffer.split("\n\n");
          buffer = events.pop() ?? "";
          for (const rawEvent of events) {
            sawFrame = true;
            const frameStatus = handleSseEvent(rawEvent, setState);
            if (frameStatus !== null) {
              latestStatus = frameStatus;
            }
          }
        }
      } catch (streamError) {
        if (controller.signal.aborted) return;
        const message = streamError instanceof Error ? streamError.message : "Deployment stream failed";
        if (!sawFrame) {
          emptyDrops += 1;
          if (emptyDrops >= MAX_EMPTY_DROPS) {
            setState((current) => ({
              ...current,
              reconnecting: false,
              error: `${message} — gave up after ${emptyDrops} connection attempts.`,
            }));
            return;
          }
        }
      }
      if (sawFrame) {
        // The endpoint works; a stream that made progress should reconnect fast.
        emptyDrops = 0;
      }
      scheduleReconnect();
    }

    void connect();

    return () => {
      disposed = true;
      controller.abort();
      if (reconnectTimer !== undefined) {
        window.clearTimeout(reconnectTimer);
      }
    };
  }, [deploymentId, enabled, token]);

  return state;
}

/** Applies one SSE frame. Returns the frame's deployment status, if any. */
export function handleSseEvent(
  rawEvent: string,
  setState: Dispatch<SetStateAction<StreamState>>,
): DeploymentStatus | null {
  const lines = rawEvent.split("\n");
  const eventLine = lines.find((line) => line.startsWith("event: "));
  const dataLines = lines.filter((line) => line.startsWith("data: "));
  if (!eventLine || dataLines.length === 0) return null;

  const eventName = eventLine.replace("event: ", "");
  const rawData = dataLines.map((line) => line.replace("data: ", "")).join("\n");

  let data: Record<string, unknown>;
  try {
    data = JSON.parse(rawData) as Record<string, unknown>;
  } catch {
    // A malformed frame must not tear down a live deployment log view.
    return null;
  }

  if (eventName === "log") {
    setState((current) => ({
      ...current,
      logs: appendLog(current.logs, {
        stream: data.stream as DeploymentLog["stream"],
        line: String(data.line ?? ""),
        sequence: Number(data.sequence ?? current.logs.length + 1),
      }),
    }));
  }

  if (eventName === "status" || eventName === "heartbeat") {
    const status = data.status as DeploymentStatus;
    setState((current) => ({ ...current, status }));
    return status;
  }
  return null;
}

function appendLog(logs: DeploymentLog[], nextLog: DeploymentLog) {
  if (logs.some((log) => log.sequence === nextLog.sequence)) {
    return logs;
  }
  return [...logs, nextLog];
}

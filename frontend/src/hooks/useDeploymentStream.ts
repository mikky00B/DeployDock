import { useEffect, useState, type Dispatch, type SetStateAction } from "react";

import { apiClient } from "../api/client";
import type { DeploymentLog, DeploymentStatus } from "../types/deployment";

type StreamState = {
  logs: DeploymentLog[];
  status: DeploymentStatus | null;
  error: string | null;
};

export function useDeploymentStream(token: string | null, deploymentId: string | null, enabled: boolean) {
  const [state, setState] = useState<StreamState>({ logs: [], status: null, error: null });

  useEffect(() => {
    if (!token || !deploymentId || !enabled) return;

    const controller = new AbortController();
    setState({ logs: [], status: null, error: null });

    async function connect() {
      try {
        const response = await fetch(`${apiClient.baseUrl}/api/v1/deployments/${deploymentId}/stream`, {
          headers: { Authorization: `Bearer ${token}` },
          signal: controller.signal,
        });

        if (!response.ok || !response.body) {
          throw new Error("Could not open deployment stream");
        }

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
            handleSseEvent(rawEvent, setState);
          }
        }
      } catch (streamError) {
        if (!controller.signal.aborted) {
          setState((current) => ({
            ...current,
            error: streamError instanceof Error ? streamError.message : "Deployment stream failed",
          }));
        }
      }
    }

    void connect();

    return () => controller.abort();
  }, [deploymentId, enabled, token]);

  return state;
}

function handleSseEvent(rawEvent: string, setState: Dispatch<SetStateAction<StreamState>>) {
  const lines = rawEvent.split("\n");
  const eventLine = lines.find((line) => line.startsWith("event: "));
  const dataLines = lines.filter((line) => line.startsWith("data: "));
  if (!eventLine || dataLines.length === 0) return;

  const eventName = eventLine.replace("event: ", "");
  const rawData = dataLines.map((line) => line.replace("data: ", "")).join("\n");
  const data = JSON.parse(rawData) as Record<string, unknown>;

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
    setState((current) => ({ ...current, status: data.status as DeploymentStatus }));
  }
}

function appendLog(logs: DeploymentLog[], nextLog: DeploymentLog) {
  if (logs.some((log) => log.sequence === nextLog.sequence)) {
    return logs;
  }
  return [...logs, nextLog];
}

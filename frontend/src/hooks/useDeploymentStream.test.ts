import { act, renderHook, waitFor } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";

import { handleSseEvent, useDeploymentStream, type StreamState } from "./useDeploymentStream";

const initialState: StreamState = { logs: [], status: null, error: null, reconnecting: false };

/** Applies a sequence of raw SSE frames and returns the resulting state. */
function reduce(frames: string[], from: StreamState = initialState): StreamState {
  let state = from;
  const setState = (update: StreamState | ((current: StreamState) => StreamState)) => {
    state = typeof update === "function" ? update(state) : update;
  };
  for (const frame of frames) {
    handleSseEvent(frame, setState);
  }
  return state;
}

function logFrame(line: string, sequence: number) {
  return `event: log\ndata: ${JSON.stringify({ stream: "stdout", line, sequence })}`;
}

describe("handleSseEvent", () => {
  it("appends log lines in order", () => {
    const state = reduce([logFrame("pulling", 1), logFrame("restarted", 2)]);

    expect(state.logs.map((log) => log.line)).toEqual(["pulling", "restarted"]);
  });

  it("deduplicates a replayed sequence number", () => {
    const state = reduce([logFrame("pulling", 1), logFrame("pulling", 1)]);

    expect(state.logs).toHaveLength(1);
  });

  it("records a terminal status", () => {
    const state = reduce([`event: status\ndata: {"status":"success"}`]);

    expect(state.status).toBe("success");
  });

  it("treats a heartbeat as a status update without adding a log line", () => {
    const state = reduce([`event: heartbeat\ndata: {"status":"running"}`]);

    expect(state.status).toBe("running");
    expect(state.logs).toHaveLength(0);
  });

  it("ignores a malformed frame instead of throwing", () => {
    const state = reduce([`event: log\ndata: {not-json`, logFrame("still here", 1)]);

    expect(state.logs.map((log) => log.line)).toEqual(["still here"]);
  });

  it("ignores a frame with no data lines", () => {
    expect(() => reduce(["event: log"])).not.toThrow();
    expect(reduce(["event: log"]).logs).toHaveLength(0);
  });

  it("ignores a frame with no event name", () => {
    expect(reduce([`data: {"status":"success"}`]).status).toBeNull();
  });
});

describe("useDeploymentStream reconnection", () => {
  afterEach(() => {
    vi.unstubAllGlobals();
    vi.useRealTimers();
  });

  /** A 200 response whose body streams the given frames and then closes. */
  function sseResponse(frames: string[]): Response {
    const encoder = new TextEncoder();
    const chunks = frames.map((frame) => encoder.encode(`${frame}\n\n`));
    let index = 0;
    const body = {
      getReader: () => ({
        read: async () =>
          index < chunks.length
            ? { value: chunks[index++], done: false as const }
            : { value: undefined, done: true as const },
      }),
    };
    return { ok: true, status: 200, body } as unknown as Response;
  }

  it("reconnects after a mid-deploy drop and stops once terminal", async () => {
    const fetchMock = vi.fn();
    // First connection drops after one line (proxy timeout mid-deploy)…
    fetchMock.mockResolvedValueOnce(sseResponse([logFrame("first-chunk", 1)]));
    // …the reconnect reports the next line plus success and closes.
    fetchMock.mockResolvedValueOnce(
      sseResponse([logFrame("second-chunk", 2), `event: status\ndata: {"status":"success"}`]),
    );
    vi.stubGlobal("fetch", fetchMock);

    const { result } = renderHook(() => useDeploymentStream("token", "dep-1", true));

    await waitFor(
      () => {
        expect(result.current.logs.map((log) => log.line)).toEqual(["first-chunk", "second-chunk"]);
        expect(result.current.status).toBe("success");
        expect(result.current.reconnecting).toBe(false);
      },
      { timeout: 5000 },
    );
    // Terminal status: no further connection attempts.
    expect(fetchMock).toHaveBeenCalledTimes(2);
  });

  it("gives up after repeated connections that never deliver a frame", async () => {
    vi.useFakeTimers();
    const fetchMock = vi.fn().mockRejectedValue(new TypeError("Failed to fetch"));
    vi.stubGlobal("fetch", fetchMock);

    const { result } = renderHook(() => useDeploymentStream("token", "dep-1", true));

    // Fast-forward through the whole exponential backoff schedule.
    await act(async () => {
      await vi.advanceTimersByTimeAsync(120_000);
    });

    expect(result.current.error).toContain("gave up");
    expect(fetchMock).toHaveBeenCalledTimes(8);
    expect(result.current.reconnecting).toBe(false);
  });
});

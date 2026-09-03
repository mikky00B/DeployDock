import { describe, expect, it } from "vitest";

import { handleSseEvent, type StreamState } from "./useDeploymentStream";

const initialState: StreamState = { logs: [], status: null, error: null };

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

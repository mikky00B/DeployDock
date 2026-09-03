import { afterEach, describe, expect, it, vi } from "vitest";

import { apiClient } from "./client";

function jsonResponse(body: unknown, status = 200) {
  return new Response(JSON.stringify(body), {
    status,
    headers: { "Content-Type": "application/json" },
  });
}

afterEach(() => {
  vi.restoreAllMocks();
});

describe("apiClient.request", () => {
  it("sends the bearer token and parses the body", async () => {
    const fetchMock = vi.fn().mockResolvedValue(jsonResponse({ id: "abc" }));
    vi.stubGlobal("fetch", fetchMock);

    const result = await apiClient.request<{ id: string }>("/api/v1/servers", { token: "t0ken" });

    expect(result).toEqual({ id: "abc" });
    const init = fetchMock.mock.calls[0]?.[1];
    expect(init.headers.Authorization).toBe("Bearer t0ken");
  });

  it("omits the Authorization header when no token is given", async () => {
    const fetchMock = vi.fn().mockResolvedValue(jsonResponse({}));
    vi.stubGlobal("fetch", fetchMock);

    await apiClient.request("/api/v1/health");

    const init = fetchMock.mock.calls[0]?.[1];
    expect(init.headers.Authorization).toBeUndefined();
  });

  it("returns undefined for a 204", async () => {
    vi.stubGlobal("fetch", vi.fn().mockResolvedValue(new Response(null, { status: 204 })));

    await expect(apiClient.request("/api/v1/servers/x")).resolves.toBeUndefined();
  });

  it("surfaces a string detail as the error message", async () => {
    vi.stubGlobal(
      "fetch",
      vi.fn().mockResolvedValue(
        jsonResponse({ detail: "Deployment abc is already running for this app." }, 409),
      ),
    );

    await expect(apiClient.request("/api/v1/apps/x/deploy", { method: "POST" })).rejects.toThrow(
      "Deployment abc is already running for this app.",
    );
  });

  it("flattens a validation detail array", async () => {
    vi.stubGlobal(
      "fetch",
      vi.fn().mockResolvedValue(
        jsonResponse(
          { detail: [{ loc: ["body", "host"], msg: "Field required" }] },
          422,
        ),
      ),
    );

    await expect(apiClient.request("/api/v1/servers", { method: "POST" })).rejects.toThrow(
      "body.host: Field required",
    );
  });

  it("falls back to a generic message for an unparseable error body", async () => {
    vi.stubGlobal(
      "fetch",
      vi.fn().mockResolvedValue(new Response("not json", { status: 500 })),
    );

    await expect(apiClient.request("/api/v1/servers")).rejects.toThrow("Request failed");
  });

  it("explains an unreachable API and preserves the cause", async () => {
    const networkError = new TypeError("Failed to fetch");
    vi.stubGlobal("fetch", vi.fn().mockRejectedValue(networkError));

    await expect(apiClient.request("/api/v1/servers")).rejects.toMatchObject({
      message: expect.stringContaining("Could not reach the API"),
      cause: networkError,
    });
  });
});

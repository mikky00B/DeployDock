import { afterEach, describe, expect, it, vi } from "vitest";

import { apiClient } from "./client";
import { repinServerHostKey, testServerConnection, updateServer } from "./servers";

afterEach(() => {
  vi.restoreAllMocks();
});

describe("server host key endpoints", () => {
  it("posts to the host-key endpoint to re-pin", async () => {
    const requestMock = vi.spyOn(apiClient, "request").mockResolvedValue({
      fingerprint: "SHA256:new",
      algorithm: "ssh-ed25519",
      previous_fingerprint: "SHA256:old",
      message: "Host key pinned.",
    });

    const result = await repinServerHostKey("t0ken", "server-1");

    expect(requestMock).toHaveBeenCalledWith("/api/v1/servers/server-1/host-key", {
      method: "POST",
      token: "t0ken",
    });
    expect(result.previous_fingerprint).toBe("SHA256:old");
  });

  it("returns the pinned fingerprint from a connection test", async () => {
    vi.spyOn(apiClient, "request").mockResolvedValue({
      success: true,
      status: "connected",
      message: "SSH connection succeeded",
      host_key_fingerprint: "SHA256:pinned",
    });

    const result = await testServerConnection("t0ken", "server-1");

    expect(result.host_key_fingerprint).toBe("SHA256:pinned");
  });
});

describe("updateServer", () => {
  it("drops undefined and empty fields so a blank key does not overwrite the stored one", async () => {
    const requestMock = vi.spyOn(apiClient, "request").mockResolvedValue({});

    await updateServer("t0ken", "server-1", {
      name: "Renamed",
      host: "203.0.113.10",
      port: 22,
      username: "deploy",
      private_key: "",
    });

    const options = requestMock.mock.calls[0]?.[1];
    expect(options?.body).toEqual({
      name: "Renamed",
      host: "203.0.113.10",
      port: 22,
      username: "deploy",
    });
  });
});

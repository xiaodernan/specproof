import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { apiGet, apiPost, ApiError, NETWORK_UNREACHABLE } from "../api";

// The shared client must convert a rejected fetch (backend down / bad base URL
// / offline / CORS) into an actionable ApiError, while letting caller-driven
// aborts surface as AbortError so they are never mistaken for a failure.
const fetchMock = vi.fn();
beforeEach(() => { vi.stubGlobal("fetch", fetchMock); fetchMock.mockReset(); });
afterEach(() => { vi.unstubAllGlobals(); });

describe("api client network guard", () => {
  it("POST: rejects with a Chinese actionable message on a raw transport failure", async () => {
    fetchMock.mockRejectedValue(new TypeError("Failed to fetch"));
    const err = (await apiPost("/jobs", { a: 1 }).catch((e: unknown) => e)) as ApiError;
    expect(err).toBeInstanceOf(ApiError);
    expect(err.status).toBe(0);
    expect(err.message).toBe(NETWORK_UNREACHABLE);
    expect(err.message).toContain("无法连接到服务");
    expect(err.message).not.toMatch(/Failed to fetch/);
  });

  it("GET: same translation for read requests", async () => {
    fetchMock.mockRejectedValue(new TypeError("NetworkError"));
    const err = (await apiGet("/api/v1/health").catch((e: unknown) => e)) as ApiError;
    expect(err).toBeInstanceOf(ApiError);
    expect(err.message).toBe(NETWORK_UNREACHABLE);
  });

  it("rethrows AbortError untouched so cancellation is not a fake outage", async () => {
    fetchMock.mockRejectedValue(new DOMException("Aborted", "AbortError"));
    const err = (await apiGet("/jobs/x").catch((e: unknown) => e)) as DOMException;
    expect(err).toBeInstanceOf(DOMException);
    expect(err.name).toBe("AbortError");
  });
});

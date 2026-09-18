import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { apiGet, openAgentEventStream, openProgressStream, setApiKey, setBearerToken } from "../api";

const fetchMock = vi.fn();
beforeEach(() => { vi.stubGlobal("fetch", fetchMock); fetchMock.mockReset(); sessionStorage.clear(); });
afterEach(() => { vi.unstubAllGlobals(); vi.useRealTimers(); });

function streamResponse(chunks: string[]) {
  const encoder = new TextEncoder();
  return new Response(new ReadableStream({ start(controller) {
    chunks.forEach((chunk) => controller.enqueue(encoder.encode(chunk)));
    controller.close();
  } }), { headers: { "Content-Type": "text/event-stream" } });
}
async function flush() { for (let n = 0; n < 15; n += 1) await Promise.resolve(); }

describe("authenticated SSE transport", () => {
  it("reads named progress across chunks and sends bearer credentials in headers", async () => {
    setApiKey("legacy-key"); setBearerToken("tenant-token");
    fetchMock.mockResolvedValue(streamResponse(["id: 1-0\r\nevent: pro", "gress\r\ndata: {\"sequence\":1,\"percentage\":45}\r\n\r\n"]));
    const events = vi.fn(); const close = openProgressStream("job/one", events, vi.fn());
    await flush();
    expect(fetchMock.mock.calls[0][0]).toBe("/jobs/job%2Fone/progress");
    expect(fetchMock.mock.calls[0][1].headers.Authorization).toBe("Bearer tenant-token");
    expect(fetchMock.mock.calls[0][1].headers["X-API-Key"]).toBeUndefined();
    expect(events).toHaveBeenCalledWith({ sequence: 1, percentage: 45 });
    close();
  });

  it("resumes after the last event and cancels reconnects when disposed", async () => {
    vi.useFakeTimers();
    fetchMock.mockResolvedValue(streamResponse(["id: 8-0\nevent: progress\ndata: {\"sequence\":8}\n\n"]));
    const close = openProgressStream("job-1", vi.fn(), vi.fn());
    await flush();
    fetchMock.mockResolvedValue(streamResponse([": heartbeat\n\n"]));
    await vi.advanceTimersByTimeAsync(1000);
    expect(fetchMock.mock.calls[1][1].headers["Last-Event-ID"]).toBe("8-0");
    close();
    const count = fetchMock.mock.calls.length;
    await vi.advanceTimersByTimeAsync(30000);
    expect(fetchMock).toHaveBeenCalledTimes(count);
  });

  it("delivers named agent events and terminates on done", async () => {
    fetchMock.mockResolvedValue(streamResponse(["event: tool_call\ndata: {\"type\":\"tool_call\",\"seq\":1}\n\nevent: done\ndata: {}\n\n"]));
    const events = vi.fn(); const done = vi.fn(); const status = vi.fn();
    const close = openAgentEventStream("agent-1", events, status, done);
    await flush();
    expect(events).toHaveBeenCalledWith({ type: "tool_call", seq: 1 });
    expect(done).toHaveBeenCalledOnce();
    expect(status).toHaveBeenLastCalledWith("closed");
    close();
  });

  it("does not repeatedly reconnect an unauthorized session", async () => {
    vi.useFakeTimers();
    fetchMock.mockResolvedValue(new Response(JSON.stringify({ detail: "Invalid credential" }), { status: 401 }));
    const close = openProgressStream("job-1", vi.fn(), vi.fn());
    await flush();
    await vi.advanceTimersByTimeAsync(30000);
    expect(fetchMock).toHaveBeenCalledOnce();
    close();
  });

  it("includes useful validation fields and request identifiers in API errors", async () => {
    fetchMock.mockResolvedValue(new Response(JSON.stringify({ detail: [{ loc: ["body", "repo_path"], msg: "Field required" }], error: { code: "VALIDATION_FAILED", request_id: "req-1" } }), { status: 422 }));
    await expect(apiGet("/jobs")).rejects.toMatchObject({ status: 422, message: "repo_path: Field required", code: "VALIDATION_FAILED", requestId: "req-1" });
  });
});

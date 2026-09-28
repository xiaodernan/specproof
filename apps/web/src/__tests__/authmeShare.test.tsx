import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { render, screen, waitFor } from "@testing-library/react";
import { setBearerToken } from "../api";
import TenantSwitcher from "../identity/TenantSwitcher";
import { useRoleAccess } from "../ui/useRoleAccess";

// #119: one page mount used to ask /auth/me once per reader -- the shell (App.tsx),
// the tenant switcher in the sidebar, and the page's own role gate each fetched the
// same answer for the same credential. Since #121 a feedback vote waits for this
// answer before it can name who voted, so the duplicate is a latency the reviewer
// feels, not just traffic.
//
// What is locked here is the product claim, measured as a request count and as the
// identity that ends up on screen -- not an implementation detail, so the sharing
// may move anywhere without rewriting these tests.

const PRINCIPAL = {
  user_id: "u-1",
  tenant_id: "0f9e0000-0000-0000-0000-000000000001",
  roles: ["operator"],
  scopes: [],
  email: "op@a.example.com",
};

function jsonResponse(body: unknown, status = 200): Response {
  return {
    ok: status >= 200 && status < 300,
    status,
    statusText: "",
    json: () => Promise.resolve(body),
    headers: new Headers(),
  } as Response;
}

function mockStorage() {
  const store = new Map<string, string>();
  return {
    getItem: vi.fn((k: string) => store.get(k) ?? null),
    setItem: vi.fn((k: string, v: string) => void store.set(k, v)),
    removeItem: vi.fn((k: string) => void store.delete(k)),
    key: vi.fn(() => null),
    clear: vi.fn(() => void store.clear()),
    length: 0,
  };
}

function bearerOf(init?: RequestInit): string {
  const headers = init?.headers as Record<string, string> | undefined;
  return String(headers?.["Authorization"] ?? "").replace(/^Bearer /, "");
}

function authMeCalls(fetchMock: ReturnType<typeof vi.fn>): number {
  return fetchMock.mock.calls.filter((call: unknown[]) =>
    String(call[0]).endsWith("/auth/me")
  ).length;
}

/** Answers with the caller's own bearer token turned into a user id, so reusing
 * another credential's answer is visible on screen rather than only in a count. */
function perCredentialFetch(tokenToUserId: Record<string, string>) {
  return vi.fn((_input: RequestInfo | URL, init?: RequestInit) =>
    Promise.resolve(
      jsonResponse({ principal: { ...PRINCIPAL, user_id: tokenToUserId[bearerOf(init)] } })
    )
  );
}

/** A page-level access gate -- the shape pages/Audit.tsx and friends render. */
function Gate({ id = "gate" }: { id?: string }) {
  const access = useRoleAccess(["admin"]);
  return <span data-testid={id}>{access.checked ? String(access.userId) : "pending"}</span>;
}

beforeEach(() => {
  vi.stubGlobal("sessionStorage", mockStorage());
  vi.stubGlobal("localStorage", mockStorage());
});

afterEach(() => {
  vi.unstubAllGlobals();
});

describe("one /auth/me round trip per credential (#119)", () => {
  it("the sidebar switcher and a page gate share a single round trip", async () => {
    setBearerToken("sp_token_a");
    const fetchMock = perCredentialFetch({ sp_token_a: "u-1" });
    vi.stubGlobal("fetch", fetchMock);

    render(
      <>
        <TenantSwitcher />
        <Gate />
      </>
    );

    // Both readers get their answer ...
    await waitFor(() => expect(screen.getByTestId("gate").textContent).toBe("u-1"));
    expect(await screen.findByText("当前空间 · 0f9e0000")).toBeTruthy();
    // ... from ONE request, not one each.
    expect(authMeCalls(fetchMock)).toBe(1);
  });

  it("a changed credential is read again, and the answer shown is the new one", async () => {
    setBearerToken("sp_token_a");
    const fetchMock = perCredentialFetch({ sp_token_a: "u-1", sp_token_b: "u-2" });
    vi.stubGlobal("fetch", fetchMock);

    const first = render(<Gate />);
    await waitFor(() => expect(screen.getByTestId("gate").textContent).toBe("u-1"));
    first.unmount();

    // Exactly what the tenant switcher and the login form do to change identity.
    setBearerToken("sp_token_b");
    render(<Gate />);
    await waitFor(() => expect(screen.getByTestId("gate").textContent).toBe("u-2"));
    expect(authMeCalls(fetchMock)).toBe(2);
  });

  it("a failed read is not remembered as 'no identity'", async () => {
    setBearerToken("sp_token_a");
    let attempt = 0;
    const fetchMock = vi.fn((_input: RequestInfo | URL) => {
      attempt += 1;
      return Promise.resolve(
        attempt === 1
          ? jsonResponse({ detail: "backend blip" }, 503)
          : jsonResponse({ principal: PRINCIPAL })
      );
    });
    vi.stubGlobal("fetch", fetchMock);

    const first = render(<Gate />);
    // A failure settles that reader as unknown (the gate itself is fail-open) ...
    await waitFor(() => expect(screen.getByTestId("gate").textContent).toBe("null"));
    first.unmount();

    // ... but the next reader asks again instead of inheriting that verdict.
    render(<Gate />);
    await waitFor(() => expect(screen.getByTestId("gate").textContent).toBe("u-1"));
    expect(authMeCalls(fetchMock)).toBe(2);
  });

  it("a credential switched mid-flight is not answered by the older read", async () => {
    // The login form and the tenant switcher both swap the credential while a
    // shell read may still be in flight, so three things have to hold at once:
    // the new credential is asked about, the answer shown is the new identity, and
    // the older read settling late does not discard the newer one's shared read.
    setBearerToken("sp_token_a");
    const releases: Array<(r: Response) => void> = [];
    const held = () => new Promise<Response>((resolve) => releases.push(resolve));
    const ids: Record<string, string> = { sp_token_a: "u-1", sp_token_b: "u-2" };
    let calls = 0;
    const fetchMock = vi.fn((_input: RequestInfo | URL, init?: RequestInit) => {
      calls += 1;
      if (calls <= 2) return held();
      return Promise.resolve(jsonResponse({ principal: { ...PRINCIPAL, user_id: ids[bearerOf(init)] } }));
    });
    vi.stubGlobal("fetch", fetchMock);

    render(<Gate id="first" />);
    // Wait until that read is really in flight before swapping the credential:
    // the sharing window is the round trip itself, and the readers of one page
    // mount all open inside it.
    await waitFor(() => expect(authMeCalls(fetchMock)).toBe(1));
    expect(screen.getByTestId("first").textContent).toBe("pending");

    setBearerToken("sp_token_b");
    render(<Gate id="second" />);
    await waitFor(() => expect(authMeCalls(fetchMock)).toBe(2));

    // The first read lands now, after the second one started.
    releases[0](jsonResponse({ principal: PRINCIPAL }));
    await waitFor(() => expect(screen.getByTestId("first").textContent).toBe("u-1"));

    // A third reader on the same (new) credential still shares the second read.
    render(<Gate id="third" />);
    releases[1](jsonResponse({ principal: { ...PRINCIPAL, user_id: "u-2" } }));
    await waitFor(() => expect(screen.getByTestId("third").textContent).toBe("u-2"));
    expect(authMeCalls(fetchMock)).toBe(2);
  });
});

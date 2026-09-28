r"""#112: the sidebar's role gates must be derived, not copied from a comment.

Measured before this gate existed (census over apps/web/src, non-test):

    App.tsx:107                     canManage  = ["admin", "operator"]
    App.tsx:108                     canBill    = ["admin", "operator", "auditor"]
    App.tsx:111                     canAudit   = AUDIT_ROLES (imported)
    identity/useIdentityAccess.ts   canManage  = roles.includes("admin") || .includes("operator")
    pages/Billing.tsx:71            BILLING_ROLES = ["admin", "operator", "auditor"]
    ui/auditLabels.ts:59            AUDIT_ROLES   = ["admin", "auditor"]

The audit surface shared one declaration between nav and page; the identity and
billing surfaces each carried TWO, written by hand at different times. Nothing
compared either pair to ``api/identity/principal.py::ROLE_MATRIX``, so editing
the matrix could — and would — leave the sidebar advertising a page whose calls
the server refuses, or hiding a page a role can still open, with every test in
the repo still green: each test renders one side in isolation.

So the value is no longer typed here either. Each surface's role set is derived
here from two server sources and compared to one shared web declaration:

    page files (this repo)  ->  the /api/ paths they request
    classify_request(...)   ->  the (resource, action) each path needs
    ROLE_MATRIX             ->  the roles granted that action

and the intersection over the calls a surface actually makes must equal what
apps/web declares. The scope (which files belong to which surface) is declared
below and is what a reviewer can check; the VALUES on both sides come from
source, which is what makes drift visible.
"""

from __future__ import annotations

import re
from pathlib import Path

from api.identity.principal import ROLE_MATRIX, ROLE_VALUES, classify_request

REPO = Path(__file__).resolve().parents[2]
WEB = REPO / "apps" / "web" / "src"
ACCESS_ROLES = WEB / "ui" / "accessRoles.ts"
APP_TSX = WEB / "App.tsx"

# Scope: the files a surface is made of. Kept short on purpose — a surface whose
# pages cannot be listed in one line is a surface this gate should not claim to
# cover (assert_covered below refuses an empty or blind read instead of passing).
SURFACES: dict[str, tuple[str, list[str]]] = {
    "identity": (
        "IDENTITY_ROLES",
        ["identity/IdentityApp.tsx", "identity/pages/TenantUsers.tsx",
         "identity/pages/TenantTokens.tsx", "identity/useIdentityAccess.ts"],
    ),
    "billing": ("BILLING_ROLES", ["pages/Billing.tsx"]),
    "audit": ("AUDIT_ROLES", ["pages/Audit.tsx"]),
    # #116: a button, not a page. The governed action is the one FindingDetail
    # casts (POST /api/v1/jobs/{id}/feedback), so the derivation reads the same
    # call the click does.
    "vote": ("FEEDBACK_VOTE_ROLES", ["pages/FindingDetail.tsx"]),
}

# The subset of SURFACES that App.tsx gates from the sidebar. Kept separate from
# SURFACES because since #116 a governed action can also be a button: the nav
# count is a claim about the sidebar, and letting it grow to cover a button would
# let a genuinely missing nav gate pass unnoticed.
NAV_SURFACES = ("identity", "billing", "audit")

# Paths every principal may read, so they cannot narrow a surface's role set.
# /auth/me answers with the caller's own principal; classify_request() returns
# None for it by design (api/identity/principal.py:226).
SELF_PATHS = {"/auth/me"}

# An api* call site: the verb, an optional generic type argument, then the open
# paren. The type argument may contain `;` (object literals such as
# `<{ users: UserRow[]; count: number }>`, which is the shape api.ts uses), so
# only quotes and parens are banned inside it — that is also what keeps
# `import { apiGet } from "../api";` from reading as a call, because the gap
# there is `, getAuthMe } from "../api";` and not whitespace.
_API_SITE_RE = re.compile(r'\bapi(Get|Post|Delete|Put)\b\s*(?:<[^"()]{0,300}?>)?\s*\(')
_PATH_RE = re.compile("""['"`](/(?:api|auth)/[^'"`?#$]*)""")
_IDENT_RE = re.compile(r"^\s*(\w+)\s*$")
_IMPORT_API_RE = re.compile(r"import\s*(?:type\s*)?\{([^}]*)\}\s*from\s*[\"'][^\"']*api[\"']", re.S)
_FUNC_RE = re.compile(r"^export (?:async )?function (\w+)", re.MULTILINE)
_DECL_RE = re.compile(r"(\w+): readonly string\[\] = \[([^\]]*)\]")
_NAV_ROLE_RE = re.compile(r"roles: (\w+)")
_SELECT_RE = re.compile(r"<select\b[^>]*>(.*?)</select>", re.DOTALL)

_METHODS = {"get": "GET", "post": "POST", "delete": "DELETE", "put": "PUT"}


def _text(path: Path) -> str:
    assert path.is_file(), f"{path.relative_to(REPO)} is gone — the scope is stale"
    return path.read_text(encoding="utf-8")


def _api_ts() -> str:
    return _text(WEB / "api.ts")


def api_function_bodies() -> dict[str, str]:
    """name -> source slice, for the exported functions in api.ts."""
    text = _api_ts()
    marks = [(m.start(), m.group(1)) for m in _FUNC_RE.finditer(text)]
    assert marks, "api.ts exposes no exported function — the probe, not the code, broke"
    out: dict[str, str] = {}
    for i, (start, name) in enumerate(marks):
        end = marks[i + 1][0] if i + 1 < len(marks) else len(text)
        out[name] = text[start:end]
    return out


def _arg_region(source: str, open_paren: int) -> str:
    """Text between the call's outermost parens, quote-aware."""
    depth = 0
    i = open_paren
    quote: str | None = None
    while i < len(source):
        ch = source[i]
        if quote is not None:
            if ch == "\\":
                i += 2
                continue
            if ch == quote:
                quote = None
        elif ch in """'"`""":
            quote = ch
        elif ch == "(":
            depth += 1
        elif ch == ")":
            depth -= 1
            if depth == 0:
                return source[open_paren + 1 : i]
        i += 1
    raise AssertionError("unbalanced parens: this reader cannot finish the call it started")


def _initializer_before(source: str, name: str, call_start: int) -> str | None:
    """The last `const/let name = ...;` preceding the call, initializer only."""
    found = None
    for cand in re.finditer(rf"(?:const|let)\s+{re.escape(name)}\s*=\s*", source):
        if cand.start() >= call_start:
            break
        found = cand
    if found is None:
        return None
    rest = source[found.end() : call_start]
    end = rest.find(";")
    return rest if end == -1 else rest[:end]


def _top_split(text: str, sep: str) -> list[str]:
    """Split on `sep` only where it sits outside quotes and brackets."""
    parts: list[str] = []
    depth = 0
    quote: str | None = None
    cur: list[str] = []
    i = 0
    while i < len(text):
        ch = text[i]
        if quote is not None:
            cur.append(ch)
            if ch == "\\":
                cur.append(text[i + 1])
                i += 2
                continue
            if ch == quote:
                quote = None
        elif ch in """'"`""":
            quote = ch
            cur.append(ch)
        elif ch in "([{":
            depth += 1
            cur.append(ch)
        elif ch in ")]}":
            depth -= 1
            cur.append(ch)
        elif ch == sep and depth == 0:
            parts.append("".join(cur))
            cur = []
        else:
            cur.append(ch)
        i += 1
    parts.append("".join(cur))
    return parts


def _concat_path(arg: str) -> str | None:
    r"""One path out of `"/api/v1/jobs/" + encodeURIComponent(jobId) + "/feedback"`.

    api.ts builds several governed paths by concatenation, and a literal-only scan
    read `POST /api/v1/jobs/` for the feedback call: a path the browser never
    sends. Dynamic segments become `_` so the resolved path keeps the shape the
    server matches. Returns None when the argument is not a concatenation starting
    at a rooted path, so the caller falls back instead of inventing a path.

    Only the call's first top-level argument is looked at, because that is the
    path parameter in every api* wrapper; reading the whole paren region glues the
    body argument onto the last segment (`"/feedback",\n draft`) and turns the
    trailing literal into a `_`.
    """
    parts = _top_split(arg, "+")
    if len(parts) < 2:
        return None
    segs: list[str] = []
    for part in parts:
        literal = re.match(r"""^\s*['"`](.*?)['"`]\s*$""", part, re.S)
        if literal is not None:
            segs.extend(s for s in literal.group(1).split("/") if s)
        elif part.strip():
            segs.append("_")
        else:
            return None
    joined = "/" + "/".join(segs)
    return joined if joined.startswith(("/api/", "/auth/")) else None


def _calls_in(source: str) -> tuple[list[tuple[str, str]], list[str]]:
    """([ (METHOD, path], opaque descriptions) per api* call in this source.

    The path may be a literal on its own, a concatenation of literals and dynamic
    segments, or a local `const` the call passes by name (Audit.tsx builds its
    query string in one). Only the first top-level argument is read, since that is
    the path parameter of every api* wrapper. Anything else comes back as opaque so
    the caller can refuse rather than silently gate a page on fewer calls than it
    makes.
    """
    calls: list[tuple[str, str]] = []
    opaque: list[str] = []
    for m in _API_SITE_RE.finditer(source):
        if source[: m.start()].rstrip().endswith("function"):
            continue
        region = _arg_region(source, m.end() - 1)
        arg = _top_split(region, ",")[0]
        joined = _concat_path(arg)
        paths = [joined] if joined else _PATH_RE.findall(arg)
        if not paths:
            ident = _IDENT_RE.match(arg)
            if ident:
                paths = _PATH_RE.findall(
                    _initializer_before(source, ident.group(1), m.start()) or ""
                )
        if not paths:
            opaque.append(
                f"{_METHODS[m.group(1).lower()]} {m.group(0)[:-1].strip()}({arg.strip()[:60]})"
            )
            continue
        calls += [(_METHODS[m.group(1).lower()], p) for p in paths]
    return calls, opaque


def surface_calls(surface: str) -> list[tuple[str, str]]:
    """Every /api/ path the surface's own files reach, direct or via api.ts."""
    bodies = api_function_bodies()
    calls: list[tuple[str, str]] = []
    opaque: list[str] = []
    for member in SURFACES[surface][1]:
        source = _text(WEB / member)
        found, unread = _calls_in(source)
        calls += found
        opaque += [f"{member}: {u}" for u in unread]
        imported = {
            name.strip().split(" as ")[0]
            for block in _IMPORT_API_RE.findall(source)
            for name in block.split(",") if name.strip()
        }
        for name in sorted(imported & set(bodies)):
            found, unread = _calls_in(bodies[name])
            calls += found
            opaque += [f"api.ts::{name}: {u}" for u in unread]
    assert not opaque, (
        f"{surface}: calls this gate cannot resolve to a path: {sorted(set(opaque))}. "
        "A page whose requests the reader cannot enumerate is a page whose role set "
        "this gate cannot check — fix the reader, do not let the gate go quiet."
    )
    assert calls, f"surface {surface} makes no /api/ call — this gate reads nothing"
    return sorted(set(calls))


def surface_cells(surface: str) -> list[tuple[str, str, str]]:
    """(method, path, 'resource:action') for every governed call of a surface."""
    cells: list[tuple[str, str, str]] = []
    unclassified: list[str] = []
    for method, path in surface_calls(surface):
        if path in SELF_PATHS:
            continue
        ra = classify_request(method, path)
        if ra is None:
            unclassified.append(f"{method} {path}")
            continue
        cells.append((method, path, f"{ra.resource}:{ra.action}"))
    assert not unclassified, (
        f"{surface}: calls the RBAC classifier does not govern: {sorted(set(unclassified))}. "
        "Either they need a cell (and this gate must compute one) or they belong in "
        "SELF_PATHS with a reason — silently skipping them would let a page be gated "
        "by fewer calls than it makes."
    )
    return cells


def roles_for(cell: str) -> set[str]:
    resource, _, action = cell.partition(":")
    return {
        role
        for role, grants in ROLE_MATRIX.items()
        if action in grants.get(resource, frozenset())
    }


def derived_roles(surface: str) -> set[str]:
    """Roles that may run EVERY governed call the surface makes."""
    cells = {cell for _, _, cell in surface_cells(surface)}
    assert cells, f"{surface}: no governed cell — the derivation is blind"
    return set.intersection(*(roles_for(cell) for cell in cells))


def declared_roles() -> dict[str, set[str]]:
    text = _text(ACCESS_ROLES)
    found = {
        name: {s.strip().strip('"') for s in body.split(",") if s.strip()}
        for name, body in _DECL_RE.findall(text)
    }
    assert found, "ui/accessRoles.ts declares no readonly string[] — the probe broke"
    return found


def test_every_gated_nav_item_resolves_to_one_shared_declaration() -> None:
    """App.tsx may gate a nav item only by a name declared in the module.

    The count is checked against the surfaces the *sidebar* gates, not against
    SURFACES: since #116 a governed action can be a button rather than a page, and
    letting the nav count grow to cover it would let a genuine fifth nav item pass
    with nobody deriving its set.
    """
    gated = _NAV_ROLE_RE.findall(_text(APP_TSX))
    declared = declared_roles()
    assert len(gated) == len(NAV_SURFACES), (
        f"App.tsx gates {sorted(gated)} but this gate's nav surfaces are "
        f"{sorted(NAV_SURFACES)}: a fourth gated page appeared (or one was removed) "
        "and its role set is unchecked either way"
    )
    missing = [name for name in gated if name not in declared]
    assert not missing, f"App.tsx nav references undeclared role sets: {missing}"
    nav_names = {SURFACES[s][0] for s in NAV_SURFACES}
    assert set(gated) == nav_names, (
        f"App.tsx gates {sorted(gated)} but the nav surfaces are declared for "
        f"{sorted(nav_names)} — that is a gated item whose set is not the one this "
        "gate derives, or a nav surface nobody gates"
    )


def test_a_declaration_nobody_reads_is_not_a_gate() -> None:
    """Each shared role set must be used by the surface it claims to govern.

    #112 collapsed five hand copies into three declarations; #116 added a fourth
    for a button. A declaration that no page or nav item reads proves nothing, so
    the gate refuses it rather than counting it as coverage.
    """
    declared = declared_roles()
    unread: list[str] = []
    for surface, (name, members) in SURFACES.items():
        assert name in declared, f"{surface}: declares {name} but accessRoles.ts has no such set"
        readers = list(members) + (["App.tsx"] if surface in NAV_SURFACES else [])
        if not any(name in _text(WEB / member) for member in readers):
            unread.append(f"{name} ({surface})")
    assert not unread, (
        f"role sets declared but never read by their surface: {unread}"
    )


def test_each_surface_role_set_is_the_one_the_matrix_derives() -> None:
    declared = declared_roles()
    for surface in sorted(SURFACES):
        name = SURFACES[surface][0]
        want = derived_roles(surface)
        got = declared[name]
        assert got == want, (
            f"{surface}: apps/web declares {name} = {sorted(got)} but the matrix "
            f"grants {sorted(want)} for the calls {name} gates "
            f"({sorted({c for _, _, c in surface_cells(surface)})}). "
            f"extra={sorted(got - want)} missing={sorted(want - got)}"
        )


def test_the_vote_set_is_derived_from_the_vote_call_not_the_page() -> None:
    """FEEDBACK_VOTE_ROLES gates a button, so it must come from the POST the click
    sends — not from whatever else FindingDetail happens to read.

    The page's GETs classify as cases:read, which is a strictly larger role set
    than the POST's cases:trigger. Intersecting the page therefore returns the
    trigger set today, and that equality is *not* the claim: if the vote call were
    ever renamed or the page lost its POST, the intersection would quietly keep
    producing a plausible set for a button nobody can press. So this test pins the
    call itself (a POST whose resolved path ends in the feedback suffix) and then
    requires the declared set to equal the roles that single cell grants.
    """
    cells = surface_cells("vote")
    votes = [(m, p, c) for m, p, c in cells if m == "POST" and p.endswith("/feedback")]
    assert len(votes) == 1, (
        f"the vote surface resolves {len(votes)} feedback POSTs out of {cells}; "
        "this gate's claim is about exactly one button, so a renamed, duplicated or "
        "missing vote call must stop here rather than be averaged with the page's "
        "reads"
    )
    method, path, cell = votes[0]
    assert path.startswith("/api/v1/jobs/"), path
    declared = declared_roles()[SURFACES["vote"][0]]
    want = roles_for(cell)
    assert declared == want, (
        f"FEEDBACK_VOTE_ROLES = {sorted(declared)} but {method} {path} needs {cell}, "
        f"which the matrix grants to {sorted(want)}"
    )


def test_the_reader_resolves_every_call_shape_the_pages_use() -> None:
    """Both ways, because a reader that quietly under-reads gates on less than the
    page actually does.

    The five shapes below are the ones present in apps/web/src today: a literal on
    the same line, a literal on the next line of a multi-line call, a generic type
    argument containing `;` (`<{ users: UserRow[]; count: number }>`, the shape
    api.ts uses — a statement-boundary scan loses it), a path built in a local
    const and passed by name (Audit.tsx), a rooted path concatenated out of
    literals and an `encodeURIComponent(...)` segment (getJobFeedback /
    createFindingFeedback), plus a template literal. The import line and the
    `export async function apiGet<T>(path: string, ...)` definition must NOT read
    as calls.
    """
    source = (
        'import { ApiError, apiGet, getAuthMe } from "../../api";\n'
        "export async function apiGet<T>(path: string, signal?: AbortSignal): Promise<T> {\n"
        '  const res = await fetch(BASE + path, { method: "GET", signal });\n'
        "  return res.json();\n"
        "}\n"
        "export function probe(limit: number, id: string) {\n"
        '  const query = "/api/v1/admin/audit?limit=" + limit;\n'
        "  apiGet<AuditResponse>(query);\n"
        '  apiGet<{ users: UserRow[]; count: number }>("/api/v1/admin/users");\n'
        "  apiPost<{ user: UserRow }>(\n"
        '    "/api/v1/admin/users",\n'
        "    { email, role },\n"
        "  );\n"
        "  apiPost<FeedbackReceipt>(\n"
        '    "/api/v1/jobs/" + encodeURIComponent(jobId) + "/feedback",\n'
        "    draft,\n"
        "  );\n"
        "  return apiDelete(`/api/v1/admin/tokens/${id}`);\n"
        "}\n"
    )
    calls, opaque = _calls_in(source)
    assert not opaque, f"shapes the reader refused: {opaque}"
    assert calls == [
        ("GET", "/api/v1/admin/audit"),
        ("GET", "/api/v1/admin/users"),
        ("POST", "/api/v1/admin/users"),
        ("POST", "/api/v1/jobs/_/feedback"),
        ("DELETE", "/api/v1/admin/tokens/"),
    ], calls


def test_a_concatenated_path_keeps_its_trailing_literal() -> None:
    """Reverse control for the shape above: a concatenation this reader cannot root
    must be reported, not half-read.

    `apiPost(fetchBase + "/feedback", draft)` starts at a variable, so no rooted
    path comes out of it. Before the first-argument split existed, the trailing
    `"/feedback", draft` was not recognised as a literal either and the call
    resolved to `/api/v1/jobs/_/_` — a path that classifies the same as the real
    one here, which is exactly why the wrong path could pass every assertion the
    gate made. Refusing it keeps the gap visible.
    """
    calls, opaque = _calls_in('apiPost(fetchBase + "/feedback", draft);\n')
    assert calls == [], calls
    assert len(opaque) == 1, f"unrootable concat was dropped: {opaque}"
    assert opaque[0].startswith("POST"), opaque[0]


def test_the_reader_reports_a_call_it_cannot_resolve() -> None:
    """Reverse control: an unresolvable call must surface, not vanish.

    With the previous one-line regex, `apiGet(remoteUrl)` produced no pair at all
    and the surface it belonged to read as 'makes no /api/ call' — a page gated
    on fewer calls than it makes looks identical to a page with no calls.
    """
    calls, opaque = _calls_in("apiGet<{ a: number }>(remoteUrl);\n")
    assert calls == []
    assert len(opaque) == 1, f"unreadable call was dropped instead of reported: {opaque}"


def test_no_surface_gates_on_a_role_literal_written_at_the_call_site() -> None:
    """The copy this gate replaces must not come back (same rule as #81's vocabulary)."""
    offenders: list[str] = []
    for path in sorted(WEB.rglob("*.ts*")):
        rel = path.relative_to(WEB).as_posix()
        if rel == "ui/accessRoles.ts" or ".test." in rel:
            continue
        for line in _text(path).splitlines():
            tokens = {t for t in re.findall(r'["\'](\w+)["\']', line) if t in set(ROLE_VALUES)}
            if tokens and re.search(r"roles\b.*(\.includes|\.some)", line):
                offenders.append(f"{rel}: {line.strip()[:90]}")
    assert not offenders, (
        "role literals compared against principal.roles outside ui/accessRoles.ts "
        "cannot be checked against the matrix by this gate:\n  " + "\n  ".join(offenders)
    )


def test_the_role_vocabulary_the_identity_pages_offer_is_the_servers() -> None:
    """Two places hand the four roles to an admin: each role `<select>` and the
    label map. Both must equal ROLE_VALUES, or a new server role is unassignable
    (or renders as its raw token) with no test noticing.

    The pickers are checked one by one, not as a union: this page carries two
    identical role selects (the table row's picker and the create form's), and a
    union would stay green while only one of them lost a role — which is exactly
    the half-edit that leaves one picker advertising a 403.
    """
    server = set(ROLE_VALUES)
    options = _text(WEB / "identity/pages/TenantUsers.tsx")
    pickers = [
        set(re.findall(r'<option value="(\w+)">', block))
        for block in _SELECT_RE.findall(options)
        if set(re.findall(r'<option value="(\w+)">', block)) & server
    ]
    assert len(pickers) == 2, (
        f"TenantUsers.tsx offers {len(pickers)} role pickers, measured 2 (the row "
        "picker and the create-form picker); a third picker means this test's "
        "per-picker claim needs re-reading, not a new number typed in"
    )
    for i, got in enumerate(pickers):
        assert got == server, (
            f"role picker #{i + 1} in TenantUsers.tsx offers {sorted(got)} but "
            f"ROLE_VALUES is {sorted(server)}; extra={sorted(got - server)} "
            "missing=" + str(sorted(server - got))
        )
    body = _text(WEB / "identity/labels.ts")
    assert "ROLE_CN: Record<string, string> = {" in body, (
        "identity/labels.ts no longer declares ROLE_CN the way this gate anchors on — "
        "re-read the file and fix the anchor here rather than trusting an unanchored scan"
    )
    role_cn = body.split("ROLE_CN: Record<string, string> = {", 1)[-1].split("};", 1)[0]
    keys = set(re.findall(r"^  (\w+):", role_cn, re.MULTILINE))
    assert keys == server, (
        f"identity/labels.ts ROLE_CN covers {sorted(keys)}, ROLE_VALUES is {sorted(server)}; "
        "a role with no gloss shows as a bare token to the person managing accounts"
    )


_ACCESS_BODY_RE = re.compile(r"getAuthMe\(\)[\s\S]{0,600}?setChecked\(true\)")


def test_only_one_module_asks_who_the_caller_is() -> None:
    """#117: the /auth/me + fail-open body lives in exactly one module.

    Measured before this clause: pages/Audit.tsx, pages/Billing.tsx and
    identity/useIdentityAccess.ts each hand-wrote the same
    getAuthMe().then(...)/catch(fail-open)/finally(setChecked) loop, and #116 added a
    fourth (ui/useRoleAccess.ts). Four bodies means four private answers to "what does
    an unknown identity do" — the same failure #112 closed for role sets: the copies can
    drift and every test that renders one page alone stays green.

    The count is a shape match over every non-test module under apps/web/src, and the
    expectation is an exact set, because a clause that reads nothing looks identical to
    one that finds nothing wrong.

    What this does NOT claim: that only one module ever reads /auth/me. Measured at landing,
    App.tsx:97, identity/TenantSwitcher.tsx:24/32 and pages/Login.tsx:82 also call getAuthMe,
    and none of them is an access gate (App keeps the principal for the whole app, the
    switcher reloads after a tenant change, Login verifies a credential just minted). The
    shape named here is the gate body specifically: read identity, fail open, then settle a
    checked flag.
    """
    population = [p for p in sorted(WEB.rglob("*.ts*")) if ".test." not in p.name]
    assert len(population) >= 20, (
        f"only {len(population)} modules under apps/web/src were scanned — that is not "
        "the app, so this clause would be reading nothing"
    )
    carriers = [
        p.relative_to(WEB).as_posix() for p in population if _ACCESS_BODY_RE.search(_text(p))
    ]
    assert carriers == ["ui/useRoleAccess.ts"], (
        f"modules that hand-write the getAuthMe/setChecked body: {carriers}. It must "
        "live once, so the alive flag, the fail-open branch and the role comparison "
        "cannot disagree per page — call useRoleAccess(<SHARED_ROLES>) instead."
    )


_AUTHME_PATH_RE = re.compile(r"""["'`]/auth/me["'`]""")
# An exported no-argument function whose body reads sessionStorage directly: the
# credential readers. Matched by shape so a rename does not mean editing this gate.
_CREDENTIAL_ACCESSOR_RE = re.compile(
    r"export function (\w+)\(\): string \{(?:(?!\}).)*?sessionStorage\.getItem", re.S
)


def auth_me_readers() -> list[str]:
    """Non-test modules under apps/web/src that name the /auth/me path."""
    return [
        p.relative_to(WEB).as_posix()
        for p in sorted(WEB.rglob("*.ts*"))
        if ".test." not in p.name and _AUTHME_PATH_RE.search(_text(p))
    ]


def credential_accessors() -> set[str]:
    """The exported functions that read a credential out of sessionStorage."""
    return set(_CREDENTIAL_ACCESSOR_RE.findall(_api_ts()))


def _function_body(name: str) -> str:
    body = api_function_bodies()[name]
    end = body.find("\n}\n")
    assert end != -1, (
        f"{name} has no closing brace at column 0, so the slice api_function_bodies() "
        "returned runs into the next function and anything read from it is not a body"
    )
    return body[:end]


def test_auth_me_is_read_through_one_shared_call() -> None:
    """#119: one module speaks /auth/me, and it shares one read per credential.

    Measured before this clause existed: a single page mount asked /auth/me once per
    reader — the shell (App.tsx), the tenant switcher in the sidebar, and the page's
    own role gate (ui/useRoleAccess.ts) — so one credential cost two or three
    identical round trips. Since #121 a feedback vote waits for that answer before it
    can name who voted, which makes the duplicates latency a reviewer feels.

    The fix is per-credential sharing inside api.ts::getAuthMe, and it only holds
    while every reader goes through that function: a module that fetched the endpoint
    itself would get no sharing, and nothing else in the repo would notice.

    Both values compared here are derived from source — the module that names the
    path, and the credential readers inside api.ts — so the clause cannot be satisfied
    by renaming, and a blind read is refused instead of counted as a pass.

    What this does NOT claim: that the answer is remembered. It is shared while in
    flight and re-read on the next mount, so a role revoked server-side shows up on
    the next navigation rather than being frozen for the session. The shared-round-trip
    behaviour itself is locked by apps/web/src/__tests__/authmeShare.test.tsx.
    """
    readers = auth_me_readers()
    assert readers == ["api.ts"], (
        f"modules naming /auth/me: {readers}. It must be api.ts::getAuthMe alone: that "
        "is where readers holding the same credential share one in-flight request, so a "
        "second reader would silently cost another round trip on every page mount"
    )
    accessors = credential_accessors()
    assert {"getBearerToken", "getApiKey"} <= accessors, (
        f"the credential readers derived from api.ts are {sorted(accessors)} — the "
        "derivation is blind (or the credential stopped being read from sessionStorage), "
        "and the check below would then compare nothing"
    )
    body = _function_body("getAuthMe")
    assert any(name in body for name in accessors), (
        "getAuthMe() no longer reads the credential, so one answer would be shared "
        f"across credentials as well ({sorted(accessors)} read the credential today). "
        "The credential is the key: a switched credential is a new question"
    )

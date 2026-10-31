"""#543 — the payload a route publishes has to be the payload the browser declared.

``apps/web/src/api.ts`` says, in TypeScript, what the browser believes a response
looks like. ``api/routes/*.py`` says, in Python, what the response is. Before this
number, **nothing in the repository compared the two**. Several test files each
hand-parsed ``export interface`` out of ``api.ts`` for their own one-endpoint claim,
and none of them read a second host: ``ModelConfig`` and ``ConnectionResult`` are
declared *privately* in ``apps/web/src/agent/pages/AgentSettings.tsx``, so an
``export interface``-only lens cannot see the two types that describe the model panel.

That gap is not theoretical, because #542 landed the first hole found by hand: the
dashboard's degraded branch answered a *different key set* than its happy branch, so
the browser read ``undefined`` for a required number and rendered it as a value. The
D-section leg written for #542 checks exactly that one endpoint. The same shape on any
other endpoint is silent today, and it stays silent in both directions: a rename on the
backend, a new key the frontend never named, a route nobody consumes.

So this file draws the line where #542 drew it and holds it with a census. Every number
below is *measured* against the tree this test runs in, and every register has a leg
that recomputes it: a roster that is recited instead of measured is how #541's "only one
definition in the product" gate ended up hand-copied, and how #527's scan root turned
out to be an assumption.

The consumer side had to be widened before the census could mean anything. The guard that
decides which ``apiGet`` mentions are calls read "`const `/`function ` anywhere in the 40
characters to the left", and `const answer = apiGet<{ principal: PrincipalInfo }>(
"/auth/me")` is a call that passes that test. The A12 arm measured what that cost: five
product sites and three test-file mentions were being read as definitions, so the census
held 23 sites instead of 28 and four of the five -- the agent job list, the principal
read, the health page, the model panel's POST -- were their endpoint's only consumer.
Ten of the 28 kept sites mention a declaration keyword inside that window and every one
of them is a call; that population is what this file's guard leg pins, with a floor of 8.
An arm that was trying to plant a different hole found this one, so the gate now measures
the guard itself.

What is deliberately NOT claimed:

* the 29 endpoints with no typed frontend consumer. They are rostered by name, not
  folded: there is no declared shape to compare against, so a payload census there would
  be an assertion with only one side.
* keys a handler attaches only inside one ``if`` arm. The fold merges every
  ``name.update(...)`` / ``name["k"] = ...`` into the handler's branches, so such a key
  reads as always-present. ``CONDITIONAL_KEYS`` names exactly which keys that covers.
* runtime truth. Nothing here makes a request; a route that answers through a shape the
  fold cannot see stays in ``UNBOUND_PAYLOADS`` with a reason that has to point at code.
"""

from __future__ import annotations

import re
import sys
from pathlib import Path

_PROJECT_ROOT = Path(__file__).resolve().parents[2]
if str(_PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(_PROJECT_ROOT))

from tests._payload_plane import (  # noqa: E402
    CallShape,
    CallSite,
    Endpoint,
    Member,
    Pair,
    alias_table,
    call_shapes,
    endpoints,
    frontend_calls,
    members_of_type,
    normalize_path,
    pairings,
    payload_of,
    ts_declarations,
    web_src,
)

REPO = _PROJECT_ROOT

#: A position in the census: ``(verb, normalized path)``. The verb is part of the
#: identity — the same path serves a GET list and a POST create with different
#: payloads, and pairing by path alone manufactured two false findings on
#: ``/agent/jobs`` while this owner was being written.
Key = tuple[str, str]

#: What ``ts_declarations`` answers: declared name -> (host file, members).
Declarations = dict[str, tuple[str, list[Member]]]

API_TS = "apps/web/src/api.ts"


def _endpoint_key(endpoint: Endpoint) -> Key:
    return (endpoint.verb, normalize_path(endpoint.path))


def _pair_key(pair: Pair) -> Key:
    return _endpoint_key(pair.endpoint)


# ---------------------------------------------------------------------------
# Registers. Every entry was produced by running the owner against this tree, and
# each one has a leg that recomputes it. Add a route without a consumer, publish a
# key nobody declared, or make a folded payload unbounded, and the matching leg goes
# red instead of the count drifting.
# ---------------------------------------------------------------------------

#: Routes with no typed frontend call site. Rostered so the number stays visible;
#: not folded, because there is no second side to compare against. Four routes that
#: used to sit here -- `GET /agent/jobs`, `GET /api/v1/health`, `GET /auth/me`,
#: `POST /api/v1/model/config` -- left the register when the consumer reading was
#: widened to calls that sit behind `const`/`await`, and one of them (GET /agent/jobs)
#: pairs only on the loose reading, so it moved to LOOSE_PAIRINGS instead of vanishing.
#: #544 widened the reading twice more -- a call written across lines, and a path held
#: in a same-file `const` -- and fourteen more left this register the same way. Two of
#: them (`GET /api/v1/jobs/{id}/capsule`, `POST /auth/logout`) are still here: their
#: callers reach the backend through `doFetch` directly, which is not a typed client and
#: has no declared shape to compare, so a wider *fold* cannot rescue them.
UNPAIRED_ENDPOINTS: frozenset[Key] = frozenset(
    {
        ("get", "/agent/jobs/{}/event-history"),
        ("get", "/agent/jobs/{}/events"),
        ("get", "/api/v1/admin/certificates/revocations"),
        ("get", "/api/v1/billing/jobs/{}"),
        ("get", "/api/v1/billing/subscriptions"),
        ("get", "/api/v1/contracts"),
        ("get", "/api/v1/jobs/{}/capsule"),
        ("get", "/api/v1/jobs/{}/matrix"),
        ("get", "/auth/oidc/callback"),
        ("get", "/auth/oidc/login"),
        ("get", "/jobs/{}/progress"),
        ("post", "/api/v1/admin/certificates/revoke"),
        ("post", "/auth/logout"),
        ("post", "/jobs/{}/cancel"),
        ("post", "/webhooks/github"),
    }
)

#: Keys a paired route publishes that the frontend type does not name. Extra payload
#: does not break JavaScript, so these are not failures — they are the drift a reader
#: would otherwise never see, and a new one means a route started answering with
#: something nobody wrote down a reason for.
ROSTERED_EXTRA_KEYS: dict[Key, frozenset[str]] = {
    ("get", "/agent/jobs"): frozenset({"next_offset"}),
    ("get", "/api/v1/admin/audit"): frozenset({"total"}),
    ("get", "/api/v1/jobs/{}/findings"): frozenset({"sources"}),
    ("get", "/jobs"): frozenset({"limit", "offset"}),
    ("get", "/jobs/{}/summary"): frozenset({"job_id"}),
    ("post", "/api/v1/demo/prepare"): frozenset({"repo"}),
    ("post", "/api/v1/model/test"): frozenset({"error_code"}),
}

#: Paired routes whose published keys cannot be folded, each with a reason that has to
#: point at code. Registering an entry is allowed; *lying* about one is not.
UNBOUND_PAYLOADS: dict[Key, str] = {
    ("get", "/api/v1/billing/usage"): (
        "billing.py:261 returns _usage_csv(rows) -- a Response built by csv.writer, "
        "which has no key set to fold -- on the accept:text/csv path and a plain dict "
        "on line 262; the fold intersects its branches, so one unreadable answer makes "
        "the whole endpoint unbounded even though the JSON half is readable"
    ),
    ("get", "/api/v1/model/config"): (
        "providers.config.public_model_config answers "
        "`{field: value for field, value in cfg.items()} | {...}` -- data decides the "
        "keys, so the fold refuses to guess them"
    ),
    ("post", "/api/v1/model/config"): (
        "the handler returns save_model_config(data), which ends in "
        "`return public_model_config()` -- the same data-decided key set as the GET "
        "route, so neither half of the model panel can be folded from here"
    ),
}

#: Pairs whose fold merged a mutation that runs only on some control paths. This is
#: the rule's known blind spot, carried as a number rather than as a claim.
CONDITIONAL_KEYS: dict[Key, frozenset[str]] = {
    ("get", "/api/v1/jobs/{}/certificate"): frozenset({"signed_path", "signed_statement"}),
    ("post", "/api/v1/model/test"): frozenset({"error_code", "message", "ok", "usage"}),
}

#: Call sites that paired only after dropping a trailing-variable reading: the suffix
#: is a query string, which is a fact about the calling file rather than something the
#: shape of the call proves. A third entry sat here when #544 first landed the
#: whitespace rule -- `GET /agent/jobs/{}/approvals` -- and the B6a arm showed it was
#: never a query string: that call closes its paren on its own line, so the newline
#: after the last literal folded into a `{}` slot the loose reading talked its way out
#: of. Stripping both ends of the argument took the entry away, which is the register
#: doing its job: the artifact had a name, and the name went missing when the artifact
#: did.
LOOSE_PAIRINGS: frozenset[Key] = frozenset(
    {("get", "/agent/jobs"), ("get", "/api/v1/admin/users")}
)

#: Sites that reach no route at all. Empty is the claim: every path the browser asks
#: for exists on the backend.
ORPHANED_CALL_SITES: frozenset[tuple[str, str, str]] = frozenset()

#: Mentions of an api client that the definition guard rejects, counted per (file, name).
#: These three are the client functions themselves; a fourth entry is either a consumer
#: the guard swallowed again or a client that stopped looking like a definition.
CLIENT_DEFINITIONS: dict[tuple[str, str], int] = {
    ("apps/web/src/api.ts", "apiGet"): 1,
    ("apps/web/src/api.ts", "apiPost"): 1,
    ("apps/web/src/api.ts", "apiDelete"): 1,
}

#: Call sites with no readable declared type. Login's probe discards the response, so
#: "no type" is the honest description of it; a new entry is a consumer that stopped
#: saying what it expects.
UNTYPED_SITES: frozenset[tuple[str, str]] = frozenset(
    {("apps/web/src/pages/Login.tsx", "/api/v1/dashboard")}
)

#: The hosts an `export interface`-only lens cannot see. If the owner narrows back to
#: ``api.ts``, the model panel's two pairs vanish from the census silently.
PRIVATE_DECLARATION_HOSTS: dict[str, str] = {
    "ModelConfig": "apps/web/src/agent/pages/AgentSettings.tsx",
    "ConnectionResult": "apps/web/src/agent/pages/AgentSettings.tsx",
}

#: Pairs that only exist because those private declarations are read.
PRIVATE_INTERFACE_PAIRS: frozenset[Key] = frozenset(
    {("get", "/api/v1/model/config"), ("post", "/api/v1/model/test")}
)

#: Every same-file path alias the fold trusts: (file, name) -> (folded path, sites it
#: shaped). This is the first reading in the owner that *rewrites* another file's code
#: into a path, so it is rostered in both directions: `api.ts`'s `path` is listed with
#: `0` sites because it feeds a `doFetch` call that is not a typed client -- an alias the
#: ruler believes in and nobody consumes is exactly the thing a reader would otherwise
#: have to re-derive by hand.
PATH_ALIASES: dict[tuple[str, str], tuple[str, int]] = {
    ("apps/web/src/api.ts", "path"): ("/api/v1/jobs/{}/capsule", 0),
    ("apps/web/src/pages/Audit.tsx", "query"): ("/api/v1/admin/audit?limit=", 1),
    ("apps/web/src/pages/JobDetail.tsx", "artifactPath"): ("/api/v1/jobs/{}", 2),
    ("apps/web/src/pages/JobDetail.tsx", "jobPath"): ("/jobs/{}", 2),
}

#: Names the alias reading refused because the same name is given a string literal more
#: than once in one file. Empty is the claim: no alias on this tree is ambiguous, so the
#: refusal rule costs nothing today and still says so when it starts costing something.
PATH_ALIAS_REFUSALS: frozenset[tuple[str, str]] = frozenset()

# Floors, not equalities: other lanes move this tree under us, and a census that fails
# because a legitimate route was added gets widened by whoever is reddest. The
# two-sided legs are what catch a real drop.
_MIN_ENDPOINTS = 50
#: Measured at #544's landing: 40 endpoints paired and 45 sites read, after the two
#: consumer-reading rules. The margin is the churn the frontend has actually shown while
#: this campaign ran (a lane adding a page is fine; a lane losing seven of forty-five
#: consumers is the drop these floors are for).
_MIN_PAIRED_ENDPOINTS = 34
_MIN_CALL_SITES = 38
_MIN_DECLARATION_HOSTS = 30
_MIN_API_TS_DECLARATIONS = 45
#: Measured 10 on this tree: product sites whose call is written as
#: `const data = await apiGet<X>(...)`, which the first version of the guard threw away.
_MIN_SITES_BEHIND_A_DECLARATION = 8
#: Measured 5 at #544's landing: census sites whose path arrived through a same-file
#: alias. One short of the measurement, because `api.ts`'s `path` is expected to stay at
#: zero and the floor is about the reading still reaching real callers.
_MIN_ALIAS_SHAPED_SITES = 4


def _census() -> tuple[list[Endpoint], list[Pair], list[CallSite], Declarations]:
    pairs, orphans = pairings(REPO)
    declarations = ts_declarations(web_src(REPO))
    return endpoints(REPO), pairs, orphans, declarations


def _checked_pairs(
    pairs: list[Pair], declarations: Declarations
) -> list[tuple[Pair, set[str], set[str]]]:
    """Pairs where both sides of the contract have a readable shape.

    A site with no declared type and a route with no foldable payload are not silence
    here: they are counted by their own legs and registers, so this helper only says
    which pairs can be *compared*.
    """
    out = []
    for pair in pairs:
        required, optional, notes = members_of_type(pair.site.type_expr, declarations)
        if notes or not (required or optional):
            continue
        payload = payload_of(REPO, pair.endpoint)
        if payload.unbounded:
            continue
        out.append((pair, required, optional))
    return out


def test_the_census_measures_a_population_rather_than_a_sample() -> None:
    """Every side of the plane has a floor, and the exclusion stays a minority."""
    endpoint_table, pairs, _orphans, declarations = _census()
    call_sites, excluded_test_sites = frontend_calls(web_src(REPO))
    hosts = {host for _name, (host, _members) in declarations.items()}
    api_ts = sum(1 for _n, (host, _m) in declarations.items() if host == API_TS)
    paired_endpoints = {_pair_key(pair) for pair in pairs}

    assert len(endpoint_table) >= _MIN_ENDPOINTS, (
        f"only {len(endpoint_table)} routes derived from api/: the owner stopped seeing "
        "a router, which is how a census quietly becomes a sample"
    )
    assert len(call_sites) >= _MIN_CALL_SITES, f"only {len(call_sites)} call sites read"
    assert len(paired_endpoints) >= _MIN_PAIRED_ENDPOINTS, f"only {len(paired_endpoints)} paired"
    assert len(hosts) >= _MIN_DECLARATION_HOSTS, (
        f"declarations read from only {len(hosts)} files: the owner is narrowing again"
    )
    assert api_ts >= _MIN_API_TS_DECLARATIONS, f"{API_TS} contributed only {api_ts} declarations"
    assert excluded_test_sites < len(call_sites), (
        f"{excluded_test_sites} sites excluded as test files against {len(call_sites)} "
        "counted: the exclusion has become the population"
    )


_DECLARATION = re.compile(r"\b(?:function|const|let|var)\b")


def _declares_on_the_line(shape: CallShape) -> bool:
    """The rejected mention's own line declares the client, instead of calling it.

    Evidence from outside the guard: the guard decides by looking left, so a leg that
    re-derived the same rule would only repeat it. `const data = await apiGet<X>(...)`
    starts its line with a *different* name, which is what the unanchored reading
    mistook for a declaration.
    """
    text = (REPO / shape.file).read_text(encoding="utf-8").splitlines()
    line = text[shape.line - 1].lstrip()
    return (
        re.match(rf"(?:export\s+)?(?:async\s+)?(?:function|const|let|var)\s+{shape.name}\b", line)
        is not None
    )


def test_the_definition_guard_rejects_only_definitions() -> None:
    """A consumer wearing a declaration's clothes is how a route looks unconsumed.

    The guard used to read "`function `/`const ` anywhere in the 40 characters to the
    left", which is also true of `const data = await apiGet<X>(...)` -- a call. Ten
    product sites are written that way, and the A12 arm measured what the unanchored rule
    cost on this tree: five of the ten were thrown away, and four of those five were their
    endpoint's only consumer -- including `POST /api/v1/model/config`, whose declared type
    is the model panel's whole contract. The A8 arm fell over it by accident while
    planting a synthetic hole.
    """
    shapes = call_shapes(web_src(REPO))
    found: dict[tuple[str, str], int] = {}
    for shape in (s for s in shapes if not s.is_call):
        found[(shape.file, shape.name)] = found.get((shape.file, shape.name), 0) + 1
        assert _declares_on_the_line(shape), (
            f"{shape.file}:{shape.line} rejects a {shape.name} that its own line does not declare"
        )
    assert found == CLIENT_DEFINITIONS, f"definition rejections drifted: {found}"

    behind = [s for s in shapes if s.is_call and _DECLARATION.search(s.window)]
    assert len(behind) >= _MIN_SITES_BEHIND_A_DECLARATION, (
        f"only {len(behind)} consumer sites sit behind a declaration keyword: an unanchored "
        "guard would be swallowing them again, and that would surface as stale registers "
        "rather than as a hole in a payload"
    )


def test_every_route_without_a_frontend_consumer_is_rostered_by_name() -> None:
    """The unpaired side is measured, in both directions.

    A register entry that is no longer unpaired is stale — somebody wired the
    frontend and left the register claiming nobody reads it — and an unpaired route
    missing from the register is a payload contract with no declared consumer.
    """
    endpoint_table, pairs, _orphans, _declarations = _census()
    unpaired = {_endpoint_key(e) for e in endpoint_table} - {_pair_key(p) for p in pairs}
    assert unpaired == UNPAIRED_ENDPOINTS, (
        f"newly unpaired={sorted(unpaired - UNPAIRED_ENDPOINTS)} "
        f"no longer unpaired={sorted(UNPAIRED_ENDPOINTS - unpaired)}"
    )


def test_every_frontend_call_site_reaches_a_route() -> None:
    """No site asks for a path that does not exist.

    An orphan is a request that 404s for a user right now, and it survives review
    because the path is built from a variable a reader cannot see through. Rostered,
    and the register is empty on purpose.
    """
    _endpoints, _pairs, orphans, _declarations = _census()
    found = {(site.verb, site.candidates[0], site.file) for site in orphans}
    assert found == ORPHANED_CALL_SITES, f"call sites that reach nothing: {sorted(found)}"


def test_a_required_key_is_published_by_every_return_branch() -> None:
    """The #542 rule, on every paired endpoint instead of on one.

    A route that answers key set A on the happy path and B on the degraded path does
    not publish A ∪ B — the browser gets whichever it got — so the set that matters is
    the intersection, and a required key missing from any branch is a hole the page
    renders as a zero, an empty string, or a missing card.
    """
    _endpoints, pairs, _orphans, declarations = _census()
    holes: list[str] = []
    for pair, required, _optional in _checked_pairs(pairs, declarations):
        missing = required - payload_of(REPO, pair.endpoint).always
        if missing:
            holes.append(
                f"{pair.endpoint.verb.upper()} {pair.endpoint.path} declared at "
                f"{pair.site.file}:{pair.site.line} misses {sorted(missing)} "
                f"in at least one branch"
            )
    assert not holes, "\n".join(holes)


def test_published_keys_the_frontend_never_declared_are_rostered() -> None:
    """Extra keys are drift with a name, not noise to be widened away."""
    _endpoints, pairs, _orphans, declarations = _census()
    found: dict[Key, set[str]] = {}
    for pair, required, optional in _checked_pairs(pairs, declarations):
        extra = payload_of(REPO, pair.endpoint).published - required - optional
        if extra:
            found.setdefault(_pair_key(pair), set()).update(extra)
    expected = {key: set(value) for key, value in ROSTERED_EXTRA_KEYS.items()}
    new = {key: sorted(value - expected.get(key, set())) for key, value in found.items()}
    gone = {key: sorted(value - found.get(key, set())) for key, value in expected.items()}
    assert not [entry for entry in new.values() if entry], f"undeclared extras appeared: {new}"
    assert not [entry for entry in gone.values() if entry], (
        f"the register still names extras this route no longer publishes: {gone}"
    )


def test_the_unbound_register_names_the_routes_that_cannot_be_folded_and_does_not_lie() -> None:
    """Register-not-lying, the ``test_sql_text_static.py`` shape.

    Three ways to fail: a route that is unbounded but unregistered, a registered entry
    that folded successfully in this tree (stale), and a registered reason that points
    at nothing — the last one is what turns a register into a place to hide a hole.
    """
    endpoint_table, pairs, _orphans, _declarations = _census()
    by_key: dict[Key, Endpoint] = {}
    for pair in pairs:
        by_key.setdefault(_pair_key(pair), pair.endpoint)
    unbounded = {
        key: payload_of(REPO, endpoint).unbounded
        for key, endpoint in by_key.items()
        if payload_of(REPO, endpoint).unbounded
    }
    assert set(unbounded) == set(UNBOUND_PAYLOADS), (
        f"unregistered={sorted(set(unbounded) - set(UNBOUND_PAYLOADS))} "
        f"stale={sorted(set(UNBOUND_PAYLOADS) - set(unbounded))}"
    )
    for key, reasons in unbounded.items():
        reason = UNBOUND_PAYLOADS[key]
        assert reason.strip(), f"{key} is registered with an empty reason"
        cited = _identifiers(reason) & _identifiers(" ".join(reasons))
        assert cited, (
            f"the registered reason for {key} names nothing that the fold actually "
            f"refused: {reasons}"
        )
        handler_text = _handler_source(key, endpoint_table)
        assert _identifiers(reason) & _identifiers(handler_text), (
            f"the registered reason for {key} cannot be pointed at in its handler: {reason!r}"
        )


def test_the_private_page_interfaces_really_are_in_the_census() -> None:
    """A declaration read from a page has to reach the comparison, not just the parser.

    ``ModelConfig`` / ``ConnectionResult`` have no ``export``. Reading them is the only
    reason the model panel's two pairs exist as pairs, so the leg checks the host *and*
    that the pairs those types describe are in the census.
    """
    _endpoints, pairs, _orphans, declarations = _census()
    for name, host in PRIVATE_DECLARATION_HOSTS.items():
        assert name in declarations, f"{name} is invisible to the owner: the lens narrowed"
        assert declarations[name][0] == host, (
            f"{name} is declared in {declarations[name][0]!r}, not {host!r}"
        )
        assert host != API_TS, f"{name} was expected outside {API_TS}"
    paired = {_pair_key(pair) for pair in pairs}
    assert paired >= PRIVATE_INTERFACE_PAIRS, sorted(PRIVATE_INTERFACE_PAIRS - paired)
    typed_by = {pair.site.typed_by for pair in pairs}
    assert "return-annotation" in typed_by, (
        "no pair is typed by its enclosing function's Promise<T>: the untyped-site "
        "reading was dropped, so POST /jobs left the census silently"
    )


def test_the_conditional_register_is_measured_not_recited() -> None:
    """The fold's one known overstatement carries a number.

    Merging every mutation makes a key attached only inside an ``if`` look
    always-present, which is why the per-branch rule above is weaker than it reads.
    The register names the pairs affected and the keys involved; the leg recomputes it,
    so the blind spot cannot grow quietly and cannot be mistaken for coverage.
    """
    _endpoints, pairs, _orphans, _declarations = _census()
    by_key: dict[Key, Endpoint] = {}
    for pair in pairs:
        by_key.setdefault(_pair_key(pair), pair.endpoint)
    found = {
        key: set(payload_of(REPO, endpoint).conditional)
        for key, endpoint in by_key.items()
        if payload_of(REPO, endpoint).conditional
    }
    expected = {key: set(value) for key, value in CONDITIONAL_KEYS.items()}
    assert found == expected, (
        f"conditional keys drifted: new={sorted(set(found) - set(expected))} "
        f"stale={sorted(set(expected) - set(found))}"
    )


def test_loose_pairings_are_rostered() -> None:
    """A pairing that needed the trailing-variable reading is named.

    ``"/api/v1/admin/users" + q`` pairs with the list route because that suffix is a
    query string. If a future site's variable is really a missing path segment, the
    loose reading invents a contract, so the roster keeps the reading countable.
    """
    _endpoints, pairs, _orphans, _declarations = _census()
    loose = {_pair_key(pair) for pair in pairs if not pair.exact}
    assert loose == LOOSE_PAIRINGS, f"loose pairings drifted: {sorted(loose)}"


def test_sites_with_no_readable_declared_type_are_rostered() -> None:
    """Untyped consumers are counted, not skipped.

    ``apiGet("/api/v1/dashboard")`` in the login probe discards the response, so there
    is no declared shape to compare — but "no type" has to be a measured fact about a
    named site, not a silent ``continue`` in the comparison leg.
    """
    _endpoints, pairs, _orphans, _declarations = _census()
    found = {
        (pair.site.file, normalize_path(pair.site.path))
        for pair in pairs
        if pair.site.typed_by == "none"
    }
    assert found == UNTYPED_SITES, f"untyped call sites drifted: {sorted(found)}"


def test_the_path_aliases_the_fold_rewrites_are_rostered_whole() -> None:
    """The reading that rewrites another file's code into a path is named, both ways.

    ``apiGet<AuditResponse>(query)`` and the three JobDetail calls built from `jobPath`
    / `artifactPath` reach the census only because a same-file `const` was substituted
    into the argument. That is the owner's one rule that invents text where the tree has
    an identifier, so it is rostered as a table rather than trusted: a new alias is a
    red leg, an alias whose folded path moved is a red leg, and an alias the census
    never consumes -- `api.ts`'s `path`, which feeds a `doFetch` call that is not a typed
    client -- stays on the register with a zero instead of quietly disappearing.

    The transitive reading is what keeps `artifactPath` honest. Fold each declaration
    once and `const artifactPath = "/api/v1" + jobPath` reads as `/api/v1{}`, which
    pairs against nothing. The R2 rehearsal (registers left as #543 wrote them) caught
    that as two orphan sites inside six red legs; the B2 arm re-ran it against this
    register and caught it on three -- the orphan leg and this one are the same claim
    twice, which is why a non-transitive fold cannot hide behind a stale roster.
    """
    rows, refused = alias_table(web_src(REPO))
    found = {(file, name): (path, sites) for file, name, path, sites in rows}
    added = sorted(set(found) - set(PATH_ALIASES))
    removed = sorted(set(PATH_ALIASES) - set(found))
    moved = sorted(
        (key, found[key], PATH_ALIASES[key])
        for key in set(found) & set(PATH_ALIASES)
        if found[key] != PATH_ALIASES[key]
    )
    assert not added and not removed and not moved, (
        f"alias table drifted: new={added} gone={removed} changed={moved}"
    )
    assert set(refused) == PATH_ALIAS_REFUSALS, f"ambiguous alias names appeared: {sorted(refused)}"
    shaped = sum(sites for _path, sites in found.values())
    assert shaped >= _MIN_ALIAS_SHAPED_SITES, (
        f"only {shaped} census sites came through an alias: the reading has stopped "
        "earning the population it claims"
    )


def _identifiers(text: str) -> set[str]:
    return set(re.findall(r"\b[A-Za-z_][A-Za-z0-9_]{2,}\b", text))


def _handler_source(key: Key, endpoint_table: list[Endpoint]) -> str:
    for endpoint in endpoint_table:
        if _endpoint_key(endpoint) == key:
            module = REPO / (endpoint.module.replace(".", "/") + ".py")
            return module.read_text(encoding="utf-8")
    raise AssertionError(f"{key} is not an endpoint in the table")

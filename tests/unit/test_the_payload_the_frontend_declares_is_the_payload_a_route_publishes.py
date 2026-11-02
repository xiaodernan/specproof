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

* the 13 endpoints with no typed frontend consumer. They are rostered by name, not
  folded: there is no declared shape to compare against, so a payload census there would
  be an assertion with only one side.
* keys a handler attaches only inside one ``if`` arm. The fold merges every
  ``name.update(...)`` / ``name["k"] = ...`` into the handler's branches, so such a key
  reads as always-present. ``CONDITIONAL_KEYS`` names exactly which keys that covers.
* runtime truth. Nothing here makes a request; a route that answers through a shape the
  fold cannot see stays in ``UNBOUND_PAYLOADS`` with a reason that has to point at code.

#546 widened the consumer side twice more. **E6** reads a typed hook that is not an api
client: ``apps/web/src/hooks/useRemoteData.ts`` declares ``<T>``, hands ``T`` to the one
``apiGet`` in its own body, and is therefore a consumer -- but the verb is read from the
body, never taken from the name, which is why ``HOOK_CONSUMERS`` is a leg instead of a
table. **E7** reads the branch of a conditional argument:
``useRemoteData<MatrixData>(jobId ? "/api/v1/jobs/" + id + "/matrix" : null)`` is one
request whose path is chosen at runtime. The `?` of a ternary and the `?` that opens a
query string are the same character, so E7 splits on a copy with its literals masked --
the naive version measured a *loss* (47 sites read as 46, the contracts page back in the
roster, `/agent/jobs` unpaired again). Both readings rewrite or re-classify code that
belongs to other files, so both are rostered whole: ``PATH_CONDITIONALS`` and
``HOOK_CONSUMERS`` carry what the ruler believed, and their legs recompute it.

#547 stopped the fold and gave the ruler a mirror. **F1** refuses a depth-0 chooser:
``"/api/v1/x?q" === q ? "/api/v1/a" : null`` used to fold into ``/api/v1/x?q{}/api/v1/a{}``
-- a path-shaped string no caller wrote, kept because it started with `/`, and therefore
never offered to the conditional reading. It now hands the argument to E7, and when E7 has
no path either, ``RULER_BLIND_SPOTS`` carries a row instead of the census carrying a
fabrication. **The mirror** is that same exit for the shapes the ruler recognizes and does
not read: three ``use*`` declarations whose return annotation swallowed their bodies, the
conditional arm E7 reads only one layer into, and the hook spellings -- ``const useX = () =>``,
``async function useX`` -- that ``_HOOK_DEF`` cannot see. Four of the five have population
zero on this tree and the fifth holds three rows that cost nothing, because none of those
three hooks issues a request. No reading was built for any of them: ⓮'s verdict, applied
from the inside this time. What the register is for is that ``0`` is a measurement, not an
assumption -- a leg recomputes it, and the columns ``seen``/``read`` say which rows would
hurt if the tree grew.

#548 read the third direction and built the floor under it. **Axis (c)** answers what a
key the frontend marks optional really is: ``always`` (every branch publishes it, and the
branch list is all the handler's exits), ``overstated`` (in that set only because
``Payload.conditional`` merged it in), ``sometimes`` (some branches and not others --
population 0 today, and an arm says the zero is a measurement), ``absent`` (no branch
publishes it and nothing merged it). Five endpoints have anything to say, 8 + 3 + 0 + 2 keys
between them, and the row that matters is ``/jobs``: ``api.ts`` records in prose why
``JobsPage.total`` must be required, while ``Guide.tsx`` still writes ``total?: number``.
**The fuse** is ``return_accounting``: 42 speakable endpoints, their own ``return`` count
against the branches the fold reported, and the three rows that disagree are exactly the
three the fold already named in ``UNBOUND_PAYLOADS``. Without it the ``always`` above is
``set.intersection`` over whatever branch list the fold happened to build -- an intersection
is a proof only over every exit, and an early bare ``return`` would turn every ``always``
number in this plane into a partial read that prints as a guarantee. Population 0 on this
tree, so the leg carries a fixture whose counts are (2, 1) and unreported, which is what
makes the fuse a fuse rather than a comment.

#549 wrote down who reads what. **The read map** is derived from this file's own source: for
every name it imports from the plane, which legs execute it, which name it only in an
annotation, how many legs reach it through a helper of this file, and which import is used at
module level by nothing that runs (one: ``Member``). 31 + 3 + 85 relations, and the number the
last two misses were about is ``EXITS_WITH_MULTIPLE_EXECUTORS``: seven exits have more than one
executor, including the two that made predictions wrong -- ``optional_publish_bands`` (#548 arm
E7 reddened two legs where the frozen prediction named one) and ``ruler_blind_spots`` (#547 arm
D5, the same shape reached through two fixtures). **A second lens** rescans each leg's own lines
with strings and comments tokenized away and agrees leg by leg over 34 direct relations, because
a register checked only by the parser that fills it has one witness. What it does not buy: arm
G7 replaced the derivation with the frozen table and all 24 legs stayed green, so the map's
honesty lives in the step that generates the register, not in the legs that read it.

#550 put a guard on that step and gave the hop its own witness. **The ban** reads the
generator's body from the tree: ``_read_map`` may name one uppercase binding (``REPO``, the
root) and no helper in this file may name an uppercase binding outside the three anchors --
so arm G7's ``return ReadMap(...)`` is now red instead of green, and the population that
would have made a blanket ban impossible is a roster, not an excuse. **The second lens over
``via``** walks each leg's helper closure, rescans those helpers' lines with strings and
comments tokenized away, and must *equal* the generator's set on all 26 legs and 85
relations: the column that had one witness now has two, and the 14 legs whose hop comes back
empty are named, because two empty sets agree for the wrong reason just as easily.
"""

from __future__ import annotations

import ast
import io
import re
import sys
import textwrap
import tokenize
from collections import Counter
from pathlib import Path
from typing import NamedTuple

_PROJECT_ROOT = Path(__file__).resolve().parents[2]
if str(_PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(_PROJECT_ROOT))

from tests._payload_plane import (  # noqa: E402
    CallShape,
    CallSite,
    Endpoint,
    Member,
    OptionalBand,
    Pair,
    alias_table,
    call_shapes,
    conditional_table,
    endpoints,
    frontend_calls,
    hook_readings,
    members_of_type,
    normalize_path,
    optional_publish_bands,
    pairings,
    payload_of,
    return_accounting,
    ruler_blind_spots,
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
#: #546 took two more: `GET /api/v1/contracts` (a page that reads through a typed hook,
#: E6) and `GET /api/v1/jobs/{id}/matrix` (the same, through an argument that is a
#: conditional, E7). Neither route changed; only the ruler's eye did, which is the whole
#: argument for rostering both readings instead of trusting them.
UNPAIRED_ENDPOINTS: frozenset[Key] = frozenset(
    {
        ("get", "/agent/jobs/{}/event-history"),
        ("get", "/agent/jobs/{}/events"),
        ("get", "/api/v1/admin/certificates/revocations"),
        ("get", "/api/v1/billing/jobs/{}"),
        ("get", "/api/v1/billing/subscriptions"),
        ("get", "/api/v1/jobs/{}/capsule"),
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
#: `/jobs` gained `total` at #546 without the route changing: the third consumer of that
#: endpoint is `Matrix.tsx`'s inline `{ jobs: Job[] }`, which asks for less than the page
#: that has always been its witness. That is what this register is for -- a widening on
#: the consumer side can *increase* the drift, and the drift is real either way.
ROSTERED_EXTRA_KEYS: dict[Key, frozenset[str]] = {
    ("get", "/agent/jobs"): frozenset({"next_offset"}),
    ("get", "/api/v1/admin/audit"): frozenset({"total"}),
    ("get", "/api/v1/jobs/{}/findings"): frozenset({"sources"}),
    ("get", "/jobs"): frozenset({"limit", "offset", "total"}),
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

#: Mentions of a consumer that the definition guard rejects, counted per (file, name).
#: The three `api.ts` entries are the client functions themselves; the two hooks joined
#: the list at #546 when E6 made a hook name call-shaped, and a hook's own
#: `export function` line is exactly the thing the guard must still refuse. A new entry
#: is either a consumer the guard swallowed again or a client that stopped looking like a
#: definition.
CLIENT_DEFINITIONS: dict[tuple[str, str], int] = {
    ("apps/web/src/agent/components.tsx", "useAgentJob"): 1,
    ("apps/web/src/api.ts", "apiGet"): 1,
    ("apps/web/src/api.ts", "apiPost"): 1,
    ("apps/web/src/api.ts", "apiDelete"): 1,
    ("apps/web/src/hooks/useRemoteData.ts", "useRemoteData"): 1,
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

#: Every hook the census reads as a consumer: name -> (verb, file, sites read through it).
#: E6's claim is that a hook qualifies because of what its *body* does, so this register
#: is recomputed from the body and the verb is the measured one -- `useAgentJob` is here
#: with `0` sites for the same reason `api.ts`'s `path` is in the alias table with `0`:
#: the ruler believes in it, its own call sites hand it a variable instead of a path, and
#: a reader deserves to see that rather than re-derive it.
HOOK_CONSUMERS: dict[str, tuple[str, str, int]] = {
    "useAgentJob": ("get", "apps/web/src/agent/components.tsx", 0),
    "useRemoteData": ("get", "apps/web/src/hooks/useRemoteData.ts", 3),
}

#: Hooks that issue more than one client request, so no single verb can be attributed to
#: their type argument and the census refuses them. Empty is the claim on this tree.
HOOK_REFUSALS: frozenset[str] = frozenset()

#: Every conditional argument E7 folded into one path: (file, line) -> (path, branch as
#: written). The branch text is part of the register because this reading replaces an
#: expression that belongs to a page: a reader has to be able to see *which* arm the
#: census chose, and the choice is only sound while exactly one arm is a path.
PATH_CONDITIONALS: dict[tuple[str, int], tuple[str, str]] = {
    ("apps/web/src/pages/Matrix.tsx", 22): (
        "/api/v1/jobs/{}/matrix",
        '"/api/v1/jobs/" + encodeURIComponent(jobId) + "/matrix"',
    ),
}

#: Arguments with two path-shaped arms, which the fold refuses instead of choosing.
#: Empty is the claim: no call on this tree makes the census guess between endpoints.
PATH_CONDITIONAL_REFUSALS: frozenset[tuple[str, int]] = frozenset()

#: Shapes the frontend has, that the ruler sees, and that no reading consumes:
#: ``(shape, file, line)`` -> (name, verbs held, verbs taken). #547's other registers say
#: what the census believed; this one says where the census is blind, and it exists because
#: the alternative -- building a reading for a shape whose population is zero -- would put
#: an untested rule inside the ruler. The three rows here are `use*` declarations with a
#: brace-bearing return annotation, which `_function_body` takes for the body; all three
#: hold no request, so `seen` and `read` agree. The day one of them starts fetching, this
#: register's row changes text and the leg goes red -- which is the whole point: the blind
#: spot has a number attached to it rather than a paragraph.
RULER_BLIND_SPOTS: dict[tuple[str, str, int], tuple[str, tuple[str, ...], tuple[str, ...]]] = {
    ("annotation-swallowed-body", "apps/web/src/identity/useIdentityAccess.ts", 10): (
        "useIdentityAccess",
        (),
        (),
    ),
    ("annotation-swallowed-body", "apps/web/src/pages/Audit.tsx", 59): (
        "useAuditAccess",
        (),
        (),
    ),
    ("annotation-swallowed-body", "apps/web/src/pages/Billing.tsx", 132): (
        "useBillingAccess",
        (),
        (),
    ),
}

#: The rows above where the two tuples disagree: consumers or sites the census actually
#: lost. Empty is the claim on this tree, and it is the assertion that keeps
#: ``RULER_BLIND_SPOTS`` honest -- a shape nobody reads is a note, while a shape nobody
#: reads *and* someone is waiting on is a hole.
RULER_BLIND_SPOT_VICTIMS: frozenset[tuple[str, str, int]] = frozenset()

# ---------------------------------------------------------------------------
# #548 -- axis (c), and the fuse that makes its intersection a proof

#: Axis (c): what a key the frontend declares *optional* actually is. ``(verb, path)``
#: -> ((declaring file, line), {band: keys}), empty bands left out. Five rows. Three of
#: them say a page is defending against something it does not need to; one (`/jobs`) says
#: a page has not been told about a decision ``api.ts`` already wrote down in prose; and
#: health's two ``absent`` keys say the page defends against a key that cannot arrive.
AXIS_C_BANDS: dict[Key, tuple[tuple[str, int], dict[str, tuple[str, ...]]]] = {
    ("get", "/api/v1/health"): (
        ("apps/web/src/pages/Health.tsx", 78),
        {
            "always": ("checks", "degraded", "status"),
            "absent": ("capabilities", "degraded_reasons"),
        },
    ),
    ("get", "/api/v1/jobs/{}/certificate"): (
        ("apps/web/src/pages/JobDetail.tsx", 290),
        {"overstated": ("signed_path", "signed_statement")},
    ),
    ("get", "/api/v1/jobs/{}/matrix"): (
        ("apps/web/src/pages/Matrix.tsx", 22),
        {"always": ("counts_source", "rows_total", "rows_truncated", "sources")},
    ),
    ("get", "/jobs"): (
        ("apps/web/src/pages/Guide.tsx", 74),
        {"always": ("total",)},
    ),
    ("post", "/api/v1/model/test"): (
        ("apps/web/src/agent/pages/AgentSettings.tsx", 91),
        {"overstated": ("usage",)},
    ),
}

#: The same register summed, because a row comparison alone cannot see keys moving
#: *between* bands on a route that keeps speaking: ``always`` 8 -> 11 and ``overstated``
#: 3 -> 0 is one line in the owner (arm E2) and leaves all five rows standing.
AXIS_C_KEY_TOTALS: dict[str, int] = {
    "always": 8,
    "overstated": 3,
    "sometimes": 0,
    "absent": 2,
}

#: How many endpoints the axis can speak about: the 42 the fuse registers, minus the 3 the
#: fold refused to bound. A row vanishing from ``AXIS_C_BANDS`` and this count *not* moving
#: is a route whose reading went quiet; both moving is a route leaving the plane.
_AXIS_C_ROW_COUNT = 39

#: Which paired endpoints publish the two keys health declares optional. This is the
#: evidence that health's ``absent`` row is a reading and not blindness: the ruler sees
#: ``degraded_reasons`` well enough to report it on both of the dashboard's branches, and
#: ``capabilities`` reaches no bounded payload anywhere in the repo. Registering it here
#: also means the day a route starts answering ``capabilities`` moves a number, instead of
#: turning this band into a definition nobody may touch.
AXIS_C_ABSENT_PUBLISHERS: dict[str, tuple[Key, ...]] = {
    "capabilities": (),
    "degraded_reasons": (("get", "/api/v1/dashboard"),),
}

#: The fuse: ``(returns in the handler's own scope, branches the fold reported)`` -> how
#: many of the 42 speakable endpoints have that shape. The (1, 1) block is the part of this
#: plane that is a proof; (2, 1) and (1, 0) are partial reads, tolerable only because the
#: fold *said* so. A fifth key appearing here means the fold started disagreeing with a
#: handler quietly, and every ``always`` set above is then an intersection over a list that
#: is not the census.
RETURN_ACCOUNT_DISTRIBUTION: dict[tuple[int, int], int] = {
    (1, 1): 37,
    (2, 2): 2,
    (2, 1): 1,
    (1, 0): 2,
}

#: The rows where the two counts disagree: ``(verb, path)`` -> (own returns, branches).
#: Each must also stand in ``UNBOUND_PAYLOADS``, because "the fold refused this return"
#: and "the fold did not see this return" are the same pair of numbers and only one of
#: them is honest.
RETURN_ACCOUNT_MISMATCHES: dict[Key, tuple[int, int]] = {
    ("get", "/api/v1/billing/usage"): (2, 1),
    ("get", "/api/v1/model/config"): (1, 0),
    ("post", "/api/v1/model/config"): (1, 0),
}

# ---------------------------------------------------------------------------
# #549 -- the read map: which leg reads which exit, derived from this file's own source
#
# Two prediction misses in a row had the same cause, and neither was bad reasoning: #547's arm
# D5 reddened two legs where one was predicted, and #548's arm E7 reddened two legs where one
# was predicted, because ``optional_publish_bands`` has two executors and "which legs read this
# exit" lived only in the table printed *after* the arms ran. So the map is now derived inside
# the gate, from this file's syntax tree, and four legs read it.
#
# Three relations, plus one that is not a leg at all:
#   executed   -- the name occurs in the leg's own statements, not only in an annotation;
#   annotated  -- the name occurs only inside an annotation subtree of that leg;
#   via-helper -- the leg does neither, but a helper of this file it reaches does;
#   alias-only -- module level only (a type alias), read by no leg, and invisible to ruff
#                 because the import genuinely is used -- just never by a test.
#
# A second lens over the same fact reads the *text* of each leg's line span with strings and
# comments tokenized away. The two agree leg by leg, which is what keeps a recited register
# from passing as a measurement: the AST lens alone could be stubbed into agreeing with itself.


#: One row per name this file imports from the owner: the legs that execute it, the legs
#: that only name it in an annotation, and how many legs reach it through a helper of this
#: file. ``_read_map`` produces it; ``test_the_exit_read_map_is_measured_not_recited``
#: recomputes it, so an edit that moves a call without moving a number is impossible here.
EXIT_READS: dict[str, tuple[tuple[str, ...], tuple[str, ...], int]] = {
    "CallShape": ((), (), 1),
    "CallSite": ((), (), 11),
    "Endpoint": (
        (),
        (
            "test_an_optional_key_is_rostered_in_the_band_the_route_puts_it_in",
            "test_the_conditional_register_is_measured_not_recited",
            "test_the_unbound_register_names_the_routes_that_cannot_be_folded_and_does_not_lie",
        ),
        8,
    ),
    "Member": ((), (), 0),
    "OptionalBand": ((), (), 1),
    "Pair": ((), (), 11),
    "alias_table": (("test_the_path_aliases_the_fold_rewrites_are_rostered_whole",), (), 0),
    "call_shapes": (("test_the_definition_guard_rejects_only_definitions",), (), 0),
    "conditional_table": (
        (
            "test_the_conditional_branches_the_fold_rewrites_are_rostered_whole",
            "test_the_fold_stops_where_the_caller_stopped_spelling_a_path",
            "test_the_three_conditional_guards_each_carry_their_own_case",
        ),
        (),
        0,
    ),
    "endpoints": ((), (), 11),
    "frontend_calls": (
        (
            "test_a_hook_that_issues_two_requests_is_refused_and_says_so",
            "test_the_census_measures_a_population_rather_than_a_sample",
            "test_the_conditional_branches_the_fold_rewrites_are_rostered_whole",
            "test_the_fold_stops_where_the_caller_stopped_spelling_a_path",
            "test_the_hook_consumers_are_measured_from_their_own_bodies",
            "test_the_three_conditional_guards_each_carry_their_own_case",
        ),
        (),
        0,
    ),
    "hook_readings": (
        (
            "test_a_hook_that_issues_two_requests_is_refused_and_says_so",
            "test_the_hook_consumers_are_measured_from_their_own_bodies",
        ),
        (),
        0,
    ),
    "members_of_type": ((), (), 2),
    "normalize_path": (("test_sites_with_no_readable_declared_type_are_rostered",), (), 8),
    "optional_publish_bands": (
        (
            "test_an_optional_key_is_rostered_in_the_band_the_route_puts_it_in",
            "test_the_fold_reports_every_return_the_handler_can_take",
        ),
        (),
        0,
    ),
    "pairings": ((), (), 11),
    "payload_of": (
        (
            "test_a_required_key_is_published_by_every_return_branch",
            "test_an_optional_key_is_rostered_in_the_band_the_route_puts_it_in",
            "test_published_keys_the_frontend_never_declared_are_rostered",
            "test_the_conditional_register_is_measured_not_recited",
            "test_the_unbound_register_names_the_routes_that_cannot_be_folded_and_does_not_lie",
        ),
        (),
        0,
    ),
    "return_accounting": (("test_the_fold_reports_every_return_the_handler_can_take",), (), 0),
    "ruler_blind_spots": (
        (
            "test_the_fold_stops_where_the_caller_stopped_spelling_a_path",
            "test_the_shapes_the_ruler_sees_and_does_not_read_are_rostered",
            "test_the_three_conditional_guards_each_carry_their_own_case",
        ),
        (),
        0,
    ),
    "ts_declarations": ((), (), 11),
    "web_src": (
        (
            "test_the_census_measures_a_population_rather_than_a_sample",
            "test_the_conditional_branches_the_fold_rewrites_are_rostered_whole",
            "test_the_definition_guard_rejects_only_definitions",
            "test_the_hook_consumers_are_measured_from_their_own_bodies",
            "test_the_path_aliases_the_fold_rewrites_are_rostered_whole",
            "test_the_shapes_the_ruler_sees_and_does_not_read_are_rostered",
        ),
        (),
        10,
    ),
}

#: ``(executed, annotated, via-helper)`` relation instances over the whole table. The 85
#: in the last column is the point of the register: most of this gate reads the plane
#: through ``_census`` and ``_checked_pairs``, so a map that only recorded direct calls
#: would report a gate with no helpers and lose the reads it cannot see.
_EXIT_READ_INSTANCES = (31, 3, 85)

#: The legs whose reads are all direct or annotated -- the population the cross-check
#: compares between its two lenses. A zero here would make the agreement vacuous.
_DIRECT_RELATION_INSTANCES = 34

#: Which exits more than one leg executes, and how many do it. These are the rows an arm
#: is about to red twice: #548's E7 moved ``optional_publish_bands`` and both of its
#: executors failed; #547's D5 did the same to a guard layer reached through two fixtures.
EXITS_WITH_MULTIPLE_EXECUTORS: dict[str, int] = {
    "conditional_table": 3,
    "frontend_calls": 6,
    "hook_readings": 2,
    "optional_publish_bands": 2,
    "payload_of": 5,
    "ruler_blind_spots": 3,
    "web_src": 6,
}

#: Named by the two legs that read axis (c), spelled out because the arm prediction that
#: missed was about identity, not count: a third executor is new information even when
#: ``EXITS_WITH_MULTIPLE_EXECUTORS`` still says ``>= 2``.
_AXIS_C_EXECUTORS = (
    "test_an_optional_key_is_rostered_in_the_band_the_route_puts_it_in",
    "test_the_fold_reports_every_return_the_handler_can_take",
)

#: Imports that reach no leg. ``Member`` is the only one and ruff cannot see it: the name
#: is used, in the module-level alias ``Declarations``, by nothing that runs.
EXIT_READS_ALIAS_ONLY: frozenset[str] = frozenset({"Member"})

#: Legs that never execute or annotate an owner name themselves. Four roster legs read
#: through helpers; four are #549's, which read this map rather than the plane; two are
#: #550's, which audit the map builder's own body. Registered by name because "no direct
#: read" and "no read at all" are the same zero, and the difference is only visible in
#: the helper hop.
LEGS_WITHOUT_DIRECT_READ: frozenset[str] = frozenset(
    {
        "test_an_exit_two_legs_execute_is_rostered_before_the_arm_that_bits_two",
        "test_every_frontend_call_site_reaches_a_route",
        "test_every_name_this_file_imports_reaches_a_leg_or_is_rostered",
        "test_every_route_without_a_frontend_consumer_is_rostered_by_name",
        "test_loose_pairings_are_rostered",
        "test_the_exit_read_map_is_measured_not_recited",
        "test_the_helper_hop_has_its_own_second_lens",
        "test_the_private_page_interfaces_really_are_in_the_census",
        "test_the_read_map_generator_names_no_register_and_the_anchors_are_rostered",
        "test_the_two_lenses_over_the_read_map_agree_leg_by_leg",
    }
)

#: ``(names in the owner's __all__, names this file imports, names public by convention)``.
#: Three numbers, because the surface has two seams and each is a roster below.
_OWNER_SURFACE = (27, 21, 28)

#: Exported by the owner, not imported here. The owner's surface is not this gate's
#: surface: these six are how the plane is built (``Payload``, ``api_routers``,
#: ``path_candidates``) or shapes other files consume (``BlindSpot``, ``HookReading``,
#: ``ReturnAccount``). Importing one is legitimate, and it must move ``_OWNER_SURFACE``.
_OWNER_EXPORTED_NOT_IMPORTED: frozenset[str] = frozenset(
    {
        "BlindSpot",
        "HookReading",
        "Payload",
        "ReturnAccount",
        "api_routers",
        "path_candidates",
    }
)

#: Public by name in the owner yet absent from ``__all__``: a name another module may
#: import today and a leg would not see in the export list. ``HTTP_VERBS`` is the one
#: row, and the seam it opens goes both ways -- it is why ``surface`` is a triple.
_OWNER_PUBLIC_NOT_EXPORTED: frozenset[str] = frozenset({"HTTP_VERBS"})


#: The ten registers the read map above is made of, by name. Rostered so that the ban in
#: ``test_the_read_map_generator_names_no_register_and_the_anchors_are_rostered`` has a
#: population to report identity about -- which helper named which register, not how many
#: relations moved. A register that stops existing moves this tuple.
_READ_MAP_REGISTERS = (
    "EXIT_READS",
    "EXIT_READS_ALIAS_ONLY",
    "EXITS_WITH_MULTIPLE_EXECUTORS",
    "LEGS_WITHOUT_DIRECT_READ",
    "_AXIS_C_EXECUTORS",
    "_DIRECT_RELATION_INSTANCES",
    "_EXIT_READ_INSTANCES",
    "_OWNER_EXPORTED_NOT_IMPORTED",
    "_OWNER_PUBLIC_NOT_EXPORTED",
    "_OWNER_SURFACE",
)

#: Helpers whose body names one of those registers. Measured 0: the generator reaches for the
#: repo root and for frozen literals, never for the numbers it is supposed to derive. #549's
#: arm G7 is the shape this roster would have caught -- it named two registers and stayed green.
_HELPERS_NAMING_READ_MAP_REGISTERS: frozenset[str] = frozenset()

#: The uppercase bindings ``_read_map`` itself names. One, and it is a path.
_READ_MAP_ANCHORS: frozenset[str] = frozenset({"REPO"})

#: Every uppercase binding this file's helpers name, registers excluded. This is the scope of
#: the ban: a helper may reach the repo root, the four band names and the page a fixture writes,
#: and nothing else spelled in uppercase. #549 recorded "7 helpers violate" for a criterion that
#: counted these three as violations; measured against the registers themselves the population is
#: zero, which is why the guard is a scope plus a roster rather than a blanket.
_ANCHOR_BINDINGS: frozenset[str] = frozenset({"_BANDS", "_PAGE", "REPO"})

#: Legs whose helper hop brings back no plane name at all. The empty-via legs are the ones the
#: cross-check below compares as empty on both sides, so they need a roster: a lens that reached
#: no helper and a lens that reached helpers reading nothing look identical in a count.
LEGS_WITHOUT_VIA_HELPER_READ: frozenset[str] = frozenset(
    {
        "test_a_hook_that_issues_two_requests_is_refused_and_says_so",
        "test_an_exit_two_legs_execute_is_rostered_before_the_arm_that_bits_two",
        "test_every_name_this_file_imports_reaches_a_leg_or_is_rostered",
        "test_the_conditional_branches_the_fold_rewrites_are_rostered_whole",
        "test_the_exit_read_map_is_measured_not_recited",
        "test_the_fold_reports_every_return_the_handler_can_take",
        "test_the_fold_stops_where_the_caller_stopped_spelling_a_path",
        "test_the_helper_hop_has_its_own_second_lens",
        "test_the_hook_consumers_are_measured_from_their_own_bodies",
        "test_the_path_aliases_the_fold_rewrites_are_rostered_whole",
        "test_the_read_map_generator_names_no_register_and_the_anchors_are_rostered",
        "test_the_shapes_the_ruler_sees_and_does_not_read_are_rostered",
        "test_the_three_conditional_guards_each_carry_their_own_case",
        "test_the_two_lenses_over_the_read_map_agree_leg_by_leg",
    }
)

#: Sum over legs of the helpers each reaches, counted once per leg (so a helper two legs share
#: is two edges). The population the text lens walks: 0 would mean the leg below compares two
#: empty sets and calls it agreement.
_CLOSURE_EDGE_TOTAL = 71


class ReadMap(NamedTuple):
    """What this file's source says about its own imports."""

    rows: dict[str, tuple[frozenset[str], frozenset[str], frozenset[str]]]
    alias_only: frozenset[str]
    legs: frozenset[str]
    surface: tuple[int, int, int]
    exported_not_imported: frozenset[str]
    public_not_exported: frozenset[str]


def _annotation_names(node: ast.AST) -> set[str]:
    """Every bare name that sits inside an annotation subtree of ``node``."""
    out: set[str] = set()
    for sub in ast.walk(node):
        ann: ast.expr | None = None
        if isinstance(sub, (ast.AnnAssign, ast.arg)):
            ann = sub.annotation
        elif isinstance(sub, (ast.FunctionDef, ast.AsyncFunctionDef)):
            ann = sub.returns
        if ann is not None:
            out |= {n.id for n in ast.walk(ann) if isinstance(n, ast.Name)}
    return out


def _executable_names(fn: ast.FunctionDef) -> set[str]:
    """Bare names in a function, minus those that appear only inside annotations.

    A name used both ways lands here: the annotation is not the reason the leg reads it.
    """
    all_names = {n.id for n in ast.walk(fn) if isinstance(n, ast.Name)}
    return all_names - _annotation_names(fn)


def _token_words(lines: list[str], start: int, end: int) -> set[str]:
    """The second lens: word tokens in a line span, with strings and comments dropped.

    Not a restatement of the tree walk -- it rescans the text the parser was given. A name that
    only *looks* read (inside a docstring) reaches neither lens; a name read through an
    f-string expression reaches both. That is the property the cross-check leg needs, because a
    register could otherwise be kept honest only by the arm that breaks it.
    """
    span = textwrap.dedent("\n".join(lines[start - 1 : end]))
    out: set[str] = set()
    try:
        for tok in tokenize.generate_tokens(io.StringIO(span).readline):
            if tok.type in (tokenize.NAME, tokenize.OP):
                out.add(tok.string)
    except tokenize.TokenError:
        return {"<a span this file's own lines will not tokenize>"}
    return out


def _owner_surface(owner: ast.Module) -> tuple[set[str], set[str]]:
    """(``__all__`` of the owner, names public by convention) -- the two are not the same set."""
    exported: set[str] = set()
    for stmt in owner.body:
        if (
            isinstance(stmt, ast.Assign)
            and isinstance(stmt.value, (ast.List, ast.Tuple))
            and any(isinstance(t, ast.Name) and t.id == "__all__" for t in stmt.targets)
        ):
            exported = {
                e.value
                for e in stmt.value.elts
                if isinstance(e, ast.Constant) and isinstance(e.value, str)
            }
    public = {
        node.name
        for node in owner.body
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef))
        and not node.name.startswith("_")
    }
    for stmt in owner.body:
        if isinstance(stmt, ast.Assign):
            public |= {
                t.id for t in stmt.targets if isinstance(t, ast.Name) and not t.id.startswith("_")
            }
    return exported, public


def _read_map() -> ReadMap:
    """Derive the exit -> leg map from this file's source. Nothing here is hand-copied."""
    gate_src = Path(__file__).resolve().read_text(encoding="utf-8")
    module = ast.parse(gate_src)
    owner = ast.parse((REPO / "tests" / "_payload_plane.py").read_text(encoding="utf-8"))
    exported, public = _owner_surface(owner)

    imported: set[str] = set()
    for stmt in module.body:
        if (
            isinstance(stmt, ast.ImportFrom)
            and stmt.module
            and stmt.module.endswith("_payload_plane")
        ):
            imported = {alias.asname or alias.name for alias in stmt.names}

    funcs = {node.name: node for node in module.body if isinstance(node, ast.FunctionDef)}
    legs = {name for name in funcs if name.startswith("test_")}
    executable = {name: _executable_names(funcs[name]) & imported for name in funcs}
    annotated = {
        name: _annotation_names(funcs[name]) & imported - executable[name] for name in funcs
    }

    def calls_in(fn: ast.FunctionDef) -> set[str]:
        return {
            call.func.id
            for call in ast.walk(fn)
            if isinstance(call, ast.Call)
            and isinstance(call.func, ast.Name)
            and call.func.id in funcs
        }

    via: dict[str, set[str]] = {}
    for leg in sorted(legs):
        own = executable[leg] | annotated[leg]
        reached: set[str] = set()
        seen: set[str] = set()
        stack = sorted(calls_in(funcs[leg]))
        while stack:
            helper = stack.pop()
            if helper in seen:
                continue
            seen.add(helper)
            reached |= (executable[helper] | annotated[helper]) - own
            stack += sorted(calls_in(funcs[helper]))
        via[leg] = reached - own

    rows = {
        name: (
            frozenset(leg for leg in legs if name in executable[leg]),
            frozenset(leg for leg in legs if name in annotated[leg]),
            frozenset(leg for leg in legs if name in via[leg]),
        )
        for name in sorted(imported)
    }

    module_level: set[str] = set()
    for stmt in module.body:
        if isinstance(stmt, ast.FunctionDef):
            continue
        module_level |= {n.id for n in ast.walk(stmt) if isinstance(n, ast.Name)}
    read_by_leg = {name for name, row in rows.items() if any(row)}

    return ReadMap(
        rows=rows,
        alias_only=frozenset(module_level & imported - read_by_leg),
        legs=frozenset(legs),
        surface=(len(exported), len(imported), len(public)),
        exported_not_imported=frozenset(exported - imported),
        public_not_exported=frozenset(public - exported),
    )


def _leg_direct_reads(read: ReadMap, leg: str) -> set[str]:
    """Names the leg itself reads (executed or annotated), without the helper hop."""
    return {name for name, row in read.rows.items() if leg in row[0] or leg in row[1]}


def _uppercase_module_binds(module: ast.Module) -> frozenset[str]:
    """Every module-level binding this file spells in uppercase: registers, anchors and floors.

    The ban leg needs the population, not a hand-typed list of it: a register added by a later
    number is inside the ban the moment it exists, because it is an uppercase binding.
    """
    out: set[str] = set()
    for stmt in module.body:
        if not isinstance(stmt, (ast.Assign, ast.AnnAssign)):
            continue
        targets: list[ast.expr] = (
            list(stmt.targets) if isinstance(stmt, ast.Assign) else [stmt.target]
        )
        out |= {t.id for t in targets if isinstance(t, ast.Name) and t.id.isupper()}
    return frozenset(out)


def _helper_named_binds(
    funcs: dict[str, ast.FunctionDef], binds: frozenset[str]
) -> dict[str, frozenset[str]]:
    """Which of ``binds`` each module-level helper's body executes, keyed by helper.

    The bind set arrives as an argument on purpose. A guard that named the registers it audits
    would be the violation it is looking for, and ``_read_map``'s own body would then be read
    by a helper that reads it -- the self-reference this leg exists to refuse.
    """
    return {
        name: frozenset(_executable_names(funcs[name]) & binds)
        for name in sorted(funcs)
        if not name.startswith("test_")
    }


def _helper_closure(funcs: dict[str, ast.FunctionDef], leg: str) -> tuple[str, ...]:
    """Every helper ``leg`` reaches, transitively -- the same walk the generator's stack makes.

    Written beside ``_read_map`` rather than inside it, so the second lens over the helper hop
    can disagree with the generator: this one answers *which helpers*, and the leg below
    compares *what they read*.
    """

    def calls_in(fn: ast.FunctionDef) -> set[str]:
        return {
            call.func.id
            for call in ast.walk(fn)
            if isinstance(call, ast.Call)
            and isinstance(call.func, ast.Name)
            and call.func.id in funcs
        }

    seen: set[str] = set()
    stack = sorted(calls_in(funcs[leg]))
    while stack:
        helper = stack.pop()
        if helper in seen:
            continue
        seen.add(helper)
        stack += sorted(calls_in(funcs[helper]))
    return tuple(sorted(seen))


# Floors, not equalities: other lanes move this tree under us, and a census that fails
# because a legitimate route was added gets widened by whoever is reddest. The
# two-sided legs are what catch a real drop.
_MIN_ENDPOINTS = 50
#: Measured at #544's landing: 40 endpoints paired and 45 sites read, after the two
#: consumer-reading rules. #546 moved the measurement to 42 paired and 48 sites and left
#: both floors where they were: a floor that rises with every widening tracks growth
#: instead of guarding it, and what these two are for is a lane *losing* consumers.
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


_BANDS = ("always", "overstated", "sometimes", "absent")


def _band_row(row: OptionalBand) -> tuple[tuple[str, int], dict[str, tuple[str, ...]]]:
    """(declaring site, only the bands holding something) for one axis-(c) row.

    Empty bands stay out: a row's job is to say what the route does, and four tuples per
    endpoint would make one key moving from ``always`` to ``sometimes`` read as two
    changes rather than one.
    """
    return (row.file, row.line), {name: getattr(row, name) for name in _BANDS if getattr(row, name)}


def _fixture_repo(root: Path, api: dict[str, str], web: dict[str, str]) -> Path:
    """A whole tiny repo -- one route module and one frontend -- for the two route-side exits.

    ``_fixture_web`` is enough while only the consumer is being argued about. Axis (c) and
    the fuse both read a *handler*, so the lab needs an ``api/`` tree too, addressed the way
    the owner addresses it: ``(root / "api").rglob`` for routers and
    ``root / module.replace(".", "/")`` for the fold. The route's module name is therefore
    ``api.routes.ping``, and a fixture that spelled it any other way would fold nothing.
    """
    for rel, text in api.items():
        target = root / "api" / rel
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text(text, encoding="utf-8")
    for rel, text in web.items():
        target = root / "apps" / "web" / "src" / rel
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text(text, encoding="utf-8")
    return root


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


def test_the_hook_consumers_are_measured_from_their_own_bodies() -> None:
    """E6: a consumer that is not an api client, qualified by what its body does.

    ``useRemoteData<MatrixData>(path)`` declares a payload contract and never names a
    verb, so the census has somewhere to get one. It takes it from the hook's own body --
    ``apiGet<T>(path, controller.signal)`` -- which is why this leg reads the body instead
    of a table: a register that recites "useRemoteData means GET" would stay green when a
    lane rewrote the hook to POST, and the pairing the census reports would then be a
    claim about a request nobody makes.

    The site count belongs to the register for the same reason #544 gave the alias table
    one. A hook that stopped being call-shaped loses its three sites, and the 48-to-38
    floor would not notice; here the count is the claim.
    """
    readings = hook_readings(web_src(REPO))
    consumers = {r.name: r for r in readings if len(r.verbs) == 1}
    refused = sorted(r.name for r in readings if len(r.verbs) > 1)
    assert refused == sorted(HOOK_REFUSALS), f"multi-request hooks appeared: {refused}"
    assert set(consumers) == set(HOOK_CONSUMERS), (
        f"hook consumers drifted: new={sorted(set(consumers) - set(HOOK_CONSUMERS))} "
        f"gone={sorted(set(HOOK_CONSUMERS) - set(consumers))}"
    )
    calls, _excluded = frontend_calls(web_src(REPO))
    for name, reading in consumers.items():
        verb, host, rostered = HOOK_CONSUMERS[name]
        assert reading.verbs == (verb,), f"{name} issues {reading.verbs}, register says {verb}"
        assert reading.file == host, f"{name} moved to {reading.file}"
        found_sites = sum(1 for site in calls if site.via_hook == name)
        assert found_sites == rostered, (
            f"{name}: the register says it shaped {rostered} census sites, the census found "
            f"{found_sites}"
        )


def test_the_conditional_branches_the_fold_rewrites_are_rostered_whole() -> None:
    """E7: an argument that is a ternary, and the one arm the census was allowed to take.

    ``jobId ? "/api/v1/jobs/" + id + "/matrix" : null`` is a request whose path is chosen
    at runtime. Folding it is a rewrite of somebody else's expression, so the register
    carries the branch as written: the claim is not "this page reads the matrix" but "this
    arm of this ternary is the path the census used", and a reader can check it.

    The masked literal is only one of three guards, and on today's tree it is the one with
    no work to do: C3 (unmask alone) measured 14 green legs and an unmoved census, because
    `_fold_argument` asks for branches only after the literal-and-alias fold has failed and
    the single argument that reaches it has no ``?`` inside a literal. The damage belongs to
    C3b, which drops the ordering too -- and there it is exactly what the #546 rehearsal
    predicted: 48 sites became 46, the contracts page went back to
    ``UNPAIRED_ENDPOINTS``, ``/agent/jobs`` lost its loose pairing, and the extras register
    lost an endpoint, four registers moving to make the census look *narrower*. Two path
    shaped arms are a refusal for the same reason: a ruler that picks one of two endpoints
    has paired a call with a contract its caller never asked for.
    """
    rows, refused = conditional_table(web_src(REPO))
    found = {(file, line): (path, branch) for file, line, path, branch in rows}
    added = sorted(set(found) - set(PATH_CONDITIONALS))
    removed = sorted(set(PATH_CONDITIONALS) - set(found))
    moved = sorted(
        (key, found[key], PATH_CONDITIONALS[key])
        for key in set(found) & set(PATH_CONDITIONALS)
        if found[key] != PATH_CONDITIONALS[key]
    )
    assert not added and not removed and not moved, (
        f"conditional table drifted: new={added} gone={removed} changed={moved}"
    )
    assert {(file, line) for file, line, _paths in refused} == PATH_CONDITIONAL_REFUSALS, (
        f"the fold started refusing (or stopped refusing) arguments: {sorted(refused)}"
    )
    calls, _excluded = frontend_calls(web_src(REPO))
    for file, line, path, _branch in rows:
        site = next((s for s in calls if s.file == file and s.line == line), None)
        assert site is not None and site.path == path, (
            f"{file}:{line} is rostered as a rewritten branch but the census has no such site"
        )


def _identifiers(text: str) -> set[str]:
    return set(re.findall(r"\b[A-Za-z_][A-Za-z0-9_]{2,}\b", text))


def _handler_source(key: Key, endpoint_table: list[Endpoint]) -> str:
    for endpoint in endpoint_table:
        if _endpoint_key(endpoint) == key:
            module = REPO / (endpoint.module.replace(".", "/") + ".py")
            return module.read_text(encoding="utf-8")
    raise AssertionError(f"{key} is not an endpoint in the table")


def _fixture_web(root: Path, files: dict[str, str]) -> Path:
    """A synthetic frontend, addressed the way the owner addresses the real one.

    Four of #547's claims are about shapes this tree does not contain, and the only honest
    way to ask a ruler about a shape is to write it down. `_rel_in_web` labels a file from
    the last three parts of the tree it was handed, so building `<root>/apps/web/src` keeps
    a fixture row in the same `apps/web/src/...` form as the real register entries: the
    value a leg expects and the evidence it reads are the same shape of thing, and an arm
    that breaks the labelling breaks the leg instead of hiding behind it.
    """
    web = root / "apps" / "web" / "src"
    for rel, text in files.items():
        target = web / rel
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text(text, encoding="utf-8")
    return web


#: One call written inside a component body. `__LINE__` rather than a format field: the
#: type literal on the first line is `{ rows: string[] }`, and `str.format` reads that
#: `{` as a field name -- measured by the probe dying with ``KeyError: ' rows'``.
_PAGE = "type T = { rows: string[] };\nfunction Page() {\n  __LINE__\n  return null;\n}\n"


def _page(line: str) -> str:
    return _PAGE.replace("__LINE__", line)


def test_the_fold_stops_where_the_caller_stopped_spelling_a_path(tmp_path: Path) -> None:
    """F1: a depth-0 chooser yields a branch or a row, never a path glued from two expressions.

    ``"/api/v1/x?q" === q ? "/api/v1/a" : null`` is not one expression built out of
    another. The fold used to walk every literal in the argument and record one `{}` slot
    per gap, which produced ``/api/v1/x?q{}/api/v1/a{}`` -- a path-shaped string the page
    never wrote, kept by the census because it started with `/`, so the conditional
    reading was never asked. The rehearsal measured both halves: with the stop the site is
    ``/api/v1/a`` with one row in the conditional roster; without it the site is the glued
    string and the roster is empty, and the census would have paired a browser against an
    endpoint that exists in no router.

    The second half is the part a fix usually forgets. When neither arm is a path
    (``kind === "a" ? queryA : queryB``), refusing to fabricate also *loses the site*, and
    a ruler that goes quiet is indistinguishable from a ruler with nothing to read. That
    argument is a ``glued-across-depth0-operator`` row.

    Nothing on the product tree is affected: the one depth-0 chooser the census meets is
    ``pages/Matrix.tsx:22``, whose arm is a path, and the rehearsal read all 23 registers
    identical with the stop in and out. A fence with no load on it today still has to say
    which way it falls, which is what this file's fixture is for.
    """
    armed = _fixture_web(
        tmp_path / "arm",
        {
            "Chooser.tsx": _page(
                'const found = apiGet<T>("/api/v1/x?q" === q ? "/api/v1/a" : null);'
            ),
        },
    )
    calls, _excluded = frontend_calls(armed)
    assert [site.path for site in calls] == ["/api/v1/a"], (
        f"the fold glued the two sides of a chooser again: {[s.path for s in calls]}"
    )
    rows, refused = conditional_table(armed)
    assert [(row[2], row[3]) for row in rows] == [("/api/v1/a", '"/api/v1/a"')], rows
    assert refused == [], f"the roster refused what it should have read: {refused}"
    assert ruler_blind_spots(armed) == [], "a reading landed and the blind census said so anyway"

    dark = _fixture_web(
        tmp_path / "dark",
        {"Both.tsx": _page('const found = apiGet<T>(kind === "a" ? queryA : queryB);')},
    )
    calls, _excluded = frontend_calls(dark)
    assert calls == [], f"an argument of two variables became a site: {[s.path for s in calls]}"
    rows, refused = conditional_table(dark)
    assert rows == [] and refused == [], f"the chooser was read as something: {rows} {refused}"
    spots = ruler_blind_spots(dark)
    assert [(s.shape, s.file, s.line) for s in spots] == [
        ("glued-across-depth0-operator", "apps/web/src/Both.tsx", 3)
    ], f"the stopped fold went silent instead of reporting: {spots}"


def test_the_three_conditional_guards_each_carry_their_own_case(tmp_path: Path) -> None:
    """E7 splits on a masked copy, at depth 0, one layer deep: three guards, three shapes.

    #546 measured the first guard on the product tree and found it inert: removing the
    literal mask (arm C3) left all 14 legs green and the census unmoved, because the fold
    only asks for branches once the literal-and-alias reading has failed, and the one
    argument that reaches it has no ``?`` inside a literal. C3b, which also drops the
    *ordering*, measured 48 sites becoming 46. An inert layer with no fixture is a layer
    that can be deleted for a reason, so this leg writes the three shapes that separate the
    guards -- each one answers differently from the other two:

    * `s + "/api/v1/x?q" ? "/api/v1/a" : null` -- the ``?`` inside a literal sits at depth
      0 in the raw text, so only the mask keeps this a conditional. Measured: one site,
      ``/api/v1/a``, and one roster row. Unmasked, the split lands inside the literal and
      the site disappears (the #546 C3 measurement, now pinned where it can be re-run).
    * `(ok ? "/api/v1/x" : "/api/v1/y") + tail` -- a conditional the caller fenced off in
      parentheses. The depth guard leaves it to the ordinary fold, which records it as
      slots and hands back nothing rooted. Measured: no site, no refusal, no row. Arm D4
      removes the guard and the same text becomes one refusal.
    * `jobId ? (inner ? "/api/v1/a" : "/api/v1/b") : "/api/v1/c"` -- one layer is as deep
      as E7 goes. Measured: the site is ``/api/v1/c``, one roster row, and the two paths
      that sat in the other arm come back as a `nested-conditional-arm` row instead of
      vanishing. The product tree has no nested conditional, so the shape is registered by
      its fixture and by zero rows on the real census.
    """
    masked = _fixture_web(
        tmp_path / "mask",
        {"Mask.tsx": _page('const found = apiGet<T>(s + "/api/v1/x?q" ? "/api/v1/a" : null);')},
    )
    calls, _excluded = frontend_calls(masked)
    assert [site.path for site in calls] == ["/api/v1/a"], (
        "the mask stopped holding the query string's `?` apart from the ternary's"
    )
    rows, refused = conditional_table(masked)
    assert len(rows) == 1 and rows[0][2] == "/api/v1/a", rows
    assert refused == []

    fenced = _fixture_web(
        tmp_path / "depth",
        {"Depth.tsx": _page('const found = apiGet<T>((ok ? "/api/v1/x" : "/api/v1/y") + tail);')},
    )
    calls, _excluded = frontend_calls(fenced)
    rows, refused = conditional_table(fenced)
    assert calls == [] and rows == [] and refused == [], (
        f"the depth guard let a parenthesized conditional through: {[s.path for s in calls]} "
        f"{rows} {refused}"
    )

    nested = _fixture_web(
        tmp_path / "nested",
        {
            "Nested.tsx": _page(
                'const found = apiGet<T>('
                'jobId ? (inner ? "/api/v1/a" : "/api/v1/b") : "/api/v1/c");'
            ),
        },
    )
    calls, _excluded = frontend_calls(nested)
    assert [site.path for site in calls] == ["/api/v1/c"], (
        f"the outer arm was not the one read: {[s.path for s in calls]}"
    )
    spots = ruler_blind_spots(nested)
    assert [(s.shape, s.seen) for s in spots] == [
        ("nested-conditional-arm", ("/api/v1/a", "/api/v1/b"))
    ], f"the inner arms were read, or lost silently: {spots}"


def test_a_hook_that_issues_two_requests_is_refused_and_says_so(tmp_path: Path) -> None:
    """E6's refusal, written down instead of left as a sentence in the owner.

    A hook that makes two requests is not a consumer: its type argument would be handed to
    whichever call the ruler picked, and an invented pairing is worse than a missing one.
    #546 measured that rule against the product tree only indirectly -- both real hooks
    issue one request, so nothing on the tree distinguishes "refused two" from "saw none".
    That is the same trap ⓬ was queued for, and this leg closes it with a tree that does
    have a second request in it.

    Both halves are asserted, because a refusal that is not reported is how a consumer
    disappears: `useDouble` has to stay in `hook_readings` with both verbs -- the census
    that refuses it still has to say it saw it -- and `useSingle`'s call has to reach the
    census with the verb read out of its body, not out of its name.
    """
    web = _fixture_web(
        tmp_path,
        {
            "hooks/Two.tsx": (
                "export function useDouble<T>(path: string) {\n"
                "  const a = apiGet<T>(path);\n"
                "  const b = apiPost<T>(path + '/ack', {});\n"
                "  return { a, b };\n}\n"
            ),
            "hooks/One.tsx": (
                "export function useSingle<T>(path: string) {\n  return apiGet<T>(path);\n}\n"
            ),
            "pages/Use.tsx": (
                "type T = { rows: string[] };\nfunction Page() {\n"
                '  const one = useSingle<T>("/api/v1/one");\n'
                '  const two = useDouble<T>("/api/v1/two");\n'
                "  return { one, two };\n}\n"
            ),
        },
    )
    readings = {(r.name, r.verbs) for r in hook_readings(web)}
    assert readings == {
        ("useSingle", ("get",)),
        ("useDouble", ("get", "post")),
    }, f"the hook census changed shape: {readings}"
    calls, _excluded = frontend_calls(web)
    sites = [(s.verb, s.path, s.via_hook) for s in calls]
    assert sites == [("get", "/api/v1/one", "useSingle")], (
        f"a two-request hook was read, or a one-request hook was lost: {sites}"
    )


def test_the_shapes_the_ruler_sees_and_does_not_read_are_rostered(tmp_path: Path) -> None:
    """Where the ruler is blind is measured, registered, and re-computed -- including the columns.

    ``_function_body`` takes the first balanced brace pair after a signature, so a hook
    written ``function useX(): { a: boolean } { ... }`` is read as a body of
    ` a: boolean `; ``_HOOK_DEF`` matches only `function useX`, so ``const useX = () =>``
    and ``async function useX`` are not declarations at all. All of these are visible from
    inside the owner, and none of them gets a reading, because the population they would
    widen is zero: every one of the 14 frontend `use*` declarations is a plain `function`,
    and the three whose annotation ate the body issue no request.

    So the register carries the shape, and the leg carries the two tuples that say whether
    the shape costs anything. `seen` comes from the declaration's own region -- bounded at
    the next top-level declaration, which the first rehearsal got wrong and paid for with
    two phantom consumers -- and `read` comes from the body the ruler actually took. The
    fixture at the bottom is the load test: the same three shapes, each one holding a
    request, and all three come back with `seen != read`.
    """
    spots = ruler_blind_spots(web_src(REPO))
    found = {(s.shape, s.file, s.line): (s.name, s.seen, s.read) for s in spots}
    added = sorted(set(found) - set(RULER_BLIND_SPOTS))
    gone = sorted(set(RULER_BLIND_SPOTS) - set(found))
    moved = sorted(
        (key, found[key], RULER_BLIND_SPOTS[key])
        for key in set(found) & set(RULER_BLIND_SPOTS)
        if found[key] != RULER_BLIND_SPOTS[key]
    )
    assert not added and not gone and not moved, (
        f"the blind-spot census drifted: new={added} gone={gone} changed={moved}"
    )
    victims = sorted((s.shape, s.file, s.line) for s in spots if s.seen != s.read)
    assert victims == sorted(RULER_BLIND_SPOT_VICTIMS), (
        f"the ruler is now losing something at {victims}; "
        f"the register says {sorted(RULER_BLIND_SPOT_VICTIMS)}"
    )

    fixture = _fixture_web(
        tmp_path,
        {
            "hooks/Arrow.tsx": "export const useArrow = <T,>(path: string) => apiGet<T>(path);\n",
            "hooks/Async.tsx": (
                "export async function useAsync<T>(path: string) {\n"
                "  return apiGet<T>(path);\n}\n"
            ),
            "hooks/Annotated.tsx": (
                "export function useAnnotated<T>(path: string): { data: T | null } {\n"
                "  const d = apiGet<T>(path);\n"
                "  return { data: null };\n}\n"
            ),
        },
    )
    blind = {(s.shape, s.name, s.seen, s.read) for s in ruler_blind_spots(fixture)}
    assert blind == {
        ("arrow-hook", "useArrow", ("get",), ()),
        ("async-hook", "useAsync", ("get",), ()),
        ("annotation-swallowed-body", "useAnnotated", ("get",), ()),
    }, f"the columns stopped being measured: {blind}"
    assert all(s.seen != s.read for s in ruler_blind_spots(fixture)), (
        "a fixture in which the blindness costs nothing proves nothing"
    )


def test_an_optional_key_is_rostered_in_the_band_the_route_puts_it_in() -> None:
    """Axis (c), the third direction: what a frontend's `?:` actually costs.

    #542 charges a *required* key a branch forgot. #543/#544 charge a *published* key
    nobody declared. Nobody read the third case -- a key the browser says may be missing --
    and the gap is not cosmetic: `api.ts` carries a comment explaining that
    `JobsPage.total` must be required, because reading that field as a count told a
    workspace with 57 verifications that it had 1, while `Guide.tsx` still writes
    `total?: number`, renders `null` when the key is absent, and `/jobs` has always
    answered it on its only exit. Two frontend files disagree with each other and the
    census is the only thing in the repo that can say so.

    The bands are asserted per endpoint *and* summed, because those catch different edits:
    a route whose reading changed, and keys moving between bands on a route that keeps
    talking.
    """
    rows = optional_publish_bands(REPO)
    assert len(rows) == _AXIS_C_ROW_COUNT, (
        f"the axis speaks about {len(rows)} endpoints, not {_AXIS_C_ROW_COUNT}"
    )
    found = {
        (row.verb, row.path): _band_row(row)
        for row in rows
        if row.always or row.overstated or row.sometimes or row.absent
    }
    added = sorted(set(found) - set(AXIS_C_BANDS))
    gone = sorted(set(AXIS_C_BANDS) - set(found))
    moved = sorted(k for k in set(found) & set(AXIS_C_BANDS) if found[k] != AXIS_C_BANDS[k])
    assert not added and not gone and not moved, (
        f"axis (c) drifted: new={added} gone={gone} changed={moved} found={found}"
    )
    totals = {name: sum(len(getattr(row, name)) for row in rows) for name in _BANDS}
    assert totals == AXIS_C_KEY_TOTALS, f"the band totals moved: {totals}"

    _endpoint_table, pairs, _orphans, _declarations = _census()
    by_key: dict[Key, Endpoint] = {}
    for pair in pairs:
        by_key.setdefault(_pair_key(pair), pair.endpoint)
    for name, expected in AXIS_C_ABSENT_PUBLISHERS.items():
        publishers = tuple(sorted(
            key for key, endpoint in by_key.items() if name in payload_of(REPO, endpoint).published
        ))
        assert publishers == tuple(sorted(expected)), (
            f"which routes publish {name!r} moved: {publishers} vs {expected}"
        )

    health = next(row for row in rows if (row.verb, row.path) == ("get", "/api/v1/health"))
    assert health.absent == ("capabilities", "degraded_reasons"), (
        f"health's optional keys are no longer the two named here: {health.absent}"
    )
    test_file = REPO / "apps" / "web" / "src" / "pages" / "Health.test.tsx"
    fallback = test_file.read_text(encoding="utf-8")
    assert 'stateOf("health-category-capabilities")).toBe("unknown")' in fallback, (
        "the page stopped pinning the fallback that makes an absent key harmless, so this "
        "band is no longer a fact about a defended field -- it is an undefended missing key"
    )


def test_the_fold_reports_every_return_the_handler_can_take(tmp_path: Path) -> None:
    """The fuse under axis (c): an intersection is a proof only over every exit.

    ``Payload.always`` is ``set.intersection(*branches)``, and every leg above reads the
    result as "these keys always arrive". Hand the fold one of a handler's two returns and
    it still prints a set -- a positive claim built on a partial read, which is the worse
    cousin of the empty reads this campaign keeps hitting: an empty read prints as nothing,
    this one prints as a guarantee. The cheapest edit a handler can take, a bare early
    ``return``, produces exactly that shape.

    Population 0 on this tree, so the leg has to bring its own. The fixture's handler has a
    bare ``return`` and a dict ``return``: the counts come back (2, 1) with nothing
    reported, and the axis still files the second return's key under ``always``. Two rows
    disagreeing on the real tree is what the unbounded roster is for; a third shape --
    disagreeing and silent -- is the one this leg exists to refuse.
    """
    rows = return_accounting(REPO)
    distribution = dict(Counter((row.own_returns, row.branches) for row in rows))
    assert distribution == RETURN_ACCOUNT_DISTRIBUTION, (
        f"the return/branch census moved: {distribution}"
    )
    mismatches = {
        (row.verb, row.path): (row.own_returns, row.branches) for row in rows if not row.complete
    }
    assert mismatches == RETURN_ACCOUNT_MISMATCHES, (
        f"rows whose exits and branches disagree moved: {mismatches}"
    )
    for key in mismatches:
        assert key in UNBOUND_PAYLOADS, f"{key} disagrees and is not in the unbounded roster"

    silent = [
        (row.verb, row.path, row.own_returns, row.branches)
        for row in rows
        if row.own_returns != row.branches and not row.unbounded
    ]
    assert not silent, f"the fold reported a partial branch list without saying so: {silent}"
    unproven = [
        (row.verb, row.path, row.always)
        for row in optional_publish_bands(REPO)
        if row.always and not row.complete
    ]
    assert not unproven, f"axis (c) called a partial read a guarantee: {unproven}"

    fixture = _fixture_repo(
        tmp_path / "fuse",
        {
            "routes/ping.py": (
                "from fastapi import APIRouter\n"
                "\n"
                "router = APIRouter(prefix='/api/v1')\n"
                "\n"
                "@router.get('/ping')\n"
                "async def api_ping(flag: bool) -> dict[str, object]:\n"
                "    if flag:\n"
                "        return\n"
                "    return {'a': 1, 'b': 2}\n"
            )
        },
        {
            "Pages.tsx": (
                "type P = { a: number; b?: number };\n"
                "function Page() {\n"
                "  apiGet<P>('/api/v1/ping');\n"
                "  return null;\n"
                "}\n"
            )
        },
    )
    accounts = {row.path: row for row in return_accounting(fixture)}
    assert set(accounts) == {"/api/v1/ping"}, f"the fixture paired wrong: {sorted(accounts)}"
    ping = accounts["/api/v1/ping"]
    assert (ping.own_returns, ping.branches, ping.unbounded) == (2, 1, ()), (
        f"the bare return was not counted as an exit, or was reported as a refusal: {ping}"
    )
    assert not ping.complete, "the fuse read a two-exit handler as one branch and called it done"
    bands = {row.path: row for row in optional_publish_bands(fixture)}
    assert bands["/api/v1/ping"].always == ("b",), (
        f"the axis stopped demonstrating the lie the fuse refuses: {bands['/api/v1/ping']}"
    )
    assert not bands["/api/v1/ping"].complete, (
        "the fixture no longer shows `always` being claimed on a partial branch list"
    )


def test_every_name_this_file_imports_reaches_a_leg_or_is_rostered() -> None:
    """The import list is a choice, and this leg registers both sides of it.

    A name can reach the plane in four ways, and only three of them are a leg reading it:
    ``Member`` is imported, is used, and is read by no test -- it sits in the module-level alias
    ``Declarations``. Ruff cannot see that, because the import really is used. The other side of
    the choice is the owner's own surface: 27 names in ``__all__`` against 21 imported here, and
    28 public by name against those 27. Both differences are rosters, so a lane that widens the
    import list or edits ``__all__`` moves a number instead of moving the meaning quietly.
    """
    read = _read_map()
    ghosts = sorted(set(EXIT_READS) - set(read.rows))
    gaps = sorted(set(read.rows) - set(EXIT_READS))
    assert not ghosts and not gaps, (
        f"the table is not over this file's imports: ghosts={ghosts} gaps={gaps}"
    )

    alias_rows = sorted(name for name, row in read.rows.items() if not any(row))
    assert alias_rows == sorted(EXIT_READS_ALIAS_ONLY), (
        f"which imports reach no leg moved: {alias_rows} vs {sorted(EXIT_READS_ALIAS_ONLY)}"
    )
    assert read.alias_only == EXIT_READS_ALIAS_ONLY, (
        f"{sorted(read.alias_only)} are named only at module level; "
        f"{sorted(EXIT_READS_ALIAS_ONLY)} is the roster"
    )

    assert read.surface == _OWNER_SURFACE, (
        f"owner surface moved (__all__, imported, public): {read.surface} vs {_OWNER_SURFACE}"
    )
    assert read.exported_not_imported == _OWNER_EXPORTED_NOT_IMPORTED, (
        f"the owner exports what this file does not import: {sorted(read.exported_not_imported)} "
        f"vs {sorted(_OWNER_EXPORTED_NOT_IMPORTED)}"
    )
    assert read.public_not_exported == _OWNER_PUBLIC_NOT_EXPORTED, (
        f"public by name yet missing from __all__: {sorted(read.public_not_exported)} "
        f"vs {sorted(_OWNER_PUBLIC_NOT_EXPORTED)}"
    )


def test_the_exit_read_map_is_measured_not_recited() -> None:
    """Every row of the table is recomputed here, so the map cannot age into a comment.

    This is the leg that makes the register a measurement rather than a transcription: it runs
    the same derivation over the file as it stands and diffs row by row. Moving a call from a
    leg into a helper is the edit this exists for -- the census still passes, the plane still
    answers, and the only number that moves is who reads what.
    """
    read = _read_map()
    found = {
        name: (tuple(sorted(row[0])), tuple(sorted(row[1])), len(row[2]))
        for name, row in read.rows.items()
    }
    added = sorted(set(found) - set(EXIT_READS))
    gone = sorted(set(EXIT_READS) - set(found))
    moved = sorted(name for name in set(found) & set(EXIT_READS) if found[name] != EXIT_READS[name])
    assert not added and not gone and not moved, (
        f"the read map drifted: new={added} gone={gone} changed={moved}"
    )

    totals = (
        sum(len(row[0]) for row in found.values()),
        sum(len(row[1]) for row in found.values()),
        sum(row[2] for row in found.values()),
    )
    assert totals == _EXIT_READ_INSTANCES, (
        f"relation instances moved: {totals} vs {_EXIT_READ_INSTANCES}"
    )


def test_an_exit_two_legs_execute_is_rostered_before_the_arm_that_bits_two() -> None:
    """The row that made this number exist.

    #548 arm E7 moved the axis's input and reddened two legs where the frozen prediction said
    one; #547 arm D5 did the same to a guard layer read through two fixtures. Neither was a
    reasoning error -- ``optional_publish_bands`` simply has two executors, and that was written
    down only in the table printed after the arms ran. Here it is written down before.
    """
    read = _read_map()
    multi = {name: len(row[0]) for name, row in read.rows.items() if len(row[0]) >= 2}
    assert multi == EXITS_WITH_MULTIPLE_EXECUTORS, (
        f"which exits more than one leg executes moved: {multi}"
    )

    axis_c = tuple(sorted(read.rows["optional_publish_bands"][0]))
    assert len(axis_c) == 2, (
        f"the axis now has {len(axis_c)} executors, and an arm on it is not one number"
    )
    assert axis_c == _AXIS_C_EXECUTORS, f"the executors of axis (c) changed identity: {axis_c}"
    assert len(read.rows["ruler_blind_spots"][0]) == 3, (
        "the blind-spot exit's executor count is what made #547 arm D6 worth running; it moved"
    )


def test_the_two_lenses_over_the_read_map_agree_leg_by_leg() -> None:
    """AST names and tokenized words, per leg, over the same import set.

    The tree lens could be stubbed into agreeing with the register it feeds -- ``return the
    frozen table`` is one line and every other leg in this file would stay green. The text lens
    cannot be stubbed the same way, because it does not look at the register: it rescans this
    file's own lines with strings and comments tokenized away. That they agree on every leg is
    the evidence that the table describes the file rather than the wish.

    The roster below is what the equation says about silence: eight legs read no exit directly.
    Four are #543/#544's roster legs, whose reads all go through ``_census`` and
    ``_checked_pairs``; four are this number's own, which read the map instead of the plane.
    "No direct read" and "no read" are the same zero, and only the helper hop tells them apart.
    """
    gate_src = Path(__file__).resolve().read_text(encoding="utf-8")
    lines = gate_src.splitlines()
    read = _read_map()

    disagreements: list[tuple[str, list[str], list[str]]] = []
    checked = 0
    for node in ast.parse(gate_src).body:
        if not isinstance(node, ast.FunctionDef) or not node.name.startswith("test_"):
            continue
        end = node.end_lineno or node.lineno
        words = _token_words(lines, node.lineno, end) & set(read.rows)
        named = _leg_direct_reads(read, node.name)
        checked += len(named)
        if words != named:
            disagreements.append((node.name, sorted(words - named), sorted(named - words)))

    assert not disagreements, (
        f"the two lenses disagree over {len(disagreements)} legs: {disagreements}"
    )
    assert checked == _DIRECT_RELATION_INSTANCES, (
        f"the cross-check has lost population: it compared {checked} relations, "
        f"expected {_DIRECT_RELATION_INSTANCES}"
    )
    quiet = sorted(leg for leg in read.legs if not _leg_direct_reads(read, leg))
    assert set(quiet) == LEGS_WITHOUT_DIRECT_READ, (
        f"legs that read no exit directly moved: {quiet} vs {sorted(LEGS_WITHOUT_DIRECT_READ)}"
    )


def test_the_read_map_generator_names_no_register_and_the_anchors_are_rostered() -> None:
    """⓳: the derivation may not read the numbers it is supposed to produce.

    #549's arm G7 put a ``return ReadMap(...)`` built from the registers at the top of
    ``_read_map`` and every leg stayed green -- 24 passed, and the instrument that diffs the
    read map against the landing tree said "same", because the registers were still accurate.
    So the honesty of this table does not live in the legs that read it; it lives in the step
    that generates it, and until this leg existed, nothing in the file said so.

    The ban is a scope, not a blanket. ``_read_map`` may name exactly one uppercase binding --
    ``REPO``, the root it reads this file and the owner from -- and no helper in the file may
    name any uppercase binding outside the three anchors below. The bind set is measured from
    the tree rather than typed out, so a register added by a later number falls under the ban
    the moment it exists instead of waiting to be rostered.
    """
    module = ast.parse(Path(__file__).resolve().read_text(encoding="utf-8"))
    funcs = {n.name: n for n in module.body if isinstance(n, ast.FunctionDef)}
    read = _read_map()
    binds = _uppercase_module_binds(module)
    registers = frozenset(_READ_MAP_REGISTERS)
    named = _helper_named_binds(funcs, binds)
    plane_named = _helper_named_binds(funcs, frozenset(read.rows))

    unbound = registers - binds
    assert not unbound, f"a register this leg audits is not a module binding: {sorted(unbound)}"

    violators = frozenset(name for name, hits in named.items() if hits & registers)
    assert violators == _HELPERS_NAMING_READ_MAP_REGISTERS, (
        f"helpers whose body names a read map register: "
        f"{sorted((name, sorted(named[name] & registers)) for name in violators)}"
    )
    assert named["_read_map"] == _READ_MAP_ANCHORS, (
        f"the generator names {sorted(named['_read_map'])} as its uppercase bindings; "
        f"the roster says {sorted(_READ_MAP_ANCHORS)}"
    )

    seen: set[str] = set()
    for hits in named.values():
        seen |= hits
    assert frozenset(seen) == _ANCHOR_BINDINGS, (
        f"the uppercase bindings this file's helpers reach moved: {sorted(seen)} "
        f"vs {sorted(_ANCHOR_BINDINGS)}"
    )
    assert not plane_named["_read_map"], (
        f"the map builder reads the plane it is mapping: {sorted(plane_named['_read_map'])}"
    )


def test_the_helper_hop_has_its_own_second_lens() -> None:
    """⓴: the helper hop stops being the one reading in this table with a single witness.

    #549 recorded the gap in its own 发现 4: the direct columns are checked by two lenses --
    ``ast`` and ``tokenize``, leg by leg over 34 relations -- while the 85 via relations were
    produced by the generator's stack walk and confirmed by nothing else. ``frozenset(range(n))``
    is enough to pass an assertion that compares only ``len()`` of a set, which is what arm G7
    reached for.

    The hop therefore gets a text lens: for every leg, take the helpers it reaches, rescan each
    helper's own lines with strings and comments tokenized away, and subtract what the leg reads
    itself. That has to *equal* the generator's via set on every leg -- equality rather than
    containment, because the probe measured no over-report on this tree, and containment is the
    shape a weakened lens hides behind.
    """
    gate_src = Path(__file__).resolve().read_text(encoding="utf-8")
    lines = gate_src.splitlines()
    funcs = {n.name: n for n in ast.parse(gate_src).body if isinstance(n, ast.FunctionDef)}
    read = _read_map()
    plane = frozenset(read.rows)

    closures = {leg: _helper_closure(funcs, leg) for leg in sorted(read.legs)}
    lens: dict[str, frozenset[str]] = {}
    for leg, closure in closures.items():
        own = frozenset(_leg_direct_reads(read, leg))
        reached: set[str] = set()
        for helper in closure:
            end = funcs[helper].end_lineno or funcs[helper].lineno
            reached |= _token_words(lines, funcs[helper].lineno, end) & plane
        lens[leg] = frozenset(reached) - own

    derived = {
        leg: frozenset(name for name, row in read.rows.items() if leg in row[2])
        for leg in closures
    }
    disagreements = sorted(leg for leg in closures if lens[leg] != derived[leg])
    assert not disagreements, (
        f"the text lens disagrees with the generator on {len(disagreements)} legs: "
        f"{[(leg, sorted(derived[leg] ^ lens[leg])) for leg in disagreements[:3]]}"
    )

    total = sum(len(names) for names in lens.values())
    via_total = sum(len(row[2]) for row in read.rows.values())
    assert (total, via_total) == (_EXIT_READ_INSTANCES[2], _EXIT_READ_INSTANCES[2]), (
        f"the hop lost or gained relations: lens {total}, register {via_total}, "
        f"frozen {_EXIT_READ_INSTANCES[2]}"
    )

    quiet = sorted(leg for leg in lens if not lens[leg])
    assert frozenset(quiet) == LEGS_WITHOUT_VIA_HELPER_READ, (
        f"legs whose helper hop brings back no plane name moved: {quiet} "
        f"vs {sorted(LEGS_WITHOUT_VIA_HELPER_READ)}"
    )

    edges = sum(len(closure) for closure in closures.values())
    assert edges == _CLOSURE_EDGE_TOTAL, (
        f"helper-reach edges over the legs moved: {edges} vs {_CLOSURE_EDGE_TOTAL}"
    )
    generators = frozenset(leg for leg, closure in closures.items() if "_read_map" in closure)
    stray = sorted(generators - LEGS_WITHOUT_VIA_HELPER_READ)
    assert not stray, (
        f"a leg that reaches the generator also reaches the plane through someone else: {stray}"
    )
    # Measured 6: #549's four map-reading legs and this number's two.
    assert len(generators) == 6, f"which legs reach the generator moved: {sorted(generators)}"

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
publishes it and nothing merged it). Five endpoints had anything to say, 8 + 3 + 0 + 2 keys
between them, and the row that mattered was ``/jobs``: ``api.ts`` records in prose why
``JobsPage.total`` must be required while ``Guide.tsx`` wrote its own inline
``total?: number``. #551 read that disagreement off this register and then repaired it, so
the axis is four rows and 7 + 3 + 0 + 2 keys today -- and the fifth place the same payload
is written down became a leg of its own.
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
module level by nothing that runs (one: ``Member``). 43 + 4 + 86 relations, and the number the
last two misses were about is ``EXITS_WITH_MULTIPLE_EXECUTORS``: ten exits have more than one
executor, including the two that made predictions wrong -- ``optional_publish_bands`` (#548 arm
E7 reddened two legs where the frozen prediction named one) and ``ruler_blind_spots`` (#547 arm
D5, the same shape reached through two fixtures). **A second lens** rescans each leg's own lines
with strings and comments tokenized away and agrees leg by leg over 47 direct relations, because
a register checked only by the parser that fills it has one witness. What it does not buy: arm
G7 replaced the derivation with the frozen table and all 24 legs stayed green, so the map's
honesty lives in the step that generates the register, not in the legs that read it.

#550 put a guard on that step and gave the hop its own witness. **The ban** reads the
generator's body from the tree: ``_read_map`` may name one uppercase binding (``REPO``, the
root) and no helper in this file may name an uppercase binding outside the three anchors --
so arm G7's ``return ReadMap(...)`` is now red instead of green, and the population that
would have made a blanket ban impossible is a roster, not an excuse. **The second lens over
``via``** walks each leg's helper closure, rescans those helpers' lines with strings and
comments tokenized away, and must *equal* the generator's set on all 34 legs and 86
relations: the column that had one witness now has two, and the twenty-one legs whose hop comes back
empty are named, because two empty sets agree for the wrong reason just as easily.

#551 read the fourth place, and changed a product file to do it. **Axis (d)** asks what the
call site's own body does with a key the route publishes: ``consumer_defences`` walks the
statement a request begins, classifies one absence-handling shape per guarded occurrence,
and joins it to the two words that matter -- how the site declares the key and what the route
does with it. Four rows on this tree, and the reading that produced them reaches 8 of the 48
paired sites, so the other 40 leave in the same register, by file, with their own count.
**The product half** is ``Guide.tsx``: it wrote its own inline ``total?: number`` where
``api.ts`` records in prose that the field is required -- two declarations of one response,
one of them weaker, the same shape #202 removed from ``Jobs.tsx``. The page is on the shared
type now and kept its ``typeof`` guard, because the two are not the same claim. Three
witnesses, none of them overlapping: ``tsc`` reports a guard only when the type still says
optional, ``vitest`` is the only thing that fails when a live guard is deleted, and this gate
is the only thing that records which guards exist at all.

#553 read the other 40, and the reach column turned out to be about binding. Its test is
``".then(" in region``, so the 8 it reports are eight sites whose response is handed to code in
the same statement -- not eight guarded sites, and not eight sites that even name a key of
their own payload. ``consumer_bindings`` labels all 48 with the one reason their statement
lens is empty (21 forward the payload whole, 7 sit in a ``Promise.all`` tuple, 3 give the read
to a hook, 5 bind with ``await``, 2 discard the response, 1 memoizes the promise, 1
destructures with a rename) and reads each through a second lens, the enclosing block. Two
numbers came out of that: the chain label and axis (d)'s reached column are the same eight
names by two independent walks, and of those eight exactly two read a payload key at all -- so
axis (d) speaks for 2 of 48, not 8. The block lens guards at five sites the statement never
saw, and the classifier gained the one shape those rows use, ``x.k || fallback``, ranked last
so it can only name an access nothing else claimed.

#554 read the same plane without asking a name. **E8** is a second denominator: the client
module's issuers are the definitions whose bodies reach a transport -- ``doFetch``,
``openEventStream`` and whatever calls either -- and a site is a line that writes one of those
names or writes a transport itself. 16 issuers, 105 sites, 58 outside ``api.ts``, and all 48
census rows are among them. What the naming ruler cannot say *by construction* is rostered: 21
rows whose written name is in no verb list (11 helpers ``api.ts`` exports, 5 functions that reach
the client module without the ``use[A-Z]`` spelling, 1 page that writes ``fetch`` itself), plus
16 rows it *does* name and still never counted -- eleven of them ``useAgentJob`` call sites,
because E6 names the hook and counts the one request inside its body. Two labels are about the
graph rather than a spelling, so they read ``issuer-def``/``issuer-call`` and not ``hook-*``:
only 3 of the tree's 7 page-level consumers carry the hook shape, and a vocabulary that called
them hooks would have been a label lying about a population. The reading's own hole is registered
as well -- it resolves brace imports only, so ``import * as client from './api'`` and a default
binding produce no row. Population 0 on this tree, and the fixture leg writes both shapes to
show the refusal belongs to the reading rather than to the tree's silence.
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
    DENOMINATOR_KINDS,
    CallShape,
    CallSite,
    ClientExport,
    ConsumerBinding,
    ConsumerDefence,
    DenominatorSite,
    Endpoint,
    Member,
    OptionalBand,
    Pair,
    _mask_prose,
    _mask_typescript,
    alias_table,
    call_shapes,
    client_surface,
    conditional_table,
    consumer_bindings,
    consumer_defences,
    denominator_sites,
    endpoints,
    frontend_calls,
    hook_readings,
    members_of_type,
    normalize_path,
    open_key_types,
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
#: What #555 removed is the entry that was *not* real: `("get", "/api/v1/admin/audit")`
#: carried `total` for six units, but the frontend declares that field at `Audit.tsx:41` --
#: a `;` inside the comment above it ended the member chunk, so the declaration existed and
#: the reading could not see it. An entry here means "nobody wrote it down", so a mask that
#: loses a line writes a false answer into the register that exists to catch lies.
ROSTERED_EXTRA_KEYS: dict[Key, frozenset[str]] = {
    ("get", "/agent/jobs"): frozenset({"next_offset"}),
    ("get", "/api/v1/jobs/{}/findings"): frozenset({"sources"}),
    # next_cursor arrived with the keyset cursor pagination (#1618/#1668bab).
    # Guide.tsx/Jobs.tsx pair the route with `JobsPage`, which DECLARES it
    # (optional, api.ts:445); Matrix.tsx pairs it with its inline
    # `{ jobs: Job[] }`, which declares neither it nor total — the union is
    # what this register records, so the key belongs here even though two of
    # the three pairs now owe it nothing.
    ("get", "/jobs"): frozenset({"limit", "offset", "total", "next_cursor"}),
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
#: -> ((declaring file, line), {band: keys}), empty bands left out. Four rows. Three of
#: them say a page is defending against something it does not need to, and health's two
#: ``absent`` keys say the page defends against a key that cannot arrive. The fifth row
#: was ``/jobs``, where a page had not been told about a decision ``api.ts`` already wrote
#: down in prose; #551 repaired it, and axis (d) below keeps the guard that survives it.
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
    # #1631: the row is back, keyed on the keyset cursor (#1668bab) — Guide.tsx
    # pairs with JobsPage, which declares `next_cursor?` (optional, api.ts:445),
    # so axis (d) files the key as optional and this register files it as
    # `always` in the route's own exits: the two registers still describe one
    # tree. `total` stays in axis (d)'s required column, untouched by #547.
    ("get", "/jobs"): (
        ("apps/web/src/pages/Guide.tsx", 74),
        {"always": ("next_cursor",)},
    ),
    ("post", "/api/v1/model/test"): (
        ("apps/web/src/agent/pages/AgentSettings.tsx", 91),
        {"overstated": ("usage",)},
    ),
}

#: The same register summed, because a row comparison alone cannot see keys moving
#: *between* bands on a route that keeps speaking: ``always`` 7 -> 10 and ``overstated``
#: 3 -> 0 is one line in the owner (arm E2) and leaves all four rows standing.
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
# #551 -- axis (d): what the consumer's own body does with a key the route publishes
#
# Axes (a) to (c) stop at the declaration. The fourth place a payload contract is written down is
# the call site's own body, and not reading it costs in both directions: a guard around a key the
# type says cannot be missing is real code that ``tsc`` cannot see -- deleting it is silent -- and
# a bare read of a key nobody declared stays latent only because the page renders ``undefined`` as
# nothing. The export answers both from one region walk and carries its own blind side with the
# answer, because most of the plane is out of reach: 40 of the 48 paired sites hand their response
# to a *later* statement, and this reading stops at the call. So what follows is a census of the
# quarter of the plane the reading reaches, and the reach registers are the size of the rest.


#: One row per guarded ``(site, key)``: ``(file, line, key)`` -> (verb, path, kind, declared,
#: published). Four rows on this tree. The one that carries a product decision is the last:
#: ``Guide.tsx`` guards ``total`` with ``typeof`` while the type it now imports says the key
#: cannot be missing -- ``vitest`` is that guard's only witness at runtime, and this register is
#: the only thing that records the guard exists. ``Audit.tsx`` is the other page guarding anything,
#: and all four of its rows now read ``required``: its ``total`` was ``undeclared`` until #555, when
#: a single prose rule made ``ts_declarations`` able to see the line the key is written on -- the
#: field is at ``Audit.tsx:41``, under a comment whose own ``;`` used to end the member chunk.
CONSUMER_DEFENCES: dict[tuple[str, int, str], tuple[str, str, str, str, str]] = {
    ("apps/web/src/pages/Audit.tsx", 145, "audit"): (
        "get",
        "/api/v1/admin/audit",
        "optchain",
        "required",
        "always",
    ),
    ("apps/web/src/pages/Audit.tsx", 145, "job_present"): (
        "get",
        "/api/v1/admin/audit",
        "nullish",
        "required",
        "always",
    ),
    ("apps/web/src/pages/Audit.tsx", 145, "total"): (
        "get",
        "/api/v1/admin/audit",
        "typeof",
        "required",
        "always",
    ),
    ("apps/web/src/pages/Guide.tsx", 74, "total"): ("get", "/jobs", "typeof", "required", "always"),
}

#: The same rows by declaration band, every band named including the empty one. ``optional`` is
#: zero here for the first time and it is this number's own doing: the page moved onto the shared
#: ``JobsPage``, whose ``total`` is required. The zero belongs in the register for the reason
#: #547 set -- it is a measurement, and the day a page writes ``total?: number`` again it moves
#: here rather than appearing only in a diff. ``undeclared`` joined it at #555: no guarded key on
#: this tree is missing from its frontend type, which is the reading the mask was blocking.
CONSUMER_DEFENCE_BANDS: dict[str, int] = {
    "required": 4,
    "optional": 0,
    "undeclared": 0,
}

#: And by defence shape. One kind per row, because the owner classifies per occurrence with a
#: stated precedence; the probe's five overlapping regexes counted ``data?.job_present ?? null``
#: three times, so the roster is where collapsing those to one is provable rather than asserted.
#: The three zero rows are shapes the classifier can report and this tree does not use.
CONSUMER_DEFENCE_KINDS: dict[str, int] = {
    "nullish": 1,
    "optchain": 1,
    "shape": 0,
    "ternary": 0,
    "typeof": 2,
    "undefined": 0,
}

#: ``(paired sites, sites whose response is handed to code in the same statement, sites it
#: is not)``. The third column is five times the second, so the four rows above are not a
#: census of the frontend
#: -- they are a census of the part of it this reading can see. A leg that reported only
#: the defences would be read as the claim the numbers here refuse.
CONSUMER_DEFENCE_REACH = (48, 8, 40)

#: Where the 40 are. ``api.ts`` owns 24 of them because it is the client library -- its calls hand
#: the payload back to a caller rather than consuming it -- and the rest are ``await`` pages that
#: read the result below the request. A page that starts guarding a key in the statement *after*
#: the call moves this register, not ``CONSUMER_DEFENCES``, which is the point of keeping the two
#: populations apart.
CONSUMER_DEFENCE_BLIND_BY_FILE: dict[str, int] = {
    "apps/web/src/agent/components.tsx": 1,
    "apps/web/src/agent/pages/AgentSettings.tsx": 2,
    "apps/web/src/api.ts": 24,
    "apps/web/src/pages/Billing.tsx": 4,
    "apps/web/src/pages/Contracts.tsx": 1,
    "apps/web/src/pages/JobDetail.tsx": 4,
    "apps/web/src/pages/Jobs.tsx": 1,
    "apps/web/src/pages/Login.tsx": 1,
    "apps/web/src/pages/Matrix.tsx": 2,
}

#: Reached sites that guard nothing: the reading looked and came back empty. Six rows, and they are
#: the population a substitution bug lands in -- a bare ``data.total`` under a required type reads
#: as a number until the day it does not. #202 removed exactly that shape from ``Jobs.tsx``; these
#: are the sites where nothing guards the key at all, which is a different claim from "not seen".
CONSUMER_DEFENCE_BARE_SITES: frozenset[tuple[str, int]] = frozenset(
    {
        ("apps/web/src/agent/pages/AgentSettings.tsx", 48),
        ("apps/web/src/pages/Dashboard.tsx", 30),
        ("apps/web/src/pages/Eval.tsx", 83),
        ("apps/web/src/pages/FindingDetail.tsx", 263),
        ("apps/web/src/pages/Health.tsx", 78),
        ("apps/web/src/pages/JobDetail.tsx", 290),
    }
)

#: Blind sites whose region still spans more than one line. The reach test is on the payload's
#: path, not the statement's height: a request written across seven argument lines extends the
#: region and reaches nothing. Measured, because "the region is longer" and "the consumer is
#: inside it" are the same claim only to a reading that never checks -- a length rule would have
#: reported 25 reached sites, 17 of which contain no consumer at all.
CONSUMER_DEFENCE_BLIND_LONG_REGION = 18


# ---------------------------------------------------------------------------
# #553 -- axis (d)'s other half: how every paired site *binds* its response
#
# ``CONSUMER_DEFENCE_REACH`` says 40 of the 48 paired sites are blind to the statement lens.
# It does not say why, and the why is not one population: 21 of them are ``api.ts`` handing the
# payload back to a caller, 7 sit inside a ``Promise.all`` tuple and wait for its callback, 3
# give the read to a hook, 5 bind with ``await`` and guard two lines below, 2 discard the
# response, 1 parks its promise in an in-flight memo variable, and 1 destructures with a
# rename (``const { job: current } = await ...``). ``consumer_bindings`` labels each site with
# exactly one reason -- the style vocabulary is ordered and first match wins, so the order is
# the definition -- and reads the site through two lenses: the statement axis (d) can see, and
# the enclosing block it cannot.
#
# Two numbers here are cross-checks rather than measurements. The ``then-chain`` count equals
# ``CONSUMER_DEFENCE_REACH[1]`` although the two exports walk the plane differently, and the
# statement lens finds a key at 3 sites while axis (d) has defences at 2 -- which is what the
# third site's row is about. The rest is the census the old reach column only hinted at.

#: Style -> how many paired sites carry it. Keyed in the owner's precedence order, so the
#: register reads as the rule that produced it; ``sum`` is 48 and there is no ``other``.
#: ``forward`` is a third of the plane and is not a defect: a client library that returns the
#: payload whole has no guard to write. ``destructuring`` is one site and it is the reading's
#: own limit: ``JobDetail.tsx`` renames ``job`` to ``current`` on the way in, so every later
#: ``current.status`` sits outside a key-name-anchored walk.
CONSUMER_BINDING_STYLES: dict[str, int] = {
    "forward": 21,
    "then-chain": 8,
    "tuple-member": 7,
    "await-binding": 5,
    "hook": 3,
    "discarded": 2,
    "promise-bound": 1,
    "destructuring": 1,
}

#: The same census by name: style -> the sites carrying it, so an arm that relabels one
#: site moves a roster and not merely a count. A count-only register would let a
#: implementation that assigns styles by position pass every leg here.
CONSUMER_BINDING_ROSTER: dict[str, tuple[tuple[str, int], ...]] = {
    "forward": (
        ("apps/web/src/api.ts", 457),
        ("apps/web/src/api.ts", 472),
        ("apps/web/src/api.ts", 590),
        ("apps/web/src/api.ts", 597),
        ("apps/web/src/api.ts", 1000),
        ("apps/web/src/api.ts", 1008),
        ("apps/web/src/api.ts", 1017),
        ("apps/web/src/api.ts", 1027),
        ("apps/web/src/api.ts", 1046),
        ("apps/web/src/api.ts", 1055),
        ("apps/web/src/api.ts", 1061),
        ("apps/web/src/api.ts", 1110),
        ("apps/web/src/api.ts", 1151),
        ("apps/web/src/api.ts", 1158),
        ("apps/web/src/api.ts", 1166),
        ("apps/web/src/api.ts", 1170),
        ("apps/web/src/api.ts", 1174),
        ("apps/web/src/api.ts", 1181),
        ("apps/web/src/api.ts", 1188),
        ("apps/web/src/api.ts", 1198),
        ("apps/web/src/api.ts", 1202),
    ),
    "then-chain": (
        ("apps/web/src/agent/pages/AgentSettings.tsx", 48),
        ("apps/web/src/pages/Audit.tsx", 145),
        ("apps/web/src/pages/Dashboard.tsx", 30),
        ("apps/web/src/pages/Eval.tsx", 83),
        ("apps/web/src/pages/FindingDetail.tsx", 263),
        ("apps/web/src/pages/Guide.tsx", 74),
        ("apps/web/src/pages/Health.tsx", 78),
        ("apps/web/src/pages/JobDetail.tsx", 290),
    ),
    "tuple-member": (
        ("apps/web/src/pages/Billing.tsx", 313),
        ("apps/web/src/pages/Billing.tsx", 314),
        ("apps/web/src/pages/Billing.tsx", 315),
        ("apps/web/src/pages/Billing.tsx", 318),
        ("apps/web/src/pages/JobDetail.tsx", 222),
        ("apps/web/src/pages/JobDetail.tsx", 223),
        ("apps/web/src/pages/JobDetail.tsx", 224),
    ),
    "await-binding": (
        ("apps/web/src/agent/components.tsx", 66),
        ("apps/web/src/agent/pages/AgentSettings.tsx", 73),
        ("apps/web/src/api.ts", 1228),
        ("apps/web/src/api.ts", 1240),
        ("apps/web/src/pages/Jobs.tsx", 58),
    ),
    "hook": (
        ("apps/web/src/pages/Contracts.tsx", 17),
        ("apps/web/src/pages/Matrix.tsx", 21),
        ("apps/web/src/pages/Matrix.tsx", 22),
    ),
    "discarded": (
        ("apps/web/src/agent/pages/AgentSettings.tsx", 91),
        ("apps/web/src/pages/Login.tsx", 84),
    ),
    "promise-bound": (
        ("apps/web/src/api.ts", 1138),
    ),
    "destructuring": (
        ("apps/web/src/pages/JobDetail.tsx", 241),
    ),
}

#: What the statement lens -- the region axis (d) reads -- actually finds a key at.
#: Three sites, ``(accesses, defence shapes)``. Only two of them have a shape: the
#: third reads ``config.base_url``/``.model``/``.protocol``/``.reasoning_effort`` inside
#: the *request* body of ``POST /api/v1/agent/config``, keys that the response type also
#: declares, so a key-name-anchored reading cannot tell the two planes apart and reports
#: four accesses and no defence. That row is the boundary of this ruler, registered
#: rather than quietly dropped.
CONSUMER_BINDING_STATEMENT_READS: dict[
    tuple[str, int],
    tuple[tuple[str, ...], tuple[str, ...]],
] = {
    ("apps/web/src/agent/pages/AgentSettings.tsx", 73): (
        ("config.base_url", "config.model", "config.protocol", "config.reasoning_effort"),
        (),
    ),
    ("apps/web/src/pages/Audit.tsx", 145): (
        ("data.audit", "data.job_present", "data.total"),
        ("audit:optchain", "job_present:nullish", "total:typeof"),
    ),
    ("apps/web/src/pages/Guide.tsx", 74): (
        ("data.total",),
        ("total:typeof",),
    ),
}

#: Guards the enclosing block has and the statement never sees, by site. These are
#: *other* rows than ``CONSUMER_DEFENCES``: no site here appears there, and a key
#: guarded twice in one block (``x?.k`` and ``x.k ?? y``) is two rows in this register
#: and one ``(site, key)`` in axis (d) -- the two columns are deliberately not merged.
#: ``Jobs.tsx`` and ``JobDetail.tsx``/``Matrix.tsx`` write the fallback with ``||``, the
#: shape axis (d)'s classifier did not have a name for until #553.
CONSUMER_BINDING_BLOCK_GUARDS: dict[tuple[str, int], tuple[str, ...]] = {
    ("apps/web/src/pages/Contracts.tsx", 17): ("contracts:nullish", "contracts:optchain"),
    ("apps/web/src/pages/JobDetail.tsx", 222): ("summary:logical-or",),
    ("apps/web/src/pages/Jobs.tsx", 58): ("jobs:logical-or", "next_cursor:nullish"),
    ("apps/web/src/pages/Matrix.tsx", 21): ("jobs:nullish", "jobs:optchain"),
    ("apps/web/src/pages/Matrix.tsx", 22): (
        "degraded_reason:logical-or",
        "rows:nullish",
        "rows_total:nullish",
    ),
}

#: ``(sites, shape rows, distinct (site, key))`` for the register above: 5 /
#: 9 / 7. The third column is smaller because two sites guard one key
#: in two shapes, and keeping both counts is what makes the flattening mistake visible.
CONSUMER_BINDING_BLOCK_TOTALS = (5, 10, 8)

#: Every ``x.k || fallback`` access in either lens: ``(file, line, key)``, three rows.
#: The shape is ranked last in the classifier, so these three are accesses nothing else
#: claimed -- a ``?.`` or ``??`` on the same access wins and lands in the registers above
#: instead. A fallback that is a disjunction is still a fallback: ``data.jobs || []``
#: turns a missing key into an empty list and is what keeps a live guard in ``vitest``.
CONSUMER_BINDING_LOGICAL_OR: tuple[tuple[str, int, str], ...] = (
    ("apps/web/src/pages/JobDetail.tsx", 222, "summary"),
    ("apps/web/src/pages/Jobs.tsx", 58, "jobs"),
    ("apps/web/src/pages/Matrix.tsx", 22, "degraded_reason"),
)

#: The 7 tuple members split by whether the tuple statement reaches the ``.then`` that
#: consumes them. ``Billing.tsx`` calls ``Promise.all`` and hands the destructured tuple
#: to a callback; ``JobDetail.tsx`` calls ``allSettled`` and reads below the request, so
#: the guard it writes is in the block register above and never in axis (d).
CONSUMER_BINDING_TUPLE_THEN: frozenset[tuple[str, int]] = frozenset(
    {
        ("apps/web/src/pages/Billing.tsx", 313),
        ("apps/web/src/pages/Billing.tsx", 314),
        ("apps/web/src/pages/Billing.tsx", 315),
        ("apps/web/src/pages/Billing.tsx", 318),
    }
)
CONSUMER_BINDING_TUPLE_NO_THEN: frozenset[tuple[str, int]] = frozenset(
    {
        ("apps/web/src/pages/JobDetail.tsx", 222),
        ("apps/web/src/pages/JobDetail.tsx", 223),
        ("apps/web/src/pages/JobDetail.tsx", 224),
    }
)

#: Forwarding sites that read a payload key in either lens. Measured empty, and named
#: because the claim it tests is a property, not a count: a site that hands the payload
#: to its caller *while also* guarding a key of its own would make ``forward`` a reason
#: for blindness and a contradiction in the same row. One arm (K5) turns a forward into
#: a destructure-and-read and this register is what reports it.
CONSUMER_BINDING_FORWARD_READS: frozenset[tuple[str, int]] = frozenset()

#: Sites whose enclosing block the walker refused to resolve, so the block lens read
#: nothing -- ``block_span`` 0. All seven are ``api.ts`` wrappers whose signature
#: spreads over more than two lines: the body's ``{`` closes the parameter list, and the
#: head test reads the opener line and the one above it, so it never reaches the
#: ``function`` keyword. Registered because an empty read and a refused read look
#: identical in a count, and this campaign has been burned from both sides of that
#: distinction -- refusing is honest only while the refusal is named.
CONSUMER_BINDING_UNREAD_BLOCKS: frozenset[tuple[str, int]] = frozenset(
    {
        ("apps/web/src/api.ts", 597),
        ("apps/web/src/api.ts", 1000),
        ("apps/web/src/api.ts", 1017),
        ("apps/web/src/api.ts", 1055),
        ("apps/web/src/api.ts", 1158),
        ("apps/web/src/api.ts", 1198),
        ("apps/web/src/api.ts", 1240),
    }
)


# ---------------------------------------------------------------------------
# #554 -- the denominator: who can reach the wire, read from the import graph
#
# Every consumer number above rests on one declaration: `_consumer_names` is the five `api*`
# verbs plus the `use[A-Z]` hooks whose body issues exactly one request. #553's arm K8 renamed
# `useRemoteData` and five legs went red, which is the same fact seen from the wrong side -- a
# naming convention was holding up a population, and the population itself was registered
# nowhere. E8 reads the identical plane without asking a name: an issuer is a client-module
# definition whose body reaches a transport, directly or through another issuer; an issuer of
# the second kind is any other frontend function whose body reaches one of those; a site is a
# line that writes one of those names, or writes a transport itself.
#
# What follows is therefore a *difference* three ways over: the closure's own roster, the rows
# the naming ruler has no name for, and the rows it names but never counts. The last of the
# three is the one that was not on the prediction sheet -- a consumer E6 can name is not the
# same claim as a consumer E6 can count.
# ---------------------------------------------------------------------------

#: name -> (declaration line, graph depth, exported?, the client names its body writes). The 16
#: rows are the closure, not a list of api clients: `downloadCapsule`, `logout` and the two
#: stream wrappers are in it because of what they *call*, and nothing in the reading was told
#: those names. ``via`` is what tells a stream from a helper -- the word in the name says nothing.
CLIENT_ISSUER_ROSTER: dict[str, tuple[int, int, bool, tuple[str, ...]]] = {
    "doFetch": (194, 0, False, ()),
    "openEventStream": (274, 0, False, ()),
    "apiDelete": (947, 1, True, ("doFetch",)),
    "apiGet": (203, 1, True, ("doFetch",)),
    "apiPost": (952, 1, True, ("doFetch",)),
    "createFindingFeedback": (593, 1, True, ("apiPost",)),
    "downloadCapsule": (363, 1, True, ("doFetch",)),
    "getAgentDiff": (1060, 1, True, ("apiGet",)),
    "getAuthConfig": (1109, 1, True, ("apiGet",)),
    "getInvoiceByPeriod": (1227, 1, True, ("apiGet",)),
    "getJobFeedback": (589, 1, True, ("apiGet",)),
    "logout": (149, 1, True, ("doFetch",)),
    "openAgentEventStream": (969, 1, True, ("openEventStream",)),
    "openProgressStream": (259, 1, True, ("openEventStream",)),
    "prepareDemoRepo": (471, 1, True, ("apiPost",)),
    "transitionInvoiceStatus": (1236, 1, True, ("apiPost",)),
}

#: How many issuers sit at each graph distance from a transport. The absence of a ``2`` is the
#: tier-3 zero: this client module has no helper-of-a-helper, so the closure converges in the
#: round that seeds depth 1 and the round after it adds nothing.
CLIENT_ISSUER_DEPTH_BANDS: dict[int, int] = {0: 2, 1: 14}

#: Per *declared* client verb: rows in the closure that define it, call-shaped mentions in
#: product files, page rows that bind it. Two of the five declarations are written nowhere at
#: all, and one is defined and used only inside ``api.ts`` -- which is why the census could say
#: "five verbs" for as long as it liked and no number in the repository moved when it was wrong.
CLIENT_VERB_POPULATION: dict[str, tuple[int, int, int]] = {
    "apiGet": (1, 32, 20),
    "apiPost": (1, 15, 2),
    "apiPut": (0, 0, 0),
    "apiPatch": (0, 0, 0),
    "apiDelete": (1, 2, 0),
}

#: Exported issuers that no page ever binds. ``doFetch`` and ``openEventStream`` stay out: they
#: are not exported, so a page cannot reach them by construction rather than by accident.
EXPORTED_ISSUERS_WITHOUT_A_PAGE_SITE: frozenset[str] = frozenset({"apiDelete"})

#: ``(rows, page-side rows, client-module rows)``. The last number is the client module talking
#: to itself -- 47 lines inside ``api.ts`` that write one of its own issuers -- and it is in the
#: same register because a denominator that only counted callers would hide the layer where a
#: helper is allowed to stop being one.
DENOMINATOR_ROW_TOTALS = (105, 58, 47)

#: Page-side rows per class. ``verb-name`` is what the naming ruler also sees; the other five
#: classes are what it cannot say by construction.
DENOMINATOR_PAGE_KINDS: dict[str, int] = {
    "helper": 11,
    "issuer-call": 15,
    "issuer-def": 7,
    "raw-transport": 1,
    "stream": 2,
    "verb-name": 22,
}

#: (file, line, kind, binding) for every page row whose *written* name is not in
#: ``_consumer_names``. 21 rows over 9 files: 11 of them are the helpers ``api.ts`` exports and
#: no verb list ever mentioned, 5 are functions that reach the client module without the
#: `use[A-Z]` spelling, and 1 is a page that asked the network a question itself.
DENOMINATOR_PAGE_BLIND: frozenset[tuple[str, int, str, str]] = frozenset(
    {
        ("apps/web/src/App.tsx", 75, "issuer-def", "Workspace"),
        ("apps/web/src/App.tsx", 131, "helper", "logout"),
        ("apps/web/src/agent/components.tsx", 33, "stream", "openAgentEventStream"),
        ("apps/web/src/agent/pages/AgentDiffViewer.tsx", 8, "issuer-def", "useDiff"),
        ("apps/web/src/agent/pages/AgentDiffViewer.tsx", 15, "helper", "getAgentDiff"),
        ("apps/web/src/agent/pages/AgentDiffViewer.tsx", 36, "issuer-call", "useDiff"),
        ("apps/web/src/pages/Billing.tsx", 394, "raw-transport", ""),
        ("apps/web/src/pages/FindingDetail.tsx", 48, "issuer-def", "FeedbackSection"),
        ("apps/web/src/pages/FindingDetail.tsx", 65, "helper", "getJobFeedback"),
        ("apps/web/src/pages/FindingDetail.tsx", 129, "helper", "createFindingFeedback"),
        ("apps/web/src/pages/FindingDetail.tsx", 346, "helper", "downloadCapsule"),
        ("apps/web/src/pages/JobDetail.tsx", 124, "issuer-def", "findingColumns"),
        ("apps/web/src/pages/JobDetail.tsx", 160, "helper", "downloadCapsule"),
        ("apps/web/src/pages/JobDetail.tsx", 174, "issuer-def", "JobDetail"),
        ("apps/web/src/pages/JobDetail.tsx", 249, "stream", "openProgressStream"),
        ("apps/web/src/pages/JobDetail.tsx", 306, "helper", "getInvoiceByPeriod"),
        ("apps/web/src/pages/JobDetail.tsx", 381, "helper", "transitionInvoiceStatus"),
        ("apps/web/src/pages/JobDetail.tsx", 628, "issuer-call", "findingColumns"),
        ("apps/web/src/pages/JobDetail.tsx", 669, "helper", "downloadCapsule"),
        ("apps/web/src/pages/Login.tsx", 54, "helper", "getAuthConfig"),
        ("apps/web/src/pages/NewVerification.tsx", 129, "helper", "prepareDemoRepo"),
    }
)

#: Rows the naming ruler *can* name and the census still never produced, as
#: (file, line, kind, binding). Eleven of the 16 are `useAgentJob` call sites: E6 names the hook,
#: the census counts the one request inside its body, and the ten pages that call it are nobody's
#: consumer. The other five are the two stream wrappers' home file, the three client verbs' own
#: declaration lines, and the ``apiGet`` inside ``useRemoteData`` whose path arrives from a caller.
DENOMINATOR_NAMED_WITHOUT_A_CENSUS_ROW: frozenset[tuple[str, int, str, str]] = frozenset(
    {
        ("apps/web/src/agent/components.tsx", 12, "issuer-def", "useAgentJob"),
        ("apps/web/src/agent/pages/AgentDiffViewer.tsx", 35, "issuer-call", "useAgentJob"),
        ("apps/web/src/agent/pages/AgentEdits.tsx", 13, "issuer-call", "useAgentJob"),
        ("apps/web/src/agent/pages/AgentEventLog.tsx", 10, "issuer-call", "useAgentJob"),
        ("apps/web/src/agent/pages/AgentGates.tsx", 29, "issuer-call", "useAgentJob"),
        ("apps/web/src/agent/pages/AgentJobApprovals.tsx", 9, "issuer-call", "useAgentJob"),
        ("apps/web/src/agent/pages/AgentJobDetail.tsx", 48, "issuer-call", "useAgentJob"),
        ("apps/web/src/agent/pages/AgentPlanReview.tsx", 9, "issuer-call", "useAgentJob"),
        ("apps/web/src/agent/pages/AgentPlanStep.tsx", 9, "issuer-call", "useAgentJob"),
        ("apps/web/src/agent/pages/AgentResult.tsx", 104, "issuer-call", "useAgentJob"),
        ("apps/web/src/agent/pages/AgentToolStream.tsx", 56, "issuer-call", "useAgentJob"),
        ("apps/web/src/api.ts", 203, "internal", "apiGet"),
        ("apps/web/src/api.ts", 947, "internal", "apiDelete"),
        ("apps/web/src/api.ts", 952, "internal", "apiPost"),
        ("apps/web/src/hooks/useRemoteData.ts", 5, "issuer-def", "useRemoteData"),
        ("apps/web/src/hooks/useRemoteData.ts", 32, "verb-name", "apiGet"),
    }
)

#: (file, line, callee, binding) where the page renamed what it imported. Population 0 on this
#: tree, and the reading handles it rather than measuring it, because renaming is the edit #553's
#: arm K8 proved a lane will actually make: the fixture leg writes two rows of this shape, so
#: this zero is a measurement and not the shape of a hole.
DENOMINATOR_ALIASED_SITES: frozenset[tuple[str, int, str, str]] = frozenset()

#: name -> (file, declaration line) for every frontend function *outside* the client module whose
#: body reaches an issuer. This is the graph's consumer population, and only 3 of the 7 rows carry
#: the `use[A-Z]` shape the naming ruler reads -- the other four are two components, the app shell
#: and a column factory, each of which asks the network a question in its own body.
PAGE_ISSUER_POPULATION: dict[str, tuple[str, int]] = {
    "FeedbackSection": ("apps/web/src/pages/FindingDetail.tsx", 48),
    "JobDetail": ("apps/web/src/pages/JobDetail.tsx", 174),
    "Workspace": ("apps/web/src/App.tsx", 75),
    "findingColumns": ("apps/web/src/pages/JobDetail.tsx", 124),
    "useAgentJob": ("apps/web/src/agent/components.tsx", 12),
    "useDiff": ("apps/web/src/agent/pages/AgentDiffViewer.tsx", 8),
    "useRemoteData": ("apps/web/src/hooks/useRemoteData.ts", 5),
}

#: The rows of that population E6's name pattern cannot see, and cannot be taught to.
PAGE_ISSUERS_WITHOUT_USE_SHAPE: frozenset[str] = frozenset(
    {"FeedbackSection", "JobDetail", "Workspace", "findingColumns"}
)

#: Sites per callee over the page rows the census never saw. `useAgentJob` is the fan-out a
#: naming reading reports as *one* consumer: eleven call sites, one census row. `fetch` is in
#: here under the word it wrote, since a page that bypassed the client module has no binding.
PAGE_ISSUER_FANOUT: dict[str, int] = {
    "useAgentJob": 11,
    "downloadCapsule": 3,
    "findingColumns": 2,
    "useDiff": 2,
    "FeedbackSection": 1,
    "JobDetail": 1,
    "Workspace": 1,
    "apiGet": 1,
    "createFindingFeedback": 1,
    "fetch": 1,
    "getAgentDiff": 1,
    "getAuthConfig": 1,
    "getInvoiceByPeriod": 1,
    "getJobFeedback": 1,
    "logout": 1,
    "openAgentEventStream": 1,
    "openProgressStream": 1,
    "prepareDemoRepo": 1,
    "transitionInvoiceStatus": 1,
    "useRemoteData": 1,
}

#: (file, line, transport word) for a page that asks the network a question without the client
#: module. ``Billing.tsx`` builds a CSV url out of an invoice payload and posts it straight to
#: ``fetch``: no name-anchored reading of any kind has a row for it, and no payload key either,
#: which is why this is the one register in this section with a population of one.
RAW_TRANSPORT_SITES: frozenset[tuple[str, int, str]] = frozenset(
    {("apps/web/src/pages/Billing.tsx", 394, "fetch")}
)

#: Page rows that open a stream instead of a request. Both reach ``openEventStream``, which no
#: declared verb ever reaches -- that is the fact the ``stream`` label is built on, and it is a
#: fact about the wire rather than about a word.
STREAM_SITES: frozenset[tuple[str, int, str]] = frozenset(
    {
        ("apps/web/src/agent/components.tsx", 33, "openAgentEventStream"),
        ("apps/web/src/pages/JobDetail.tsx", 249, "openProgressStream"),
    }
)



#: (file relative to ``apps/web/src``, line) for an import of the client module that binds
#: anything other than a brace list -- ``import * as client from './api'`` or
#: ``import api from './api'``. The reading resolves only braces, so a page that calls
#: ``client.apiGet(...)`` has no row here and no row anywhere: this is the registered hole, and
#: population 0 means no file on this tree writes that shape today. The fixture leg proves the
#: reading really does refuse it, which is what makes this zero a measurement.
CLIENT_MODULE_NON_BRACE_IMPORTS: frozenset[tuple[str, int]] = frozenset()


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
    "CallSite": ((), (), 12),
    "ClientExport": ((), (), 2),
    "ConsumerBinding": (
        (),
        ("test_every_paired_site_leaves_the_binding_census_with_exactly_one_reason",),
        0,
    ),
    "ConsumerDefence": ((), (), 1),
    "DENOMINATOR_KINDS": (
        ("test_the_denominator_is_wider_than_the_census_by_two_rosters_and_no_hand_wave",),
        (),
        0,
    ),
    "DenominatorSite": ((), (), 1),
    "Endpoint": (
        (),
        (
            "test_an_optional_key_is_rostered_in_the_band_the_route_puts_it_in",
            "test_the_conditional_register_is_measured_not_recited",
            "test_the_unbound_register_names_the_routes_that_cannot_be_folded_and_does_not_lie",
        ),
        9,
    ),
    "Member": ((), (), 0),
    "OptionalBand": ((), (), 1),
    "Pair": ((), (), 12),
    "_mask_prose": (
        (
            "test_the_mask_blanks_prose_only_and_the_shape_step_blanks_literals_only",
            "test_the_prose_mask_is_one_rule_applied_to_a_file_never_to_a_line",
        ),
        (),
        5,
    ),
    "_mask_typescript": (
        ("test_the_mask_blanks_prose_only_and_the_shape_step_blanks_literals_only",),
        (),
        0,
    ),
    "alias_table": (("test_the_path_aliases_the_fold_rewrites_are_rostered_whole",), (), 0),
    "call_shapes": (
        (
            "test_a_declared_client_verb_the_tree_never_writes_is_a_row_not_an_assumption",
            "test_a_request_mention_written_only_in_prose_makes_no_row_in_any_lens",
            "test_the_definition_guard_rejects_only_definitions",
        ),
        (),
        0,
    ),
    "client_surface": (
        (
            "test_a_declared_client_verb_the_tree_never_writes_is_a_row_not_an_assumption",
            "test_a_page_that_writes_fetch_itself_is_a_site_that_no_name_reading_can_ever_see",
            "test_a_request_mention_written_only_in_prose_makes_no_row_in_any_lens",
            "test_the_client_surface_is_a_closure_over_transports_not_a_list_of_clients",
            "test_the_shapes_this_tree_never_writes_still_produce_rows_when_a_fixture_writes_them",
        ),
        (),
        0,
    ),
    "conditional_table": (
        (
            "test_the_conditional_branches_the_fold_rewrites_are_rostered_whole",
            "test_the_fold_stops_where_the_caller_stopped_spelling_a_path",
            "test_the_three_conditional_guards_each_carry_their_own_case",
        ),
        (),
        0,
    ),
    "consumer_bindings": (
        (
            "test_a_disjunction_fallback_is_a_shape_and_the_precedence_keeps_the_chain_first",
            "test_a_page_that_writes_fetch_itself_is_a_site_that_no_name_reading_can_ever_see",
            "test_a_tuple_member_is_counted_by_whether_the_tuple_hands_its_responses_over",
            "test_a_wrapper_that_forwards_the_payload_whole_reads_no_key_in_either_lens",
            "test_every_paired_site_leaves_the_binding_census_with_exactly_one_reason",
            "test_the_block_lens_adds_a_guard_population_axis_d_never_saw",
            "test_the_denominator_is_wider_than_the_census_by_two_rosters_and_no_hand_wave",
            "test_the_graphs_consumer_population_is_seven_names_and_only_three_are_hooks",
            "test_the_statement_lens_reads_a_key_at_three_sites_and_defends_at_two",
        ),
        (),
        0,
    ),
    "consumer_defences": (
        (
            "test_a_defence_on_a_key_the_route_always_publishes_is_rostered",
            "test_the_block_lens_adds_a_guard_population_axis_d_never_saw",
            "test_the_reading_reaches_the_consumer_only_where_the_response_is_handed_over",
            "test_the_statement_lens_reads_a_key_at_three_sites_and_defends_at_two",
        ),
        (),
        0,
    ),
    "denominator_sites": (
        (
            "test_a_declared_client_verb_the_tree_never_writes_is_a_row_not_an_assumption",
            "test_a_page_that_writes_fetch_itself_is_a_site_that_no_name_reading_can_ever_see",
            "test_a_request_mention_written_only_in_prose_makes_no_row_in_any_lens",
            "test_the_denominator_is_wider_than_the_census_by_two_rosters_and_no_hand_wave",
            "test_the_graphs_consumer_population_is_seven_names_and_only_three_are_hooks",
            "test_the_shapes_this_tree_never_writes_still_produce_rows_when_a_fixture_writes_them",
        ),
        (),
        0,
    ),
    "endpoints": (("test_the_routes_this_gate_invents_exist_only_in_its_own_prose",), (), 12),
    "frontend_calls": (
        (
            "test_a_hook_that_issues_two_requests_is_refused_and_says_so",
            "test_a_request_mention_written_only_in_prose_makes_no_row_in_any_lens",
            "test_the_census_measures_a_population_rather_than_a_sample",
            "test_the_conditional_branches_the_fold_rewrites_are_rostered_whole",
            "test_the_fold_stops_where_the_caller_stopped_spelling_a_path",
            "test_the_hook_consumers_are_measured_from_their_own_bodies",
            "test_the_splitter_boundary_population_is_zero_on_the_tree",
            "test_the_three_conditional_guards_each_carry_their_own_case",
        ),
        (),
        0,
    ),
    "hook_readings": (
        (
            "test_a_hook_that_issues_two_requests_is_refused_and_says_so",
            "test_a_request_mention_written_only_in_prose_makes_no_row_in_any_lens",
            "test_the_graphs_consumer_population_is_seven_names_and_only_three_are_hooks",
            "test_the_hook_consumers_are_measured_from_their_own_bodies",
        ),
        (),
        0,
    ),
    "members_of_type": (
        (
            "test_an_inline_type_expression_is_masked_before_members_are_read",
            "test_the_six_fields_a_comment_swallowed_are_declared_and_typed_as_written",
        ),
        (),
        3,
    ),
    "normalize_path": (
        (
            "test_sites_with_no_readable_declared_type_are_rostered",
            "test_the_routes_this_gate_invents_exist_only_in_its_own_prose",
        ),
        (),
        8,
    ),
    "optional_publish_bands": (
        (
            "test_an_optional_key_is_rostered_in_the_band_the_route_puts_it_in",
            "test_the_fold_reports_every_return_the_handler_can_take",
        ),
        (),
        0,
    ),
    "open_key_types": (
        (
            "test_every_member_chunk_the_splitter_keeps_or_drops_is_counted",
            "test_the_comparison_ledger_accounts_for_every_pair",
            "test_the_open_key_types_are_the_chunks_the_splitter_used_to_lose",
            "test_the_splitter_boundary_population_is_zero_on_the_tree",
        ),
        (),
        2,
    ),
    "pairings": (
        (
            "test_every_paired_site_leaves_the_binding_census_with_exactly_one_reason",
            "test_the_reading_reaches_the_consumer_only_where_the_response_is_handed_over",
        ),
        (),
        12,
    ),
    "payload_of": (
        (
            "test_a_required_key_is_published_by_every_return_branch",
            "test_an_optional_key_is_rostered_in_the_band_the_route_puts_it_in",
            "test_published_keys_the_frontend_never_declared_are_rostered",
            "test_the_conditional_register_is_measured_not_recited",
            "test_the_unbound_register_names_the_routes_that_cannot_be_folded_and_does_not_lie",
        ),
        (),
        1,
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
    "ts_declarations": (
        (
            "test_every_member_chunk_the_splitter_keeps_or_drops_is_counted",
            "test_prose_cannot_invent_a_member",
            "test_the_body_cut_steps_over_literals",
            "test_the_literal_text_survives_the_member_reading",
            "test_the_open_key_types_are_the_chunks_the_splitter_used_to_lose",
            "test_the_six_fields_a_comment_swallowed_are_declared_and_typed_as_written",
            "test_the_splitter_boundary_population_is_zero_on_the_tree",
        ),
        (),
        12,
    ),
    "web_src": (
        (
            "test_a_declared_client_verb_the_tree_never_writes_is_a_row_not_an_assumption",
            "test_a_page_that_writes_fetch_itself_is_a_site_that_no_name_reading_can_ever_see",
            "test_a_request_mention_written_only_in_prose_makes_no_row_in_any_lens",
            "test_every_member_chunk_the_splitter_keeps_or_drops_is_counted",
            "test_the_body_cut_steps_over_literals",
            "test_the_census_measures_a_population_rather_than_a_sample",
            "test_the_comparison_ledger_accounts_for_every_pair",
            "test_the_conditional_branches_the_fold_rewrites_are_rostered_whole",
            "test_the_definition_guard_rejects_only_definitions",
            "test_the_graphs_consumer_population_is_seven_names_and_only_three_are_hooks",
            "test_the_hook_consumers_are_measured_from_their_own_bodies",
            "test_the_literal_text_survives_the_member_reading",
            "test_the_mask_blanks_prose_only_and_the_shape_step_blanks_literals_only",
            "test_the_open_key_types_are_the_chunks_the_splitter_used_to_lose",
            "test_the_path_aliases_the_fold_rewrites_are_rostered_whole",
            "test_the_prose_mask_is_one_rule_applied_to_a_file_never_to_a_line",
            "test_the_shapes_the_ruler_sees_and_does_not_read_are_rostered",
            "test_the_six_fields_a_comment_swallowed_are_declared_and_typed_as_written",
            "test_the_splitter_boundary_population_is_zero_on_the_tree",
        ),
        (),
        10,
    ),
}

#: ``(executed, annotated, via-helper)`` relation instances over the whole table. The 104
#: in the last column is the point of the register: most of this gate reads the plane
#: through ``_census`` and ``_checked_pairs``, so a map that only recorded direct calls
#: would report a gate with no helpers and lose the reads it cannot see.
_EXIT_READ_INSTANCES = (95, 4, 104)

#: The legs whose reads are all direct or annotated -- the population the cross-check
#: compares between its two lenses. A zero here would make the agreement vacuous.
_DIRECT_RELATION_INSTANCES = 99

#: Which exits more than one leg executes, and how many do it. These are the rows an arm
#: is about to red twice: #548's E7 moved ``optional_publish_bands`` and both of its
#: executors failed; #547's D5 did the same to a guard layer reached through two fixtures.
EXITS_WITH_MULTIPLE_EXECUTORS: dict[str, int] = {
    "_mask_prose": 2,
    "call_shapes": 3,
    "client_surface": 5,
    "conditional_table": 3,
    "consumer_bindings": 9,
    "consumer_defences": 4,
    "denominator_sites": 6,
    "frontend_calls": 8,
    "hook_readings": 4,
    "members_of_type": 2,
    "normalize_path": 2,
    "open_key_types": 4,
    "optional_publish_bands": 2,
    "pairings": 2,
    "payload_of": 5,
    "ruler_blind_spots": 3,
    "ts_declarations": 7,
    "web_src": 19,
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
#: #550's, which audit the map builder's own body; one is #581's, which reads the
#: maskers and no exit at all; and one is #599's, which reads the mask leg's own source.
#: Registered by name because "no direct read" and "no read at all" are the same zero,
#: and the difference is only visible in the helper hop.
LEGS_WITHOUT_DIRECT_READ: frozenset[str] = frozenset(
    {
        "test_an_exit_two_legs_execute_is_rostered_before_the_arm_that_bits_two",
        "test_every_frontend_call_site_reaches_a_route",
        "test_every_name_this_file_imports_reaches_a_leg_or_is_rostered",
        "test_every_route_without_a_frontend_consumer_is_rostered_by_name",
        "test_loose_pairings_are_rostered",
        "test_no_typescript_text_reaches_a_reading_that_did_not_pass_through_the_mask",
        "test_the_exit_read_map_is_measured_not_recited",
        "test_the_helper_hop_has_its_own_second_lens",
        "test_the_mask_leg_asserts_shape_before_it_indexes_by_position",
        "test_the_private_page_interfaces_really_are_in_the_census",
        "test_the_read_map_generator_names_no_register_and_the_anchors_are_rostered",
        "test_the_two_lenses_over_the_read_map_agree_leg_by_leg",
    }
)

#: ``(names in the owner's __all__, names this file imports, names public by convention)``.
#: Three numbers, because the surface has two seams and each is a roster below.
_OWNER_SURFACE = (36, 33, 38)

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
#: import today and a leg would not see in the export list. ``DENOMINATOR_KINDS`` joined
#: ``HTTP_VERBS`` because #554 ranks a vocabulary a leg must read but never call, and the
#: seam goes both ways -- it is why ``surface`` is a triple.
_OWNER_PUBLIC_NOT_EXPORTED: frozenset[str] = frozenset(
    {
        "DENOMINATOR_KINDS",
        "HTTP_VERBS",
    }
)


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
#: the ban: a helper may reach the repo root, the four band names, the page a fixture writes and
#: the member-head lens, and nothing else spelled in uppercase. #549 recorded "7 helpers violate"
#: for a criterion that counted these as violations; measured against the registers themselves the
#: population is zero, which is why the guard is a scope plus a roster rather than a blanket.
_ANCHOR_BINDINGS: frozenset[str] = frozenset({"_BANDS", "_MEMBER_HEAD", "_PAGE", "REPO"})

#: Legs whose helper hop brings back no plane name at all. The empty-via legs are the ones the
#: cross-check below compares as empty on both sides, so they need a roster: a lens that reached
#: no helper and a lens that reached helpers reading nothing look identical in a count.
LEGS_WITHOUT_VIA_HELPER_READ: frozenset[str] = frozenset(
    {
        "test_a_declared_client_verb_the_tree_never_writes_is_a_row_not_an_assumption",
        "test_a_disjunction_fallback_is_a_shape_and_the_precedence_keeps_the_chain_first",
        "test_a_hook_that_issues_two_requests_is_refused_and_says_so",
        "test_a_page_that_writes_fetch_itself_is_a_site_that_no_name_reading_can_ever_see",
        "test_a_request_mention_written_only_in_prose_makes_no_row_in_any_lens",
        "test_a_tuple_member_is_counted_by_whether_the_tuple_hands_its_responses_over",
        "test_a_wrapper_that_forwards_the_payload_whole_reads_no_key_in_either_lens",
        "test_an_exit_two_legs_execute_is_rostered_before_the_arm_that_bits_two",
        "test_an_inline_type_expression_is_masked_before_members_are_read",
        "test_every_name_this_file_imports_reaches_a_leg_or_is_rostered",
        "test_every_paired_site_leaves_the_binding_census_with_exactly_one_reason",
        "test_no_typescript_text_reaches_a_reading_that_did_not_pass_through_the_mask",
        "test_prose_cannot_invent_a_member",
        "test_the_block_lens_adds_a_guard_population_axis_d_never_saw",
        "test_the_conditional_branches_the_fold_rewrites_are_rostered_whole",
        "test_the_exit_read_map_is_measured_not_recited",
        "test_the_fold_reports_every_return_the_handler_can_take",
        "test_the_fold_stops_where_the_caller_stopped_spelling_a_path",
        "test_the_graphs_consumer_population_is_seven_names_and_only_three_are_hooks",
        "test_the_helper_hop_has_its_own_second_lens",
        "test_the_hook_consumers_are_measured_from_their_own_bodies",
        "test_the_mask_blanks_prose_only_and_the_shape_step_blanks_literals_only",
        "test_the_mask_leg_asserts_shape_before_it_indexes_by_position",
        "test_the_path_aliases_the_fold_rewrites_are_rostered_whole",
        "test_the_prose_mask_is_one_rule_applied_to_a_file_never_to_a_line",
        "test_the_read_map_generator_names_no_register_and_the_anchors_are_rostered",
        "test_the_reading_reaches_the_consumer_only_where_the_response_is_handed_over",
        "test_the_routes_this_gate_invents_exist_only_in_its_own_prose",
        "test_the_shapes_the_ruler_sees_and_does_not_read_are_rostered",
        "test_the_six_fields_a_comment_swallowed_are_declared_and_typed_as_written",
        "test_the_statement_lens_reads_a_key_at_three_sites_and_defends_at_two",
        "test_the_three_conditional_guards_each_carry_their_own_case",
        "test_the_two_lenses_over_the_read_map_agree_leg_by_leg",
    }
)

#: Sum over legs of the helpers each reaches, counted once per leg (so a helper two legs share
#: is two edges). The population the text lens walks: 0 would mean the leg below compares two
#: empty sets and calls it agreement.
_CLOSURE_EDGE_TOTAL = 133


# ---------------------------------------------------------------------------
# #555: the mask itself.
#
# Every reading above sits behind a text transformation: comments and string literals are removed
# before a lens decides what is code. Before this number the owner had three maskers, one prose rule
# that knew `//` and nothing else, and two granularities -- whole text for twelve readers, line by
# line for the #554 exits. The landed design is one prose rule (`_mask_prose`), applied to a file,
# plus one optional second step (`_blank_literals`) for a lens that asks a shape question and never
# reads content back. The registers below are what that claim is made of: which functions call which
# mask with what shape of argument, which files are read without one, and what the mask is forbidden
# to touch.
# ---------------------------------------------------------------------------

#: The five names that make up the mask: one prose rule, one literal step, their composition, and
#: the two file-level entry points that hand their result to readers. The inventory leg matches on
#: these strings rather than importing the functions, because it reads the owner's *tree*.
_MASKER_NAMES: tuple[str, ...] = (
    "_blank_literals",
    "_mask_prose",
    "_mask_typescript",
    "_ts_masked",
    "_ts_masked_lines",
)

#: Function -> the maskers whose names appear in its body, sorted. Measured from the owner's tree,
#: so a lane that adds a fourth masker or calls one from a new function moves this table. The two
#: entries with two names are the seam itself: `_mask_typescript` is the *composition* (prose, then
#: literals), and `_ts_masked` is the only place the composition is applied to a file.
_MASK_SITES: dict[str, tuple[str, ...]] = {
    "_declaration_bodies": ("_mask_prose",),
    "_issuers_outside_client": ("_ts_masked",),
    "_mask_typescript": ("_blank_literals", "_mask_prose"),
    "_ts_masked": ("_mask_typescript",),
    "_ts_masked_lines": ("_ts_masked",),
    "alias_table": ("_mask_prose",),
    "call_shapes": ("_mask_prose",),
    "client_surface": ("_ts_masked",),
    "conditional_table": ("_mask_prose",),
    "consumer_bindings": ("_ts_masked_lines",),
    "consumer_defences": ("_ts_masked_lines",),
    "denominator_sites": ("_ts_masked",),
    "frontend_calls": ("_mask_prose",),
    "hook_readings": ("_mask_prose",),
    "members_of_type": ("_mask_prose",),
    "ruler_blind_spots": ("_mask_prose",),
}

#: Mask calls whose first argument is a subscript -- the per-line granularity #555 deleted. It was
#: eleven sites, and the six members below are what they cost. Zero is the whole point of the unit,
#: so it is an equality, not a floor: the mask must be one rule applied once to a whole file.
_PER_LINE_MASK_ARGUMENTS = 0

#: Functions that open a TypeScript file's text, and how many `read_text` sites each has. All nine
#: sites sit inside a mask call; the count is per function so `ruler_blind_spots`, which reads two
#: passes, is visible as two.
_TS_TEXT_READERS: dict[str, int] = {
    "_declaration_bodies": 1,
    "_ts_masked": 1,
    "alias_table": 1,
    "call_shapes": 1,
    "conditional_table": 1,
    "frontend_calls": 1,
    "hook_readings": 1,
    "ruler_blind_spots": 2,
}

#: The other plane. These read Python modules and parse them, so their prose blindness comes from
#: `ast.parse` rather than from a mask -- and #555's rule says nothing about them. Registered by
#: name because the split between "masked text" and "parsed text" is the one place a new reading
#: could quietly pick the wrong side.
_PYTHON_TEXT_READERS: frozenset[str] = frozenset(
    {"_parse", "_source", "api_routers", "endpoints", "payload_of"}
)

#: The six fields `ts_declarations` answered "not declared" about, because a `;` written inside a
#: comment ended their member chunk first. Keyed by (type, member) rather than by line: #555's whole
#: claim is that these are *real* declarations, so the register that proves the reading sees them
#: must not itself be a line number.
PROSE_SHADOWED_MEMBERS: dict[tuple[str, str], tuple[str, bool, str]] = {
    ("AgentJobResult", "steps"): (API_TS, True, "AgentJobStep[]"),
    ("AgentJob", "accept"): (API_TS, True, "AgentAccept | null"),
    ("AuditResponse", "total"): ("apps/web/src/pages/Audit.tsx", False, "number | null"),
    ("NavItem", "roles"): ("apps/web/src/App.tsx", True, "readonly string[]"),
    ("StepSignals", "connection"): (
        "apps/web/src/ui/onboarding.ts",
        False,
        '"pending" | "ok" | "failed"',
    ),
    ("ToastOptions", "duration"): ("apps/web/src/ui/Toast.tsx", True, "number"),
}

#: Chunks the splitter throws away. It is empty now, and the emptiness is the claim: #599 taught
#: the split to step over literals and gave the one chunk it used to lose -- an index signature --
#: a table of its own (``OPEN_KEY_TYPES``). A row here is a *field declaration* the reading cannot
#: answer about; an index signature is not that, so the two tables must move together.
MEMBER_CHUNK_LOSSES: dict[str, tuple[str, str]] = {}

#: Declared types that admit keys nobody wrote down, with the signature that says so. The extras
#: axis asks "does the route publish a key the frontend never declared"; for a type carrying an
#: index signature that question has no answer, so ``_checked_pairs`` refuses to ask it. One row
#: today, and it is the row #581 registered as a *loss* before the split learned to read it.
OPEN_KEY_TYPES: dict[str, tuple[str, str]] = {
    "AgentAcceptFinding": (API_TS, "[key: string]: unknown"),
}

#: The seven prose spellings a request mention can sit in, and the rows each lens returns for a
#: fixture that writes all seven plus four code calls. `p-template` is the one that is *not* prose:
#: a template literal is code, and a mask that ate it would answer zero consumers on the real tree
#: (#555 measured 48 -> 0 with literals blanked).
_FIXTURE_PROSE_FORMS: tuple[str, ...] = (
    "p-block",
    "p-jsdoc",
    "p-line",
    "p-page-block",
    "p-page-line",
    "p-sameline",
    "p-template",
)
_FIXTURE_LENS_ROWS: dict[str, int] = {
    "call_shapes": 7,
    "client_surface": 6,
    "denominator_sites": 14,
    "frontend_calls": 5,
    "hook_readings": 1,
}

#: Routes that exist only in this gate's own docstrings -- the Python plane's version of the same
#: hazard, and the reason §① of the ledger calls the backend a *negative control*: a raw text scan
#: finds three get-decorations on `/ping` in this file and the AST-based reader finds none, because
#: parsing already does what the mask does for TypeScript.
_GATE_PROSE_ROUTE_MENTIONS: tuple[tuple[str, str], ...] = (
    ("get", "/ping"),
    ("get", "/ping"),
    ("get", "/ping"),
)

#: Floors for the populations the mask legs walk. Exact numbers here would make the legs part of
#: queue ⓼ (a comment edited elsewhere moves them); what must be exact is the *violation* count,
#: which is zero everywhere below except the one seam #581 measures and leaves to the next unit.
_MIN_MASKED_TS_FILES = 120
_MIN_PROSE_CHARS = 90000
#: Files carrying a ``/* */`` anywhere, including one that opens and closes on a single line -- the
#: shape the owner's old rule could not see at all, whatever granularity it was handed.
_MIN_BLOCK_PROSE_FILES = 18
_MIN_MASKED_LITERALS = 8000
_MIN_DECLARATION_BODIES = 100
_MIN_MEMBER_CHUNKS = 550
#: Declarations whose member type text carries a string literal -- the 26 that K4 measured being
#: erased when a content reading is handed the shape mask. A floor, not an equality: what the leg
#: guards is that the population exists and every interior survives.
_MIN_LITERAL_TYPE_DECLARATIONS = 26
#: Files whose text masks differently when the rule is applied to the file than when it is applied
#: to each line. The per-line count above is zero, and this is what makes that zero a choice rather
#: than a no-op: a block comment opened on one line is invisible to a rule that never sees the next.
_MIN_GRANULARITY_DIVERGENT_FILES = 12
#: What the quote-aware reading could move, and does not. Six zeros with a leg each: a ``;`` or a
#: brace inside a literal truncates a chunk, a ``}`` inside a literal ends a body early, a literal
#: on an inline object type does the same at a call site, and prose that loses its mask would invent
#: members. Measured on this tree in #599 (118 bodies, 117 declarations, 25 inline expressions) --
#: zero on every counter, which is what makes the fix a fence rather than a repair.
SPLITTER_BOUNDARY_POPULATION: dict[str, int] = {
    "bodies_with_literal_structure": 0,
    "cuts_moved_by_quote_awareness": 0,
    "splits_moved_by_quote_awareness": 0,
    "inline_exprs_at_risk": 0,
    "members_moved_on_tree": 0,
    "members_invented_by_prose": 0,
}

#: Where every pair goes: compared, or one of the four reasons a comparison would be a claim
#: instead of a reading. The leg asserts the tally against the live pairs *and* the sum against
#: ``len(pairs)``, so a pair that quietly stops being compared has to be named here -- before
#: #599 the three unbounded and the one unreadable pair were indistinguishable from the 44.
COMPARISON_LEDGER: dict[str, int] = {
    "compared": 44,
    "payload unbounded": 3,
    "type expression unreadable": 1,
    "empty member set": 0,
    "type admits any key": 0,
}
#: Consumer rows on the real tree whose call-shaped text sits *inside* a string literal. Zero, and
#: the fixture keeps one, because the difference between prose and literal is exactly what the two
#: maskers are for: the first is blanked, the second has to survive.
_CALL_MENTIONS_INSIDE_A_LITERAL = 0
#: Literals whose inside the shape reading did not blank, *named* rather than counted. All of them
#: sit on a line holding a regex literal: the quote scan has no rule for `/"/g`, opens a string at
#: the `"` inside it and keeps blanking until the next quote, so the real `'\\"'` after it is
#: already gone by the time the walk reaches it. Both are a `replace(/"/g, ...)` in a query-selector
#: builder. #599 leaves the scanner alone on purpose -- the gate's own reference lens shares the
#: same quote rule, so it cannot certify a regex fix, and a naive "+regex" rule would blank 38 more
#: decisions on this tree (measured) with 84 false candidates. Naming the rows is what keeps the
#: seam from growing quietly.
SHAPE_SCAN_BLIND_SITES: frozenset[tuple[str, int]] = frozenset(
    {
        ("apps/web/src/ui/CommandPalette.tsx", 240),
        ("apps/web/src/ui/Tabs.tsx", 48),
    }
)


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


def _defence_row(row: ConsumerDefence) -> tuple[str, str, str, str, str]:
    """One guarded site as the register spells it: (verb, path, kind, declared, published).

    The file and line are the register's key, so they stay out of the value: a row that repeats
    its own identity can move half of it and still compare equal to the roster.
    """
    return row.verb, row.path, row.kind, row.declared, row.published


#: One import of the client module that binds something other than a brace list. A namespace or
#: default binding is the shape ``denominator_sites`` cannot resolve, so the leg below counts the
#: files that write it and the fixture proves the refusal.
_NON_BRACE_IMPORT = re.compile(
    r"^import\s+(?:\*\s+as\s+\w+|\w+(?:\s*,\s*\{[^}]*\})?)\s+from\s+['\"][^'\"]*api['\"]"
)


def _declared_client_verbs() -> tuple[str, ...]:
    """The verb names the owner *declares* as its client vocabulary, read off its syntax tree.

    Not the tree's own vocabulary -- the point of the leg that calls this is that a declaration
    can be wrong without any number in the repository noticing, so the declaration itself has to
    arrive as data. Read as a literal dict so a lane that edits the list moves a row here rather
    than teaching the gate to re-derive a name it could only have been told.
    """
    owner = ast.parse((REPO / "tests" / "_payload_plane.py").read_text(encoding="utf-8"))
    for stmt in owner.body:
        if not isinstance(stmt, ast.Assign):
            continue
        if not any(isinstance(t, ast.Name) and t.id == "_CLIENT_VERBS" for t in stmt.targets):
            continue
        if isinstance(stmt.value, ast.Dict):
            return tuple(
                k.value
                for k in stmt.value.keys
                if isinstance(k, ast.Constant) and isinstance(k.value, str)
            )
    return ()


def _issuer_row(row: ClientExport) -> tuple[int, int, bool, tuple[str, ...]]:
    """One issuer as the roster spells it: (line, depth, exported?, via).

    ``name`` and ``file`` are the register's own key, so they stay out of the value -- the #553
    lesson, that a row repeating its identity can move half of it and still compare equal.
    """
    return (row.line, row.depth, row.exported, row.via)


def _site_row(row: DenominatorSite) -> tuple[str, int, str, str]:
    """One site as the rosters spell it: (file, line, kind, binding)."""
    return (row.file, row.line, row.kind, row.binding)


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


def _classify_pair(
    pair: Pair, declarations: Declarations, open_types: frozenset[str]
) -> tuple[str | None, set[str], set[str]]:
    """The pair's exclusion reason and its declared member sets -- one decision table.

    ``_checked_pairs`` keeps the pairs with no reason and the comparison ledger tallies the
    reasons, so a new exclusion cannot enter one without the other. "Type admits any key" is
    not a reading failure: the type is readable, and that is exactly why "the frontend never
    declared this key" cannot be proved about it.
    """
    required, optional, notes = members_of_type(pair.site.type_expr, declarations)
    if notes:
        return "type expression unreadable", required, optional
    if not (required or optional):
        return "empty member set", required, optional
    if _identifiers(pair.site.type_expr) & open_types:
        return "type admits any key", required, optional
    if payload_of(REPO, pair.endpoint).unbounded:
        return "payload unbounded", required, optional
    return None, required, optional


def _checked_pairs(
    pairs: list[Pair], declarations: Declarations
) -> list[tuple[Pair, set[str], set[str]]]:
    """Pairs where both sides of the contract have a readable shape.

    A site with no declared type, a route with no foldable payload, and a type that admits
    any key are not silence here: they are counted by their own legs and registers, so this
    helper only says which pairs can be *compared*.
    """
    open_types = frozenset(open_key_types(web_src(REPO)))
    out = []
    for pair in pairs:
        reason, required, optional = _classify_pair(pair, declarations, open_types)
        if reason is not None:
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
    workspace with 57 verifications that it had 1, while `Guide.tsx` wrote
    `total?: number` and rendered `null` when the key was absent, and `/jobs` has always
    answered it on its only exit. Two frontend files disagreed with each other, and the
    census was the only thing in the repo that could say so. #551 read that disagreement
    off this register and repaired it -- the type is imported from `api.ts` now -- so the
    `/jobs` row was gone, `AXIS_C_BANDS` had four entries, and `always` totalled 7 instead
    of 8. #1631 measured it back: the keyset cursor (#1668bab) made `next_cursor` an
    `always` key of the /jobs exits, so the register reads five entries and `always`
    totals 8 — the /jobs row keys on `next_cursor` (axis (d) files it optional),
    never on `total` (axis (d) files it required). Those numbers are asserted below,
    so a rollback of the declaration shows up as a red leg rather than as a comment.

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
    the choice is the owner's own surface: 31 names in ``__all__`` against 25 imported here,
    and 32 public by name against those 31. Both differences are rosters, so a lane
    that widens the import list or edits ``__all__`` moves a number instead of moving the
    meaning quietly.
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

    The roster below is what the equation says about silence: twelve legs read no exit
    directly. Four are #543/#544's roster legs, whose reads all go through ``_census`` and
    ``_checked_pairs``; four are #549's, which read the map instead of the plane, two are
    #550's, which audit the map builder's own body, and two are #599's -- one mask-order
    meta leg and one fixture-only fuse.
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
    ``ast`` and ``tokenize``, leg by leg over 47 relations -- while the 86 via relations were
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


def test_a_defence_on_a_key_the_route_always_publishes_is_rostered() -> None:
    """Axis (d): the consumer is a fourth place the contract is written, so census it.

    #548's ``/jobs`` row said the page declared ``total`` optional while ``api.ts`` said the same
    field was required. #551 moved the page onto the shared type, which is the *declaration* plane
    agreeing with itself -- and nothing on that plane can see what the page then does with the
    key. ``Guide.tsx`` still writes ``typeof data.total === "number"``, and every tool that could
    object is silent: ``tsc`` accepts the guard, and the edit that matters -- deleting it -- is a
    type error only while the type still says optional. So the guard has two witnesses and neither
    is the type checker: ``vitest`` fails when the guard goes, and this register is the only thing
    that says the guard is there at all. Four rows on this tree, pinned here row by row, band by
    band, and kind by kind.

    The join the probe had to do by hand lives inside each row: ``declared`` comes from the site's
    own type, ``published`` from the route's branch fold. That is what makes one row read as a
    fact about two files instead of a guess about one -- ``Audit.tsx`` guards ``total``, which its
    own type declares required and the route always answers.
    """
    rows = consumer_defences(REPO)
    defences = [row for row in rows if row.key]
    found = {(row.file, row.line, row.key): _defence_row(row) for row in defences}
    assert len(found) == len(defences), (
        f"one (site, key) carries two guarded occurrences: {len(defences)} rows over "
        f"{len(found)} keys, and this register is keyed once per pair"
    )
    assert found == CONSUMER_DEFENCES, f"the defence census moved: {found}"

    bands = {
        name: sum(1 for row in defences if row.declared == name)
        for name in CONSUMER_DEFENCE_BANDS
    }
    assert bands == CONSUMER_DEFENCE_BANDS, f"the declaration bands moved: {bands}"
    kinds = {
        name: sum(1 for row in defences if row.kind == name)
        for name in CONSUMER_DEFENCE_KINDS
    }
    assert kinds == CONSUMER_DEFENCE_KINDS, f"the defence shapes moved: {kinds}"
    assert sum(kinds.values()) == len(defences), (
        f"a defence carries a kind outside the roster: {sorted({row.kind for row in defences})}"
    )

    guide = CONSUMER_DEFENCES[("apps/web/src/pages/Guide.tsx", 74, "total")]
    assert guide == ("get", "/jobs", "typeof", "required", "always"), (
        f"the guard this number exists for changed shape: {guide}"
    )
    jobs_row = AXIS_C_BANDS.get(("get", "/jobs"))
    assert jobs_row == (
        ("apps/web/src/pages/Guide.tsx", 74),
        {"always": ("next_cursor",)},
    ), (
        "the /jobs row in axis (c) is the keyset cursor (#1668bab): axis (d) files "
        "`total` as required and `next_cursor` as optional, so a re-entry keyed on "
        "`total` would be describing a second, stale tree"
    )


def test_the_reading_reaches_the_consumer_only_where_the_response_is_handed_over(
    tmp_path: Path,
) -> None:
    """Where axis (d) may look -- and, rostered, where it may not.

    The population decides how the four rows above are to be read: 48 paired sites, 8 handing
    their response to code inside the same statement, 40 that do not. A page that writes
    ``const data = await apiGet<JobsPage>("/jobs")`` and guards two lines below is not undefended,
    it is unread, and leaving that asymmetry out would turn a census of a quarter of the plane
    into a claim about the plane. This campaign has been hitting that mistake from the other side
    all week -- an empty read printing as "there is no such bug" -- so the blind side leaves in the
    same table as what was found, by file and by count.

    The reach test runs on the payload's path, not on the statement's height, and the fixture is
    what proves the two apart: a request folded across four argument lines yields a *longer* region
    than a one-line chained call and reaches *less*, because those extra lines are the request, not
    the consumer. 18 of the 40 blind sites have exactly that shape. A rule that measured length
    instead would report 25 reached sites and never say that 17 of them contain no consumer.
    """
    rows = consumer_defences(REPO)
    pairs, _orphan = pairings(REPO)
    sites = {(row.file, row.line) for row in rows}
    reached = {(row.file, row.line) for row in rows if row.reached}
    blind = [row for row in rows if not row.reached]
    assert len(sites) == len(pairs), (
        f"the export speaks about {len(sites)} of the {len(pairs)} paired sites"
    )
    assert (len(sites), len(reached), len(blind)) == CONSUMER_DEFENCE_REACH, (
        f"the reach split moved: {(len(sites), len(reached), len(blind))} "
        f"vs {CONSUMER_DEFENCE_REACH}"
    )

    by_file = dict(Counter(row.file for row in blind))
    assert by_file == CONSUMER_DEFENCE_BLIND_BY_FILE, f"the blind side moved: {by_file}"
    bare = {(row.file, row.line) for row in rows if row.reached and not row.key}
    assert bare == CONSUMER_DEFENCE_BARE_SITES, (
        f"reached sites that guard nothing moved: {sorted(bare)}"
    )
    long_regions = sum(1 for row in blind if row.span > 1)
    assert long_regions == CONSUMER_DEFENCE_BLIND_LONG_REGION, (
        f"blind sites whose region still spans lines moved: {long_regions}"
    )

    fixture = _fixture_repo(
        tmp_path / "reach",
        {
            "routes/ping.py": (
                "from fastapi import APIRouter\n"
                "\n"
                "router = APIRouter(prefix='/api/v1')\n"
                "\n"
                "@router.get('/ping')\n"
                "async def api_ping() -> dict[str, int]:\n"
                "    return {'a': 1, 'b': 2}\n"
            )
        },
        {
            "Pages.tsx": (
                "type P = { a: number; b?: number };\n"
                "function Chained() {\n"
                "  return apiGet<P>('/api/v1/ping')\n"
                "    .then((data) => data.b ?? 0);\n"
                "}\n"
                "async function Awaited() {\n"
                "  const data = await apiGet<P>(\n"
                "    '/api/v1/ping',\n"
                "    { signal: undefined },\n"
                "  );\n"
                "  return data.b ?? 0;\n"
                "}\n"
            )
        },
    )
    both = consumer_defences(fixture)
    chained = [row for row in both if row.reached]
    waited = [row for row in both if not row.reached]
    assert (len(chained), len(waited)) == (1, 1), (
        f"the fixture's two spellings did not split one reached and one blind: {both}"
    )
    assert [(row.key, row.kind, row.declared, row.published) for row in chained] == [
        ("b", "nullish", "optional", "always")
    ], f"the chained consumer stopped demonstrating the join: {chained}"
    assert chained[0].span == 2, (
        f"the chain reached the consumer across {chained[0].span} lines, not the two it is"
    )
    assert waited[0].span == 4, (
        f"the multi-line request no longer spans four lines, so this fixture stops saying "
        f"that length is not reach: {waited[0]}"
    )


def test_every_paired_site_leaves_the_binding_census_with_exactly_one_reason() -> None:
    """The 40 blind sites are blind for seven different reasons, and each site gets one.

    ``CONSUMER_DEFENCE_REACH``'s third column said 40 of the 48 paired sites do not hand their
    response to code inside the same statement. It never said why, and one unlabelled majority is
    how a census of a quarter of the plane comes to be read as a census of the plane. So the
    binding census labels every site: 21 are ``api.ts`` forwarding the payload to a caller, 7 sit
    inside a ``Promise.all`` tuple, 3 give the read to a hook, 5 bind with ``await``, 2 discard
    the response, 1 memoizes the promise, 1 destructures with a rename. The vocabulary is ordered
    and first match wins, so a site that both awaits and sits in a tuple is a tuple member -- what
    decides where its guard can be written is the tuple, not the keyword.

    The roster is asserted here rather than only the counts. An implementation that assigned
    styles by position -- first 21 forward, next 8 chains -- would reproduce every number in
    ``CONSUMER_BINDING_STYLES`` and fail one name below, which is the same distinction #550's arm
    K7-shape makes about the read map: a count is not an identity.
    """
    rows: list[ConsumerBinding] = consumer_bindings(REPO)
    pairs, _orphan = pairings(REPO)
    assert len(rows) == len(pairs), f"{len(rows)} rows over {len(pairs)} paired sites"
    sites = [(row.file, row.line) for row in rows]
    assert len(set(sites)) == len(sites), "one site carried two style labels"
    assert set(sites) == {(pair.site.file, pair.site.line) for pair in pairs}, (
        "the census is not over the paired sites"
    )

    counts = dict(Counter(row.style for row in rows))
    assert counts == CONSUMER_BINDING_STYLES, f"the style population moved: {counts}"
    roster = {
        style: tuple(sorted((row.file, row.line) for row in rows if row.style == style))
        for style in CONSUMER_BINDING_STYLES
    }
    assert roster == CONSUMER_BINDING_ROSTER, (
        f"sites changed style label: "
        f"{sorted((s, set(roster[s]) ^ set(CONSUMER_BINDING_ROSTER[s])) for s in roster)}"
    )
    assert sum(counts.values()) == len(rows) == 48, f"the labels do not cover the census: {counts}"


def test_the_statement_lens_reads_a_key_at_three_sites_and_defends_at_two() -> None:
    """Axis (d) reaches 8 sites and reads a payload key at 2 -- so its useful population is 2/48.

    Two independent walks land on the same eight names: ``consumer_bindings`` labels a site
    ``then-chain`` from its own statement frame, while ``consumer_defences`` tests ``.then(``
    inside the region it walks. That agreement is what makes the number usable at all. The rest of
    the leg is what the number was hiding. Of the eight, two read a payload key by name and both
    write a guard -- those are exactly the four rows ``CONSUMER_DEFENCES`` carries -- and six read
    no key of their response at all, which #552 registered as ``CONSUMER_DEFENCE_BARE_SITES`` and
    described as "looked, and there was nothing to find".

    The third site that reads a key in its own statement is not one of the eight: it is
    ``AgentSettings.tsx:73``, an ``await`` binding, and what it reads is
    ``config.base_url``/``.model``/``.protocol``/``.reasoning_effort`` -- the keys of the
    *request* body of the same POST whose response type declares those names. A reading anchored
    on key names cannot separate the two planes, so the row reports four accesses and no defence.
    It stays in the register because the boundary of a ruler is a fact about the ruler.
    """
    rows = consumer_bindings(REPO)
    chains = sorted((row.file, row.line) for row in rows if row.style == "then-chain")
    assert len(chains) == CONSUMER_DEFENCE_REACH[1], (
        f"the chain label reaches {len(chains)} sites, axis (d) says {CONSUMER_DEFENCE_REACH[1]}"
    )
    reached = sorted({(row.file, row.line) for row in consumer_defences(REPO) if row.reached})
    assert chains == reached, f"the two walks stopped agreeing about who is reached: {chains}"

    statement: dict[tuple[str, int], tuple[tuple[str, ...], tuple[str, ...]]] = {}
    for row in rows:
        if row.statement_reads:
            statement[(row.file, row.line)] = (
                tuple(sorted(set(row.statement_reads))),
                tuple(sorted(set(row.statement_kinds))),
            )
    assert statement == CONSUMER_BINDING_STATEMENT_READS, (
        f"the sites that read a key by name moved: {sorted(statement)}"
    )
    guarded = {site for site, (_, kinds) in statement.items() if kinds}
    assert len(guarded) == 2, f"defences live at {len(guarded)} sites, not the two registered"
    assert guarded == {(row.file, row.line) for row in consumer_defences(REPO) if row.key}, (
        "the statement lens and axis (d) disagree about who guards"
    )
    bare = set(chains) - guarded
    assert bare == CONSUMER_DEFENCE_BARE_SITES, (
        f"reached sites that read no key moved: {sorted(bare)}"
    )
    noise = {site for site, (accesses, kinds) in statement.items() if accesses and not kinds}
    assert noise == {("apps/web/src/agent/pages/AgentSettings.tsx", 73)}, (
        f"a site reads keys and defends none of them: {sorted(noise)}"
    )
    assert noise.isdisjoint(chains), "the request-body read stopped being an await binding"


def test_the_block_lens_adds_a_guard_population_axis_d_never_saw() -> None:
    """Reading the enclosing block finds guards at five more sites -- other rows, not more of
    axis (d)'s.

    #552 refused this widening, and its reason was real but small: two of the newly-visible sites
    guard one key twice, once as ``x?.k`` and once as ``x.k ?? y``, which collides with the
    one-row-per-``(site, key)`` rule. Both halves of that are true and they are separable, so the
    block lens keeps its own register, where ``Contracts.tsx:17`` legitimately carries two shapes
    for ``contracts``, and the ``(sites, rows, (site, key))`` triple below is what makes the
    flattening visible instead of quietly resolved. What #552 could not see from here was that the
    collision was the minority: of the 40 blind sites, 37 still guard nothing when the whole
    function body is read.

    The disjointness assertion is the leg's spine. A block row that duplicated an axis-(d) row
    would mean two registers describing one fact, which is how a count gets doubled and a claim
    gets softened.
    """
    rows = consumer_bindings(REPO)
    block_only = {
        (row.file, row.line): tuple(sorted(set(row.block_kinds)))
        for row in rows
        if set(row.block_kinds) - set(row.statement_kinds)
    }
    assert block_only == CONSUMER_BINDING_BLOCK_GUARDS, (
        f"the guards outside the statement moved: {sorted(block_only)}"
    )
    keys = {(site, kind.split(":")[0]) for site, kinds in block_only.items() for kind in kinds}
    totals = (len(block_only), sum(len(v) for v in block_only.values()), len(keys))
    assert totals == CONSUMER_BINDING_BLOCK_TOTALS, f"the block population moved: {totals}"

    axis_d = {(row.file, row.line, row.key) for row in consumer_defences(REPO) if row.key}
    assert not (keys & axis_d), f"a lens double-counted an axis-(d) row: {sorted(keys & axis_d)}"
    twice = {
        (site, key)
        for site, kinds in block_only.items()
        for key in {kind.split(":")[0] for kind in kinds}
        if sum(1 for kind in kinds if kind.startswith(key + ":")) > 1
    }
    assert twice == {
        (("apps/web/src/pages/Contracts.tsx", 17), "contracts"),
        (("apps/web/src/pages/Matrix.tsx", 21), "jobs"),
    }, f"which site guards one key in two shapes moved: {sorted(twice)}"


def test_a_disjunction_fallback_is_a_shape_and_the_precedence_keeps_the_chain_first(
    tmp_path: Path,
) -> None:
    """``x.k || fallback`` is the classifier's seventh shape, ranked last -- and the fixture is
    what proves the ranking is load-bearing.

    Three of the block lens's nine rows are disjunctions: ``data.jobs || []`` in ``Jobs.tsx``,
    ``value.summary ||`` in ``JobDetail.tsx`` and ``data.degraded_reason ||`` in ``Matrix.tsx``.
    Before #553 the classifier had no name for a fallback spelled with ``||``, so those reads left
    the census as "no defence" -- the campaign's own error, an unlooked-for shape reporting as an
    absent bug, aimed at a shape this frontend uses constantly.

    Ranking matters more than adding. The new shape is tested after ``?.``, ``??``,
    ``Array.isArray``, ``typeof``, ``=== undefined`` and the ternary, so it can only name an
    access nothing else claimed. The fixture is the witness: one site writes ``data?.b || 0``,
    carrying a chain and a disjunction on one access, and must still read as ``optchain``. An arm
    that moves ``logical-or`` ahead of the chain test flips that row and reddens nothing else --
    which is the point: the order is the definition, and this is the only leg that holds it.
    """
    rows = consumer_bindings(REPO)
    ors = sorted(
        {
            (row.file, row.line, kind.split(":")[0])
            for row in rows
            for kind in (*row.statement_kinds, *row.block_kinds)
            if kind.endswith(":logical-or")
        }
    )
    assert ors == sorted(CONSUMER_BINDING_LOGICAL_OR), f"the disjunction population moved: {ors}"
    assert len(ors) == 3, f"{len(ors)} disjunction accesses, the register says three"

    fixture = _fixture_repo(
        tmp_path / "shapes",
        {
            "routes/ping.py": (
                "from fastapi import APIRouter\n"
                "\n"
                "router = APIRouter(prefix='/api/v1')\n"
                "\n"
                "@router.get('/ping')\n"
                "async def api_ping() -> dict[str, int]:\n"
                "    return {'a': 1, 'b': 2}\n"
            )
        },
        {
            "Shapes.tsx": (
                "type P = { a: number; b?: number };\n"
                "function Chain() {\n"
                "  return apiGet<P>('/api/v1/ping')\n"
                "    .then((data) => data?.b || 0);\n"
                "}\n"
                "function Disjunction() {\n"
                "  return apiGet<P>('/api/v1/ping')\n"
                "    .then((data) => data.b || 0);\n"
                "}\n"
                "function Coalesce() {\n"
                "  return apiGet<P>('/api/v1/ping')\n"
                "    .then((data) => data.b ?? 0);\n"
                "}\n"
            )
        },
    )
    seen = {
        (row.line, row.statement_kinds)
        for row in consumer_bindings(fixture)
        if row.style == "then-chain"
    }
    assert seen == {(3, ("b:optchain",)), (7, ("b:logical-or",)), (11, ("b:nullish",))}, (
        f"the classifier stopped ranking the shapes against one another: {sorted(seen)}"
    )


def test_a_wrapper_that_forwards_the_payload_whole_reads_no_key_in_either_lens() -> None:
    """``forward`` is a reason for blindness, not a defect -- and this leg holds the property that
    keeps it one.

    Twenty-one of the 48 sites are ``api.ts`` wrappers that return the response to their caller
    without looking at it. That is what a client library is for, so the label names where the
    guard has to be found instead -- the caller, which #553's call-graph probe read, and it added
    two guarded sites and no new reason. The property that would make the label a lie is a forward
    site that *also* guards a key of its own: then "this statement is empty because the payload
    is forwarded" would be both true and useless. Measured empty, and registered as such because
    two empty sets agree for the wrong reason just as easily.

    The register under it is the block lens's own blind side: seven sites where the walker refused
    to resolve an enclosing block. Every one is an ``api.ts`` wrapper whose signature spreads past
    the two lines the head test reads, so the ``{`` it finds closes a parameter list rather than a
    body. Those seven read nothing -- and the difference between "read nothing" and "could not
    read" is the distinction this campaign keeps paying for.
    """
    rows = consumer_bindings(REPO)
    forward = sorted((row.file, row.line) for row in rows if row.style == "forward")
    assert forward == sorted(CONSUMER_BINDING_ROSTER["forward"]), (
        f"the forwarding wrappers moved: {forward}"
    )
    readers = sorted(
        (row.file, row.line)
        for row in rows
        if row.style == "forward" and (row.statement_reads or row.block_reads)
    )
    assert readers == sorted(CONSUMER_BINDING_FORWARD_READS), (
        f"a forwarding site started consuming the payload it claims to hand over: {readers}"
    )

    unread = sorted((row.file, row.line) for row in rows if row.block_span == 0)
    assert unread == sorted(CONSUMER_BINDING_UNREAD_BLOCKS), (
        f"the block walker's refusals moved: {unread}"
    )
    assert {file_ for file_, _ in unread} == {"apps/web/src/api.ts"}, (
        "a refused block left api.ts, so the signature-shape explanation is no longer the story"
    )
    assert not [
        (row.file, row.line)
        for row in rows
        if row.block_span == 0 and (row.block_reads or row.block_kinds)
    ], "an unresolved block reported a guard"


def test_a_tuple_member_is_counted_by_whether_the_tuple_hands_its_responses_over() -> None:
    """Seven members: four reach a ``.then`` callback, three do not -- axis (d)'s asymmetry one
    level up.

    ``Promise.all([...]).then(([plans, sub, usage, invoices]) => ...)`` puts the consumer outside
    every member's own statement, so ``Billing.tsx``'s four calls are blind to the statement lens
    while the page guards payload keys in the callback it cannot reach. ``JobDetail.tsx`` writes
    ``allSettled`` and destructures below the request, so its three members keep their guard in
    the block register and have no ``.then`` to reach at all.

    The split is the finding, because a tuple member is not one kind of site: four have their
    consumer inside the same statement, one line past where the call ends, and three have it in a
    later statement. What the split does *not* turn on is the callee's name -- arm K6 rewrites
    ``Promise.all`` into ``allSettled`` on the Billing line and the four stay four, because the
    test is on the ``.then`` the statement reaches, not on the word that opened the tuple.
    """
    rows = consumer_bindings(REPO)
    members = [row for row in rows if row.style == "tuple-member"]
    assert len(members) == CONSUMER_BINDING_STYLES["tuple-member"] == 7, (
        f"{len(members)} tuple members"
    )
    with_then = {(row.file, row.line) for row in members if row.tuple_reaches_then}
    without = {(row.file, row.line) for row in members if not row.tuple_reaches_then}
    assert with_then == CONSUMER_BINDING_TUPLE_THEN, (
        f"the members that reach their callback moved: {sorted(with_then)}"
    )
    assert without == CONSUMER_BINDING_TUPLE_NO_THEN, (
        f"the members that do not moved: {sorted(without)}"
    )
    assert (len(with_then), len(without)) == (4, 3), "the tuple split moved"
    assert with_then | without == set(CONSUMER_BINDING_ROSTER["tuple-member"]), (
        "a tuple member is in the roster and in neither half of the split"
    )
    guarded_in_block = set(CONSUMER_BINDING_BLOCK_GUARDS)
    assert without & guarded_in_block == {("apps/web/src/pages/JobDetail.tsx", 222)}, (
        f"which allSettled member guards in its block moved: {sorted(without & guarded_in_block)}"
    )
    assert with_then.isdisjoint(guarded_in_block), (
        "a member that reaches its callback grew a block guard of its own"
    )


def test_the_client_surface_is_a_closure_over_transports_not_a_list_of_clients() -> None:
    """⓻: 16 issuers, and the only fact that put any of them on this list is what their body calls.

    ``doFetch`` and ``openEventStream`` write the two transports this frontend has, so they are
    depth 0 and are not exported -- nobody outside ``api.ts`` can call them. Everything else in
    the roster reaches one of those two, either by writing a declared verb or by writing a name
    that does: ``downloadCapsule`` and ``logout`` call ``doFetch`` directly, and the two stream
    wrappers call ``openEventStream``, which no declared verb ever reaches. Not one of those four
    names appears in ``_CLIENT_VERBS``, and none of them is in the census; they are here because
    the walk followed a call.

    The roster also pins the *shape* of the walk, and the shape is seeded rather than measured
    from a root: a body that writes a transport is 0, a body that writes a declared verb is 1,
    and a call adds at most one on top of what it calls. So ``via`` is *not* strictly shallower
    -- ``createFindingFeedback`` sits at 1 next to an ``apiPost`` that is also 1, because the
    verb seed already put it there and the walk had nothing to add -- while ``depth <= 1 +
    depth(via)`` still holds for all fourteen edged rows, no row needed a second round, and the
    depth-0 rows are exactly the two bodies that write a transport themselves. Arm V3 collapses
    the walk to "transport plus the layer that writes a verb" and the four rows above leave,
    which is the bite this roster is sized to fail on.
    """
    rows = client_surface(REPO)
    roster = {row.name: _issuer_row(row) for row in rows}
    changed = sorted(
        (name, CLIENT_ISSUER_ROSTER[name], roster[name])
        for name in roster.keys() & CLIENT_ISSUER_ROSTER.keys()
        if CLIENT_ISSUER_ROSTER[name] != roster[name]
    )
    assert not changed and roster.keys() == CLIENT_ISSUER_ROSTER.keys(), (
        f"the issuer closure moved: gained "
        f"{sorted(roster.keys() - CLIENT_ISSUER_ROSTER.keys())}, lost "
        f"{sorted(CLIENT_ISSUER_ROSTER.keys() - roster.keys())}, changed {changed[:3]}"
    )
    bands = dict(sorted(Counter(row.depth for row in rows).items()))
    assert bands == CLIENT_ISSUER_DEPTH_BANDS, f"depth histogram moved: {bands}"
    assert all(row.file == API_TS for row in rows), (
        "an issuer was reported outside the client module: "
        f"{sorted((row.name, row.file) for row in rows if row.file != API_TS)}"
    )
    assert not [
        (row.name, row.depth, row.via)
        for row in rows
        if (not row.via) != (row.depth == 0)
    ], "a depth-0 row is no longer exactly the bodies that write a transport themselves"
    assert not [
        (row.name, row.depth, other, roster[other][1])
        for row in rows
        for other in row.via
        if other not in roster or not 0 < row.depth <= 1 + roster[other][1]
    ], "an issuer's depth broke the walk bound 0 < depth <= 1 + depth(via)"
    edgeless = sorted(row.name for row in rows if not row.via)
    assert edgeless == sorted(
        name for name, value in CLIENT_ISSUER_ROSTER.items() if value[1] == 0
    ), f"a row with no outgoing edge stopped being a transport wrapper: {edgeless}"
    assert edgeless == sorted(row.name for row in rows if not row.exported), (
        "the transport wrappers and the non-exported rows are no longer the same two names"
    )
    assert len(rows) == sum(CLIENT_ISSUER_DEPTH_BANDS.values()), (
        "the roster and the histogram count different populations"
    )


def test_a_declared_client_verb_the_tree_never_writes_is_a_row_not_an_assumption() -> None:
    """⓻: the vocabulary is a declaration, so census the declaration against the tree.

    Three columns per declared verb -- defined in the client module, mentioned in call shape by a
    product file, bound by a page -- and they disagree in exactly two rows of the roster:
    ``apiPut`` and ``apiPatch`` are declared and written nowhere at all, while ``apiDelete`` is
    declared, defined, called twice inside ``api.ts`` and bound by no page. Nothing was red about
    any of that, because no register held the declared list: a lane that deleted all five
    declarations would have moved the census, and a lane that added a sixth would have moved
    nothing at all.

    The keys of the register *are* the declaration, read off the owner's tree, so arm V2 (two
    declarations withdrawn, nothing in the frontend touched) reddens this leg and only this leg:
    the tree cannot change when a name nobody writes is removed, but the roster loses two rows.
    """
    declared = _declared_client_verbs()
    surface = client_surface(REPO)
    shapes = call_shapes(web_src(REPO))
    page = [row for row in denominator_sites(REPO) if row.file != API_TS]
    derived = {
        verb: (
            sum(1 for row in surface if row.name == verb),
            sum(1 for shape in shapes if shape.name == verb),
            sum(1 for row in page if row.binding == verb),
        )
        for verb in declared
    }
    moved = sorted(
        (verb, CLIENT_VERB_POPULATION.get(verb), derived.get(verb))
        for verb in set(derived) | set(CLIENT_VERB_POPULATION)
        if CLIENT_VERB_POPULATION.get(verb) != derived.get(verb)
    )
    assert not moved, f"the declared verbs and the tree disagree differently now: {moved[:4]}"
    assert len(declared) == len(CLIENT_VERB_POPULATION), (
        f"the owner declares {len(declared)} client verbs; this register holds "
        f"{len(CLIENT_VERB_POPULATION)} rows"
    )
    never_written = sorted(name for name, (_d, written, _b) in derived.items() if written == 0)
    assert never_written == ["apiPatch", "apiPut"], (
        f"which declared verbs the tree never writes moved: {never_written}"
    )
    never_bound = sorted(
        row.name
        for row in surface
        if row.exported and not any(site.binding == row.name for site in page)
    )
    assert set(never_bound) == EXPORTED_ISSUERS_WITHOUT_A_PAGE_SITE, (
        f"an exported issuer lost or gained its first page site: {never_bound}"
    )
    assert "doFetch" not in never_bound and "openEventStream" not in never_bound, (
        "an unexported wrapper is suddenly unreachable by a page, which is the fact that kept "
        "it out of the roster above"
    )


def test_the_denominator_is_wider_than_the_census_by_two_rosters_and_no_hand_wave() -> None:
    """⓻: 105 sites, 58 of them outside the client module, and the census has rows for 48.

    The two readings agree on one thing and one thing only: where they agree. Every census row is
    a site row, and the set difference the other way is the finding -- split into the 21 rows the
    naming ruler has *no name for* and the 16 rows it names but never counts. The second of those
    is the one nobody predicted: ``_consumer_names`` does contain ``useAgentJob``, so the ruler
    knows the consumer, and the census still reports one site for it while ten pages call it.
    ``by_name`` is read off the word the line wrote, not the word behind it, so an aliased import
    lands in the blind roster even though the ruler owns the name it renamed.

    Two structural claims hold the rest of it in place: one line is one row (a line that writes
    two clients keeps the label the vocabulary ranks first), and every row's kind is a label in
    ``DENOMINATOR_KINDS`` -- so the classifier cannot invent a class the register never counted.
    """
    rows = denominator_sites(REPO)
    api_rows = [row for row in rows if row.file == API_TS]
    page = [row for row in rows if row.file != API_TS]
    assert (len(rows), len(page), len(api_rows)) == DENOMINATOR_ROW_TOTALS, (
        f"the denominator moved: ({len(rows)}, {len(page)}, {len(api_rows)}) "
        f"vs {DENOMINATOR_ROW_TOTALS}"
    )
    kinds = dict(sorted(Counter(row.kind for row in page).items()))
    assert kinds == DENOMINATOR_PAGE_KINDS, f"page-side kind population moved: {kinds}"
    assert frozenset(kinds) | {"internal"} == frozenset(DENOMINATOR_KINDS), (
        f"the vocabulary and the population stopped covering each other: "
        f"{sorted(frozenset(DENOMINATOR_KINDS) ^ (frozenset(kinds) | {'internal'}))}"
    )
    assert all(row.kind in DENOMINATOR_KINDS for row in rows), (
        f"a row carries a label outside the vocabulary: "
        f"{sorted({(r.file, r.line, r.kind) for r in rows if r.kind not in DENOMINATOR_KINDS})}"
    )
    assert all(row.kind == "internal" for row in api_rows), (
        "a client-module line was labelled as if a page wrote it"
    )
    sites = {(row.file, row.line) for row in rows}
    assert len(sites) == len(rows), "two rows share one line, so the one-row-per-line rule broke"
    census = {(row.file, row.line) for row in consumer_bindings(REPO)}
    assert census <= sites, (
        f"a census site is no longer a site in the graph reading: {sorted(census - sites)}"
    )
    blind = frozenset(_site_row(row) for row in page if not row.by_name)
    assert blind == DENOMINATOR_PAGE_BLIND, (
        f"the rows the naming ruler cannot say moved: gained "
        f"{sorted(blind - DENOMINATOR_PAGE_BLIND)}, lost {sorted(DENOMINATOR_PAGE_BLIND - blind)}"
    )
    blind_keys = {(row.file, row.line) for row in page if not row.by_name}
    assert not blind_keys & census, (
        f"a blind row is also a census row, so the two halves of the split stopped being "
        f"disjoint: {sorted(blind_keys & census)}"
    )
    named = frozenset(
        _site_row(row) for row in rows if row.by_name and (row.file, row.line) not in census
    )
    assert named == DENOMINATOR_NAMED_WITHOUT_A_CENSUS_ROW, (
        f"named-but-uncounted rows moved: gained "
        f"{sorted(named - DENOMINATOR_NAMED_WITHOUT_A_CENSUS_ROW)}, lost "
        f"{sorted(DENOMINATOR_NAMED_WITHOUT_A_CENSUS_ROW - named)}"
    )
    aliased = frozenset(
        (row.file, row.line, row.callee, row.binding)
        for row in rows
        if row.binding and row.callee != row.binding
    )
    assert aliased == DENOMINATOR_ALIASED_SITES, (
        f"an import renamed its callee and the reading followed it: {sorted(aliased)}"
    )


def test_the_graphs_consumer_population_is_seven_names_and_only_three_are_hooks() -> None:
    """⓻: a consumer, by body rather than by name, is seven frontend functions.

    ``hook_readings`` qualifies two of them (E6's population), and ``_HOOK_DEF`` can at least
    *see* three -- ``useDiff`` is spelled like a hook and refused because its body calls
    ``getAgentDiff`` instead of a verb. The other four have no hook name at all: the app shell,
    a page component, a section component and a column factory, each of which reaches the client
    module in its own body. Two independent readings of the same question therefore report 2 and
    7, and the difference is not a bug in either -- it is what ``use[A-Z]`` was ever able to see.

    The fan-out register is the other half of the claim: sites per callee over the rows the census
    never saw. ``useAgentJob`` carries 11 of the 34, which is why one census row and eleven
    consumers are both true statements about the same tree. Arm V5 renames ``useRemoteData`` and
    this leg must move *names* rather than lose the row: the graph followed the body, so the
    rename arrives in the roster instead of vanishing from the denominator.
    """
    page = [row for row in denominator_sites(REPO) if row.file != API_TS]
    defs = {row.binding: (row.file, row.line) for row in page if row.kind == "issuer-def"}
    moved = sorted(
        (name, PAGE_ISSUER_POPULATION[name], defs[name])
        for name in defs.keys() & PAGE_ISSUER_POPULATION
        if PAGE_ISSUER_POPULATION[name] != defs[name]
    )
    assert defs.keys() == PAGE_ISSUER_POPULATION.keys() and not moved, (
        f"the graph's consumer population moved: gained "
        f"{sorted(defs.keys() - PAGE_ISSUER_POPULATION.keys())}, lost "
        f"{sorted(PAGE_ISSUER_POPULATION.keys() - defs.keys())}, moved {moved}"
    )
    use_shaped = sorted(name for name in defs if re.match(r"^use[A-Z]", name))
    assert use_shaped == ["useAgentJob", "useDiff", "useRemoteData"], (
        f"which issuers carry the hook spelling moved: {use_shaped}"
    )
    assert frozenset(defs) - frozenset(use_shaped) == PAGE_ISSUERS_WITHOUT_USE_SHAPE, (
        f"the issuers E6's pattern cannot see moved: "
        f"{sorted(frozenset(defs) - frozenset(use_shaped) - PAGE_ISSUERS_WITHOUT_USE_SHAPE)}"
    )
    named = sorted(row.name for row in hook_readings(web_src(REPO)) if len(row.verbs) == 1)
    assert named == ["useAgentJob", "useRemoteData"], (
        f"the naming ruler's own consumer population moved: {named}"
    )
    assert frozenset(named) <= frozenset(defs), (
        f"a hook E6 counts is no longer an issuer the graph reaches: "
        f"{sorted(frozenset(named) - frozenset(defs))}"
    )
    census = {(row.file, row.line) for row in consumer_bindings(REPO)}
    invisible = [row for row in page if (row.file, row.line) not in census]
    fanout = dict(Counter(row.binding or row.callee for row in invisible))
    diff = sorted(
        (name, PAGE_ISSUER_FANOUT.get(name), fanout.get(name))
        for name in set(fanout) | set(PAGE_ISSUER_FANOUT)
        if PAGE_ISSUER_FANOUT.get(name) != fanout.get(name)
    )
    assert not diff, f"the sites-per-callee split moved: {diff[:6]}"
    assert max(fanout.values()) == PAGE_ISSUER_FANOUT["useAgentJob"] == 11, (
        "the largest fan-out is no longer the one named hook's eleven call sites"
    )
    assert sum(fanout.values()) == len(invisible) == 34, (
        f"the fan-out no longer covers every census-invisible page row: {sum(fanout.values())}"
    )


def test_a_page_that_writes_fetch_itself_is_a_site_that_no_name_reading_can_ever_see() -> None:
    """⓻: three classes of site exist that a name-anchored reading cannot reach in principle.

    ``Billing.tsx`` builds a CSV url out of an invoice payload and asks the network for it with a
    bare ``fetch``, so the site has no callee name to look up at all. Two rows open a stream
    instead of a request, and both reach ``openEventStream`` -- a name no declared verb ever
    writes, which is the only thing that separates them from the eleven helper rows. The third
    class is what the tree does *not* contain: no file imports the client module under a namespace
    or a default binding, where ``api.apiGet(...)`` and ``defaultClient(...)`` would both be
    invisible to this reading, because a member access is refused by construction and a default
    binding is not read at all.

    Population 1, 2 and 0. Arm V4 rewrites ``Health.tsx``'s typed call into the same bare-fetch
    shape and the first register doubles, which is what turns the ``Billing.tsx`` row from an
    anecdote into a class; the fixture leg shows the other two shapes do produce a row or refuse
    one, so the zeros are measurements rather than the reading's vocabulary.
    """
    rows = denominator_sites(REPO)
    raw = frozenset(
        (row.file, row.line, row.callee) for row in rows if row.kind == "raw-transport"
    )
    assert raw == RAW_TRANSPORT_SITES, (
        f"the pages that bypassed the client module moved: {sorted(raw)}"
    )
    assert all(
        row.binding == "" and not row.by_name for row in rows if row.kind == "raw-transport"
    ), "a bare transport grew a binding, so it is no longer a site with no name to look up"
    assert not [
        (row.file, row.line)
        for row in rows
        if row.kind == "raw-transport" and row.file == API_TS
    ], "a raw transport was counted inside the client module, where that is the wrapper itself"
    census = {(row.file, row.line) for row in consumer_bindings(REPO)}
    assert not census & {(file, line) for file, line, _word in raw}, (
        "the naming ruler also has a row for the bare fetch, so the two readings are no longer "
        "different readings"
    )

    stream = frozenset((row.file, row.line, row.binding) for row in rows if row.kind == "stream")
    assert stream == STREAM_SITES, f"the stream rows moved: {sorted(stream)}"
    surface = {row.name: row for row in client_surface(REPO)}
    streams_reach = {name for _row in stream for name in surface[_row[2]].via}
    assert streams_reach == {"openEventStream"}, (
        f"a stream reaches something other than the event-source wrapper: {sorted(streams_reach)}"
    )
    verbs_reach = {
        name for verb in CLIENT_VERB_POPULATION if verb in surface for name in surface[verb].via
    }
    assert "openEventStream" not in verbs_reach, (
        "a declared verb started reaching the event-source wrapper, so `stream` is no longer "
        "a class the vocabulary can single out"
    )

    non_brace = frozenset(
        (rel, line)
        for rel, text in (
            (
                ts.relative_to(web_src(REPO)).as_posix(),
                ts.read_text(encoding="utf-8"),
            )
            for ts in sorted(
                list(web_src(REPO).rglob("*.ts")) + list(web_src(REPO).rglob("*.tsx"))
            )
        )
        for line, source in enumerate(text.splitlines(), start=1)
        if re.search(_NON_BRACE_IMPORT, source)
    )
    assert non_brace == CLIENT_MODULE_NON_BRACE_IMPORTS, (
        f"a file started importing the client module in a shape the reading cannot bind: "
        f"{sorted(non_brace)}"
    )


def test_the_shapes_this_tree_never_writes_still_produce_rows_when_a_fixture_writes_them(
    tmp_path: Path,
) -> None:
    """⓻: the reading has teeth for every class the product tree reports as zero.

    Four shapes are registered above as empty or single-row populations -- an aliased import, a
    helper-of-a-helper, a line that claims two classes, a namespace or default import -- and a
    zero that no fixture can distinguish from a hole is not a measurement. So the lab writes all
    four, plus a bare ``fetch`` in a page and a hook that issues no verb:

    * ``import { apiGet as get }`` produces a row per line that writes ``get`` -- two of them,
      the plain call and the double-claim line -- each with ``callee='get'``,
      ``binding='apiGet'`` and ``by_name=False``. The rename does not hide the site from the
      graph, and the naming ruler still cannot see it -- which is the whole claim of this number,
      shown on a tree small enough to read.
    * ``deepClient`` reaches the client module through a helper rather than a verb: depth 2 exists
      here, so the walk is transitive and not a one-hop table. ``arrowClient`` is spelled
      ``const ... =>`` and is in the closure with its own edge -- read through the block-less
      body, which is the second witness for #554's ``_decl_body`` fix, because the shape before it
      inherited the body of whichever declaration came next.
    * ``get(useWrapper())`` claims two classes on one line and keeps ``verb-name``, the earlier
      label. Arm V8 swaps the two ranks in ``DENOMINATOR_KINDS`` and this row is where the swap
      shows up: the real tree has no line that claims both, so ordering only ever bites here.
    * ``client.apiGet(...)`` and ``defaultClient(...)`` produce **no** row. That is the reading's
      registered hole, asserted rather than hoped for, and it is why the product-side register
      above counts the files that import this way instead of assuming there are none.
    """
    root = _fixture_repo(
        tmp_path,
        {},
        {
            "api.ts": (
                "async function raw(path: string): Promise<any> {\n"
                "  const r = await fetch(path);\n"
                "  return r.json();\n"
                "}\n"
                "export async function apiGet<T>(path: string): Promise<T> {\n"
                "  return (await raw(path)) as T;\n"
                "}\n"
                "export async function innerName<T>(path: string): Promise<T> {\n"
                "  return apiGet<T>(path);\n"
                "}\n"
                "export const arrowClient = (path: string) => apiGet<string>(path);\n"
                "export async function deepClient<T>(path: string): Promise<T> {\n"
                "  return innerName<T>(path);\n"
                "}\n"
                "export function openThing(path: string) {\n"
                "  return new EventSource(path);\n"
                "}\n"
                "function innerPath(path: string): string {\n"
                "  return '/api/v1/' + path;\n"
                "}\n"
                "export function twoClients<T>(path: string): Promise<T> {\n"
                "  return apiGet<T>(innerPath(path));\n"
                "}\n"
            ),
            "hook.tsx": (
                "import { innerName } from './api';\n"
                "export function useWrapper() {\n"
                "  return innerName('/api/v1/w');\n"
                "}\n"
            ),
            "pages/P.tsx": (
                "import { apiGet as get, innerName, arrowClient, twoClients, "
                "deepClient } from './api';\n"
                "import * as client from './api';\n"
                "import defaultClient from './api';\n"
                "import { useWrapper } from './hook';\n"
                "export function P() {\n"
                "  const a = get<{ x: number }>('/api/v1/a');\n"
                "  const b = innerName('/api/v1/b');\n"
                "  const c = arrowClient('/api/v1/c');\n"
                "  const d = client.apiGet('/api/v1/d');\n"
                "  const e = defaultClient('/api/v1/e');\n"
                "  const f = fetch('/api/v1/f');\n"
                "  const g = useWrapper();\n"
                "  const h = get(useWrapper());\n"
                "  const i = twoClients('/api/v1/i');\n"
                "  const j = deepClient<{ n: number }>('/api/v1/j');\n"
                "  return [a, b, c, d, e, f, g, h, i, j];\n"
                "}\n"
            ),
        },
    )
    page = "apps/web/src/pages/P.tsx"
    surface = {row.name: _issuer_row(row) for row in client_surface(root)}
    assert sorted(name for name, value in surface.items() if value[1] == 0) == [
        "openThing",
        "raw",
    ], f"the fixture's transports moved: {sorted(surface)}"
    tier2 = sorted(name for name, value in surface.items() if value[1] == 2)
    assert tier2 == ["deepClient"], f"the tier-2 witness moved: {tier2}"
    assert surface["arrowClient"][3] == ("apiGet",), (
        "the brace-less arrow lost its own edge, so its body is being read as someone "
        f"else's: {surface['arrowClient']}"
    )
    assert "innerPath" not in surface, (
        "a function that reaches nothing became an issuer -- it builds a path, not a request"
    )

    rows = {(row.file, row.line): row for row in denominator_sites(root)}
    assert len(rows) == 22, f"the fixture's row population moved: {len(rows)}"
    aliased = rows[(page, 6)]
    assert (aliased.callee, aliased.binding, aliased.kind, aliased.by_name) == (
        "get",
        "apiGet",
        "verb-name",
        False,
    ), f"an aliased import stopped being followed: {aliased}"
    assert frozenset(
        (row.file, row.line, row.callee, row.binding)
        for row in rows.values()
        if row.binding and row.callee != row.binding
    ) == frozenset(
        {(page, 6, "get", "apiGet"), (page, 13, "get", "apiGet")}
    ), "the fixture's rename stopped being the row where callee and binding differ"
    multi = rows[(page, 13)]
    assert (multi.callee, multi.kind) == ("get", "verb-name"), (
        f"a line claiming two classes kept {multi.kind}; the vocabulary's order is the definition"
    )
    assert rows[(page, 12)].kind == "issuer-call", (
        f"the call site of a graph-level consumer moved to {rows[(page, 12)].kind}"
    )
    assert rows[("apps/web/src/hook.tsx", 2)].kind == "issuer-def", (
        "a hook that issues no verb stopped being the graph's consumer"
    )
    for name, line in (
        ("innerName", 7),
        ("arrowClient", 8),
        ("twoClients", 14),
        ("deepClient", 15),
    ):
        row = rows[(page, line)]
        assert (row.kind, row.binding, row.by_name) == ("helper", name, False), (
            f"the helper class moved at {name}: {row}"
        )
    raw = rows[(page, 11)]
    assert (raw.callee, raw.kind, raw.binding, raw.by_name) == (
        "fetch",
        "raw-transport",
        "",
        False,
    ), f"a page's bare fetch was labelled {raw.kind}"
    assert {row.kind for row in rows.values()} == {
        "internal",
        "issuer-def",
        "issuer-call",
        "helper",
        "raw-transport",
        "verb-name",
    }, (
        f"the fixture stopped exercising six of the seven classes: "
        f"{sorted({row.kind for row in rows.values()})}"
    )
    for line in (1, 2, 3, 4, 9, 10, 16):
        assert (page, line) not in rows, (
            f"line {line} of the fixture became a row ({rows[(page, line)]}) -- 9 is "
            f"`client.apiGet(...)` and 10 is `defaultClient(...)`, the two import shapes "
            f"this reading cannot bind"
        )


# ---------------------------------------------------------------------------
# The gate's own lens over the mask. Each helper below re-derives something the owner does
# internally, because a leg that asks the mask what it masked answers with the mask.
# ---------------------------------------------------------------------------


def _parent_map(module: ast.Module) -> dict[int, ast.AST]:
    """Child -> parent links, which `ast.walk` does not keep."""
    parents: dict[int, ast.AST] = {}
    for node in ast.walk(module):
        for child in ast.iter_child_nodes(node):
            parents[id(child)] = node
    return parents


def _holder_of(node: ast.AST, parents: dict[int, ast.AST]) -> str:
    cur: ast.AST | None = node
    while cur is not None:
        if isinstance(cur, ast.FunctionDef):
            return cur.name
        cur = parents.get(id(cur))
    return "<module>"


def _ts_tokens(text: str) -> tuple[list[tuple[int, int]], list[tuple[int, int]]]:
    """(``prose spans``, ``literal spans``) from a tokenizer written beside this gate.

    The mask legs cannot ask the mask what it considers prose -- that question answers itself, and
    #549's arm G7 is the lesson: an instrument that reports the wish passes every assertion that
    reads it. So this walk keeps the two categories apart the way the language does: ``//`` runs to
    the newline, ``/*`` runs to its closer (or to the end of the text, unterminated), a quote runs
    to its quote or to the line end except for a backtick, which may cross lines, and a backslash
    carries whatever follows it along.
    """
    prose: list[tuple[int, int]] = []
    literals: list[tuple[int, int]] = []
    i = 0
    size = len(text)
    while i < size:
        if text.startswith("//", i):
            j = i
            while j < size and text[j] != "\n":
                j += 1
            prose.append((i, j))
            i = j
        elif text.startswith("/*", i):
            closer = text.find("*/", i + 2)
            stop = size if closer < 0 else closer + 2
            prose.append((i, stop))
            i = stop
        elif text[i] in "'\"`":
            quote = text[i]
            j = i + 1
            while j < size:
                if text[j] == "\\":
                    j += 2
                    continue
                if text[j] == quote:
                    j += 1
                    break
                if text[j] == "\n" and quote != "`":
                    break
                j += 1
            literals.append((i, min(j, size)))
            i = literals[-1][1]
        else:
            i += 1
    return prose, literals


def _mask_inventory(
    owner: ast.Module, maskers: tuple[str, ...]
) -> tuple[dict[str, tuple[str, ...]], list[str]]:
    """Which function calls which mask, and every mask call handed a line rather than a file."""
    parents = _parent_map(owner)
    sites: dict[str, set[str]] = {}
    per_line: list[str] = []
    for node in ast.walk(owner):
        if not isinstance(node, ast.Call) or not isinstance(node.func, ast.Name):
            continue
        if node.func.id not in maskers:
            continue
        holder = _holder_of(node, parents)
        sites.setdefault(holder, set()).add(node.func.id)
        first = node.args[0] if node.args else None
        if isinstance(first, ast.Subscript):
            per_line.append(f"{holder}:{node.lineno}:{node.func.id}")
    return {name: tuple(sorted(kinds)) for name, kinds in sites.items()}, per_line


def _text_reader_sites(
    owner: ast.Module, maskers: tuple[str, ...]
) -> tuple[dict[str, int], dict[str, int]]:
    """``read_text`` sites split by whether a mask call encloses them, counted per function.

    The two dictionaries are the whole coverage claim: a text read that is *not* inside a mask has
    to be a Python module read, where ``ast.parse`` does the prose-blinding instead. A new
    TypeScript reader that opens a file raw lands in the second dictionary under a name no roster
    carries.
    """
    parents = _parent_map(owner)
    masked: dict[str, int] = {}
    bare: dict[str, int] = {}

    def enclosed(node: ast.AST) -> bool:
        cur: ast.AST | None = parents.get(id(node))
        while cur is not None:
            if (
                isinstance(cur, ast.Call)
                and isinstance(cur.func, ast.Name)
                and cur.func.id in maskers
            ):
                return True
            cur = parents.get(id(cur))
        return False

    for node in ast.walk(owner):
        if not isinstance(node, ast.Call) or not isinstance(node.func, ast.Attribute):
            continue
        if node.func.attr != "read_text":
            continue
        holder = _holder_of(node, parents)
        bucket = masked if enclosed(node) else bare
        bucket[holder] = bucket.get(holder, 0) + 1
    return masked, bare


def _rel_label(web: Path, ts: Path) -> str:
    """The file's own tail plus its path inside the web root, in the form the rosters spell."""
    return "/".join(web.parts[-3:]) + "/" + ts.relative_to(web).as_posix()


def _declaration_bodies(web: Path, head: re.Pattern[str]) -> list[tuple[str, str, str]]:
    """(name, host, body) for every object-shaped declaration this lens finds.

    Braces are matched by walking, not by a regex: a nested object member has to close before its
    declaration does. The body excludes both braces, which is what the splitter is fed.
    """
    out: list[tuple[str, str, str]] = []
    for ts in sorted(list(web.rglob("*.ts")) + list(web.rglob("*.tsx"))):
        text = _mask_prose(ts.read_text(encoding="utf-8"))
        for match in head.finditer(text):
            name = match.group(1) or match.group(2)
            open_at = match.end() - 1
            depth = 0
            i = open_at
            while i < len(text):
                if text[i] == "{":
                    depth += 1
                elif text[i] == "}":
                    depth -= 1
                    if depth == 0:
                        break
                i += 1
            out.append((name, _rel_label(web, ts), text[open_at + 1 : i]))
    return out


def _chunk_walk(body: str, member_head: re.Pattern[str]) -> list[tuple[str, bool]]:
    """Every depth-0 chunk of an object body, and whether this lens calls it a member.

    ``[`` and ``]`` are kept in the chunk on purpose: an index signature is a real field declaration
    in TypeScript, and a census that drops the brackets would report it as noise rather than as a
    member the reading lost.
    """
    out: list[tuple[str, bool]] = []
    depth = 0
    buf = ""
    for ch in body:
        if ch in "{[(":
            depth += 1
            buf += ch
        elif ch in "})]":
            depth -= 1
            buf += ch
        elif ch == ";" and depth == 0:
            if buf.strip():
                out.append((buf, bool(member_head.match(buf))))
            buf = ""
        else:
            buf += ch
    if buf.strip():
        out.append((buf, bool(member_head.match(buf))))
    return out


def _chunk_name(chunk: str) -> str:
    match = re.match(r"^\s*(?:readonly\s+)?\[?\s*([A-Za-z_$][\w$]*)", chunk)
    return match.group(1) if match else ""


def _literals_holding_structure(text: str) -> list[str]:
    """Literals whose own contents carry a ``;`` or a brace -- the splitter's blind side."""
    _prose, literals = _ts_tokens(text)
    return [text[a:b] for a, b in literals if any(c in text[a + 1 : b - 1] for c in ";{}")]


def _blank_literal_interiors(text: str) -> str:
    """The same text with literal interiors blanked, delimiters and columns kept.

    The counterfactual half of #599's fix: a split that runs on this string sees exactly what a
    quote-stepping split sees structurally, so comparing the two says whether the tree depends
    on the blindness. Contents are never needed here -- the content lens is `ts_declarations`.
    """
    _prose, literals = _ts_tokens(text)
    chars = list(text)
    for start, stop in literals:
        for k in range(start + 1, stop - 1):
            chars[k] = " "
    return "".join(chars)


def _declaration_bodies_quote_aware(
    web: Path, head: re.Pattern[str]
) -> list[tuple[str, str, str]]:
    """``_declaration_bodies`` with literal interiors blanked before the braces are counted.

    Same heads, same order, same records -- only the walk's feeding text differs. If stepping
    over literals moves a body boundary on this tree, these bodies disagree with the raw ones.
    """
    out: list[tuple[str, str, str]] = []
    for ts in sorted(list(web.rglob("*.ts")) + list(web.rglob("*.tsx"))):
        text = _mask_prose(ts.read_text(encoding="utf-8"))
        shape = _blank_literal_interiors(text)
        for match in head.finditer(text):
            name = match.group(1) or match.group(2)
            open_at = match.end() - 1
            depth = 0
            i = open_at
            while i < len(text):
                if shape[i] == "{":
                    depth += 1
                elif shape[i] == "}":
                    depth -= 1
                    if depth == 0:
                        break
                i += 1
            out.append((name, _rel_label(web, ts), text[open_at + 1 : i]))
    return out


def _split_stepping_over_literals(body: str) -> list[str]:
    """Member names read from a body whose literal interiors cannot act as structure."""
    return [
        _chunk_name(chunk)
        for chunk, is_member in _chunk_walk(_blank_literal_interiors(body), _MEMBER_HEAD)
        if is_member
    ]


def _prose_line_numbers(text: str) -> set[int]:
    prose, _literals = _ts_tokens(text)
    lines: set[int] = set()
    for start, stop in prose:
        for k in range(start, stop):
            lines.add(text.count("\n", 0, k) + 1)
    return lines


def _forms_in_prose(text: str, mention: re.Pattern[str]) -> set[str]:
    prose, _literals = _ts_tokens(text)
    return {m.group(1) for start, stop in prose for m in mention.finditer(text[start:stop])}


def _mentions_inside_literals(text: str, shape: re.Pattern[str]) -> list[tuple[int, str]]:
    _prose, literals = _ts_tokens(text)
    out: list[tuple[int, str]] = []
    for start, stop in literals:
        inner_end = max(start + 1, stop - 1)
        for match in shape.finditer(text, start + 1, inner_end):
            out.append((text.count("\n", 0, match.start()) + 1, match.group(0)))
    return out


#: A declaration head as this gate reads it -- the same two spellings the owner matches, written out
#: a second time so the chunk census below cannot be told what to look for by the reader it audits.
_DECLARATION_HEAD = re.compile(
    r"^(?:export\s+)?(?:interface\s+(\w+)[^{}]*\{|type\s+(\w+)\s*=\s*\{)", re.M
)

#: Deliberately wider than the owner's member rule: a name, an optional mark, an index signature, a
#: method, any of them behind ``readonly``. A chunk that is a field and is missing from the reading
#: is a loss whatever swallowed it, which is the point of counting chunks instead of hunting causes.
_MEMBER_HEAD = re.compile(
    r"^\s*(?:readonly\s+)?(?:\[\s*\w+\s*:\s*\w+\s*\]|[A-Za-z_$][\w$]*\s*\??\s*[:<(])"
)

_PROSE_MENTION = re.compile(r"/api/v1/(p-[a-z-]+)")
_CALL_SHAPED_TEXT = re.compile(r"(?<![\w.$])api[A-Z]\w*\s*[<(]")

#: A regex literal on one line: a slash in operand position, at least one character, a closing
#: slash and flags. Crude on purpose -- it is only ever consulted to explain a disagreement between
#: this walk's tokenizer and the owner's quote scan, never to decide what is prose.
_REGEX_LIKE = re.compile(r"(?<![\w)\]}'\"])/(?:\\.|[^/\n\\])+/[gimsuy]*")

#: Route-shaped text, read the way a raw scan of the backend would read it -- decoration name plus
#: a quoted path. Only the prose of this file matches it, which is the point of the leg below.
_ROUTE_MENTION = re.compile(r'@router\.(\w+)\(\s*["\']([^"\']+)')


def test_the_prose_mask_is_one_rule_applied_to_a_file_never_to_a_line() -> None:
    """⓽, first half: the owner has one prose rule and it is handed whole files.

    Before #555 the mask knew ``//`` and nothing else, and it was applied at two granularities --
    over a file for twelve readers and over each line for the #554 exits. A ``/* ... */`` opened on
    one line and closed on another was code to both of them, and the ledger's six members are what
    that cost: a ``;`` written inside a JSDoc ended the member chunk, ``_one_member``'s regex then
    refused the remainder, and the field the browser declared did not exist as far as the census was
    concerned.

    ``_PER_LINE_MASK_ARGUMENTS`` is the sentence this leg exists to make impossible. It is zero, and
    the floor below says the zero is not vacuous: on the very same files, applying the rule line by
    line instead of file by file gives a *different* text -- so a lane that goes back to the old
    granularity changes what the readings see, not merely how often they call a function.
    """
    owner = ast.parse((REPO / "tests" / "_payload_plane.py").read_text(encoding="utf-8"))
    sites, per_line = _mask_inventory(owner, _MASKER_NAMES)
    assert sites == _MASK_SITES, f"which function calls which mask moved: {sites}"
    assert len(per_line) == _PER_LINE_MASK_ARGUMENTS, (
        f"a mask was handed one line instead of a file: {sorted(per_line)} -- that is the "
        f"granularity #555 removed, and it is what hid the six members"
    )

    files = sorted(list(web_src(REPO).rglob("*.ts")) + list(web_src(REPO).rglob("*.tsx")))
    divergent = [
        ts.name
        for ts in files
        if _mask_prose(ts.read_text(encoding="utf-8"))
        != "\n".join(_mask_prose(line) for line in ts.read_text(encoding="utf-8").split("\n"))
    ]
    assert len(divergent) >= _MIN_GRANULARITY_DIVERGENT_FILES, (
        f"only {len(divergent)} files mask differently per line than per file: the two "
        f"granularities have quietly become one, and this floor has no load on it"
    )


def test_no_typescript_text_reaches_a_reading_that_did_not_pass_through_the_mask() -> None:
    """⓽, second half: coverage. Not one reader opens a frontend file raw.

    This is the part a fix usually forgets. Replacing the rule is worth nothing if a single reader
    still calls ``read_text`` on its own, because that reader keeps the old behavior and the census
    keeps a second, undocumented answer to the same question. The owner had exactly that shape:
    ``ts_declarations`` -- the one exit whose whole job is reading declarations -- never masked at
    all, which is why the six fields below had to be found by a probe rather than by a leg.

    Two rosters, one claim: the masked sites are the TypeScript readers, and every unmasked
    ``read_text`` in the owner belongs to the Python plane, where ``ast.parse`` does the blinding.
    """
    owner = ast.parse((REPO / "tests" / "_payload_plane.py").read_text(encoding="utf-8"))
    masked, bare = _text_reader_sites(owner, _MASKER_NAMES)
    assert masked == _TS_TEXT_READERS, f"which function reads TypeScript text moved: {masked}"
    assert frozenset(bare) == _PYTHON_TEXT_READERS, (
        f"unmasked reads: {sorted(bare)} vs the Python plane {sorted(_PYTHON_TEXT_READERS)} -- "
        f"a TypeScript reader that reads raw is a second, unregistered answer"
    )


def test_the_mask_blanks_prose_only_and_the_shape_step_blanks_literals_only() -> None:
    """The two readings, separated by what they are allowed to erase.

    ``_mask_prose`` blanks exactly the spans an independent tokenizer calls comments -- and nothing
    else: no literal, no code, no character count, no newline. ``_mask_typescript`` adds the literal
    step on top of that, keeping the quotes and erasing the inside, and it is legal only for a lens
    that asks a shape question. §① measured what happens when that boundary is crossed: with
    literals blanked, ``frontend_calls`` reports **0** of 48 sites, because a route path *is* a
    string literal. So the division of labor is not a style preference and this leg is where it is
    pinned.

    Every violation list is empty. The floors say how much text that walked: 144 files, prose on
    94k characters, literals 9k -- the zero is measured over a population, not asserted over an
    example.
    """
    files = sorted(list(web_src(REPO).rglob("*.ts")) + list(web_src(REPO).rglob("*.tsx")))
    prose_chars = 0
    literal_count = 0
    block_files: set[str] = set()
    prose_survived: list[str] = []
    code_touched: list[str] = []
    literal_touched: list[str] = []
    width_moved: list[str] = []
    shape_kept_literal: list[str] = []
    scan_blind_sites: list[tuple[str, int]] = []
    shape_lost_quote: list[str] = []

    masks: dict[str, tuple[str, str]] = {}
    for ts in files:
        raw = ts.read_text(encoding="utf-8")
        rel = _rel_label(web_src(REPO), ts)
        masked, shape = _mask_prose(raw), _mask_typescript(raw)
        masks[rel] = (masked, shape)
        if len(masked) != len(raw) or len(shape) != len(raw):
            width_moved.append(rel)
        if masked.count("\n") != raw.count("\n") or shape.count("\n") != raw.count("\n"):
            width_moved.append(rel)
    # The width assertion runs before any walk indexes the masked text. K2 -- a mask that deletes
    # characters instead of blanking them -- used to surface as an IndexError inside the character
    # walk, which turned a violated invariant into a crash and hid every finding after it. A broken
    # mask has to be *reported* by the invariant it breaks.
    assert not width_moved, f"the mask changed the shape of the text: {sorted(set(width_moved))}"

    for ts in files:
        raw = ts.read_text(encoding="utf-8")
        masked, shape = masks[_rel_label(web_src(REPO), ts)]
        prose, literals = _ts_tokens(raw)
        rel = _rel_label(web_src(REPO), ts)

        in_prose: set[int] = set()
        for start, stop in prose:
            in_prose.update(range(start, stop))
            prose_chars += sum(1 for k in range(start, stop) if raw[k] != "\n")
            if raw.startswith("/*", start):
                block_files.add(rel)

        in_literal: set[int] = set()
        raw_lines = raw.split("\n")
        for start, stop in literals:
            if any(k in in_prose for k in range(start, stop)):
                continue
            literal_count += 1
            in_literal.update(range(start, stop))
            lineno = raw.count(chr(10), 0, start) + 1
            if masked[start:stop] != raw[start:stop]:
                literal_touched.append(f"{rel}:{lineno}")
            closer = stop - 1 if raw[stop - 1] == raw[start] else None
            if closer is not None and shape[closer] != raw[start]:
                shape_lost_quote.append(f"{rel}:{lineno}")
            interior = raw[start + 1 : closer] if closer is not None else raw[start + 1 : stop]
            blanked = shape[start + 1 : closer] if closer is not None else shape[start + 1 : stop]
            if re.sub(r"[^\n]", " ", interior) != blanked:
                if _REGEX_LIKE.search(raw_lines[lineno - 1]):
                    scan_blind_sites.append((rel, lineno))
                else:
                    shape_kept_literal.append(f"{rel}:{lineno}")

        for k, ch in enumerate(raw):
            if ch == "\n":
                continue
            if k in in_prose:
                if masked[k] != " " or shape[k] != " ":
                    prose_survived.append(f"{rel}:{raw.count(chr(10), 0, k) + 1}")
            elif k not in in_literal and masked[k] != ch:
                code_touched.append(f"{rel}:{raw.count(chr(10), 0, k) + 1}")

    assert files, "the frontend plane is empty"
    assert len(files) >= _MIN_MASKED_TS_FILES, f"only {len(files)} files walked"
    assert prose_chars >= _MIN_PROSE_CHARS, f"only {prose_chars} prose characters walked"
    assert len(block_files) >= _MIN_BLOCK_PROSE_FILES, (
        f"only {len(block_files)} files carry block comments"
    )
    assert literal_count >= _MIN_MASKED_LITERALS, f"only {literal_count} literals walked"
    assert set(scan_blind_sites) == SHAPE_SCAN_BLIND_SITES, (
        f"the quote scan opened a string inside a regex literal at {sorted(scan_blind_sites)}"
    )
    assert not prose_survived, f"prose survived the mask at {len(prose_survived)} characters"
    assert not code_touched, f"the mask rewrote code at {code_touched[:6]}"
    assert not literal_touched, f"the prose mask touched a literal at {literal_touched[:6]}"
    assert not shape_kept_literal, (
        f"the shape reading left literal text at {shape_kept_literal[:6]}"
    )
    assert not shape_lost_quote, (
        f"the shape reading erased its own delimiters at {shape_lost_quote[:6]}"
    )


def test_the_six_fields_a_comment_swallowed_are_declared_and_typed_as_written() -> None:
    """The six rows §①.5 named, asserted as facts about the tree rather than as a fixed count.

    Each of these is a field the frontend spells out and the reading answered "not declared" about.
    ``AuditResponse.total`` is the one that reached a register: it sat in
    ``ROSTERED_EXTRA_KEYS`` for six units, filed as "the route publishes a key nobody wrote down",
    while line 41 of the very page that guards it said otherwise. An entry in that register is a
    claim about the *frontend*, and a mask that loses a line writes a false claim into the one table
    whose job is to catch false claims.

    Keyed by (type, member) rather than by (file, line): these are declarations, and the register
    that proves the reading can see them must not itself be a queue ⓼ hostage.
    """
    decl = ts_declarations(web_src(REPO))
    found: dict[tuple[str, str], tuple[str, bool, str]] = {}
    for type_name, member in PROSE_SHADOWED_MEMBERS:
        host, members = decl[type_name]
        hit = [item for item in members if item.name == member]
        found[(type_name, member)] = (
            (host, hit[0].optional, hit[0].type_text) if hit else ("MISSING", False, "MISSING")
        )
    assert found == PROSE_SHADOWED_MEMBERS, f"the restored members moved: {found}"

    required, optional, notes = members_of_type("AuditResponse", decl)
    assert "total" in required, f"total read as required? required={sorted(required)}"
    assert not optional and not notes, f"the audit type's shape stopped being plain: {notes}"


def test_a_request_mention_written_only_in_prose_makes_no_row_in_any_lens(tmp_path: Path) -> None:
    """The fence with population: seven ways to write a call in prose, and the rows they make.

    #554's V6 arm added one comment line to ``api.ts`` and six legs went red, which proved two of
    the lenses read prose as code. The finding was real and the *population* was not: on this tree,
    zero rows come from a comment. A zero that comes from absence of a test is not a measurement, so
    this fixture writes the mention seven times -- line comment, same-line block comment, a block
    comment spanning lines, a JSDoc, and the two page-side spellings -- plus one inside a template
    literal, which is the control that keeps the mask honest in the other direction.

    ``p-template`` is not prose. It becomes a row, and that is the boundary #555 is made of: a mask
    that also blanked literals would read 0 of 48 consumers, because a route path is a string.
    """
    web = _fixture_web(
        tmp_path,
        {
            "api.ts": _PROSE_FIXTURE_API_TS,
            "types.ts": _PROSE_FIXTURE_TYPES_TS,
            "pages/Thing.tsx": _PROSE_FIXTURE_PAGE_TSX,
        },
    )
    texts = {
        _rel_label(web, ts): ts.read_text(encoding="utf-8")
        for ts in sorted(list(web.rglob("*.ts")) + list(web.rglob("*.tsx")))
    }
    prose_lines = {
        (rel, line) for rel, text in texts.items() for line in _prose_line_numbers(text)
    }
    forms: set[str] = set()
    for text in texts.values():
        forms |= _forms_in_prose(text, _PROSE_MENTION)
    assert forms | {"p-template"} == set(_FIXTURE_PROSE_FORMS), (
        f"the fixture's prose forms moved: prose={sorted(forms)}"
    )

    rows = {
        "call_shapes": [(s.file, s.line) for s in call_shapes(web)],
        "frontend_calls": [(c.file, c.line) for c in frontend_calls(web)[0]],
        "hook_readings": [(h.file, h.line) for h in hook_readings(web)],
        "client_surface": [(e.file, e.line) for e in client_surface(tmp_path)],
        "denominator_sites": [(s.file, s.line) for s in denominator_sites(tmp_path)],
    }
    counts = {name: len(value) for name, value in sorted(rows.items())}
    assert counts == _FIXTURE_LENS_ROWS, f"the fixture's row populations moved: {counts}"

    from_prose = {
        name: sorted(pos for pos in value if pos in prose_lines) for name, value in rows.items()
    }
    assert not any(from_prose.values()), f"a comment became a consumer row: {from_prose}"

    api_ts = "apps/web/src/api.ts"
    template_rows = {name for name, value in rows.items() if (api_ts, 26) in value}
    assert template_rows == {"call_shapes", "frontend_calls"}, (
        f"the template-literal mention is read by {sorted(template_rows)}; it is code and has to "
        f"survive the prose mask -- only the shape step may erase it, and then it is not a site"
    )
    planted_hits = {
        rel: hits for rel, text in texts.items() for hits in [_mentions_inside_literals(
            text, _CALL_SHAPED_TEXT
        )]
    }
    assert planted_hits[api_ts] == [(26, "apiGet<")], (
        f"the planted literal mention is no longer visible inside its string: {planted_hits}"
    )

    real = [
        (_rel_label(web_src(REPO), ts), hit)
        for ts in sorted(list(web_src(REPO).rglob("*.ts")) + list(web_src(REPO).rglob("*.tsx")))
        for hit in _mentions_inside_literals(ts.read_text(encoding="utf-8"), _CALL_SHAPED_TEXT)
    ]
    assert len(real) == _CALL_MENTIONS_INSIDE_A_LITERAL, (
        f"a consumer row written inside a string literal appeared on the real tree: {real[:6]} -- "
        f"the census reads it as a request the page makes, and no page makes it"
    )


def test_every_member_chunk_the_splitter_keeps_or_drops_is_counted(tmp_path: Path) -> None:
    """The general form of the six: a chunk that is a field and is not in the answer is a loss.

    §①.5 found its six members by chasing one mechanism -- a ``;`` in prose. This leg refuses to
    assume the mechanism and counts instead: replay the split over every declaration body with this
    file's own walk, keep the chunks that look like fields, and diff their names against what
    ``ts_declarations`` reports. Whatever the cause, that difference is a field the browser declared
    and the reading answers "not declared" about.

    One row used to be here, and it was not the prose bug: an index signature. ``[key: string]:
    unknown`` is TypeScript for "any key is allowed here", so #599 gave it a table of its own
    (``OPEN_KEY_TYPES``) instead of pretending it is a field. The census skips exactly the chunks
    that table registers, which is the interlock: break the exit and this leg grows a row.

    The second half is the same hazard one layer down. ``_split_members`` counted braces without
    stepping over quotes, so a ``;`` or a ``{`` written *inside* a string truncated the body the
    way a comment's ``;`` used to. Nothing on this tree writes it -- that is the first assertion --
    and the planted interface pins the answer: all three fields, with the literal structure still
    inside ``label``'s type text.
    """
    decl = ts_declarations(web_src(REPO))
    open_keys = open_key_types(web_src(REPO))
    bodies = _declaration_bodies(web_src(REPO), _DECLARATION_HEAD)
    assert len(bodies) >= _MIN_DECLARATION_BODIES, f"only {len(bodies)} declaration bodies found"

    chunks = 0
    lost: dict[str, tuple[str, str]] = {}
    for name, rel, body in bodies:
        entry = decl.get(name)
        if entry is None:
            continue
        kept = {item.name for item in entry[1]}
        registered = " ".join(open_keys.get(name, ("", ""))[1].split())
        for chunk, is_member in _chunk_walk(body, _MEMBER_HEAD):
            chunks += 1
            if is_member and " ".join(chunk.split()) == registered:
                continue
            if is_member and _chunk_name(chunk) not in kept:
                lost[name] = (rel, " ".join(chunk.split())[:48])
    assert chunks >= _MIN_MEMBER_CHUNKS, f"only {chunks} chunks walked"
    assert lost == MEMBER_CHUNK_LOSSES, f"chunks the splitter threw away moved: {lost}"
    assert not any(_literals_holding_structure(body) for _n, _r, body in bodies), (
        "a declaration body now carries a ; or a brace inside a string literal, and the "
        "splitting rule reads it as structure: the members after it are silently lost"
    )

    planted = _fixture_web(
        tmp_path,
        {
            "Holder.ts": (
                "export interface Holder {\n"
                "  id: string;\n"
                '  label: "keep; this" | "and { this";\n'
                "  count: number;\n"
                "}\n"
                "export interface Plain {\n"
                "  id: string;\n"
                "  count: number;\n"
                "}\n"
            )
        },
    )
    read = ts_declarations(planted)
    holder = [item.name for item in read["Holder"][1]]
    assert holder == ["id", "label", "count"], (
        f"the planted literal seam truncated the body again: {holder} "
        f"-- the split must step over the literal without removing its text"
    )
    assert [item.name for item in read["Plain"][1]] == ["id", "count"]
    assert _literals_holding_structure(
        (planted / "Holder.ts").read_text(encoding="utf-8")
    ), "the planted fixture no longer contains the shape it plants"


def test_the_routes_this_gate_invents_exist_only_in_its_own_prose() -> None:
    """The negative control §①.7 measured: the Python plane does not need a mask, and says so.

    The same hazard exists on the backend -- a decoration quoted inside a docstring is route-shaped
    text -- and it costs nothing there, because the Python readers parse. #555 counted it rather
    than assuming it: 1,217 files, three route-shaped mentions in raw text that no decoration
    answers, and every one of them is in *this file's* docstrings, written by legs that quote a
    handler to explain a fold.

    So this leg is where the two planes differ out loud: TypeScript gets a mask because the readings
    are textual, and Python gets ``ast.parse`` because it has one. It is also the self-audit that
    keeps the gate honest about its own words -- the fake routes are this file's, and a lane that
    quoted a route in a *new* place would move the register rather than slip past it.
    """
    gate_src = Path(__file__).resolve().read_text(encoding="utf-8")
    mentions = [(verb.lower(), path) for verb, path in _ROUTE_MENTION.findall(gate_src)]
    assert tuple(mentions) == _GATE_PROSE_ROUTE_MENTIONS, (
        f"route-shaped text this gate writes about itself moved: {mentions}"
    )

    module = ast.parse(gate_src)
    decorated = [
        node.name
        for node in ast.walk(module)
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)) and node.decorator_list
    ]
    assert not decorated, f"this gate defines real endpoints in code: {decorated}"

    published = {normalize_path(e.path) for e in endpoints(REPO)}
    invented = [path for _verb, path in mentions if path in published]
    assert not invented, (
        f"a route this file only mentions in prose is in the endpoint table: {invented}"
    )


_PROSE_FIXTURE_API_TS = '''import type { Thing } from "./types";

async function doFetch(path: string): Promise<unknown> {
  const resp = await fetch(path, { headers: { Authorization: "Bearer x" } });
  return resp.json();
}

export async function apiGet<T>(path: string): Promise<T> {
  return (await doFetch(path)) as T;
}

// apiGet<Thing>("/api/v1/p-line")
export async function getThing(): Promise<Thing> {
  /* apiGet<Thing>("/api/v1/p-sameline") */
  return apiGet<Thing>("/api/v1/p-code");
}

export async function getOther(): Promise<Thing> {
  /*
     apiGet<Thing>("/api/v1/p-block")
     fetch("/api/v1/p-block")
  */
  return apiGet<Thing>("/api/v1/p-code2");
}

const note = `apiGet<Thing>("/api/v1/p-template")`;

export function openThingStream() {
  return new EventSource("/api/v1/p-stream");
}

/**
 * JSDoc that mentions apiGet<Thing>("/api/v1/p-jsdoc") on one line.
 */
export function getThird(): Promise<Thing> {
  return apiGet<Thing>("/api/v1/p-code3");
}
'''

_PROSE_FIXTURE_PAGE_TSX = '''import { apiGet, getThing } from "../api";

export function useThing() {
  return apiGet<Thing>("/api/v1/p-hook");
}

export function ThingPage() {
  // const a = await apiGet<Thing>("/api/v1/p-page-line");
  const b = await getThing();
  /*
    const c = await apiGet<Thing>("/api/v1/p-page-block");
  */
  return null;
}
'''

_PROSE_FIXTURE_TYPES_TS = "export interface Thing { id: string }\n"


def test_the_splitter_boundary_population_is_zero_on_the_tree(tmp_path: Path) -> None:
    """The six shapes a quote-blind split cannot read, and the six zeros the tree answers with.

    #599 taught the member split to step over literals. On this tree that is not a repair: no
    declaration body carries a ``;`` or a brace inside a string, and every counterfactual below
    finds nothing to move. The zeros are measured, not asserted from a docstring -- the same walk
    is re-run with literal interiors blanked and compared with the raw one -- and the fixture at
    the bottom is the load test: each of the six shapes a quote-blind split gets wrong, read back
    whole, with the literal text still inside ``type_text``.
    """
    decl = ts_declarations(web_src(REPO))
    open_keys = open_key_types(web_src(REPO))
    bodies = _declaration_bodies(web_src(REPO), _DECLARATION_HEAD)
    aware = _declaration_bodies_quote_aware(web_src(REPO), _DECLARATION_HEAD)
    assert len(aware) == len(bodies), f"the two cuts found {len(aware)} and {len(bodies)} bodies"

    counts = dict.fromkeys(SPLITTER_BOUNDARY_POPULATION, 0)
    for (name, _rel, body), (_aware_name, _r, aware_body) in zip(bodies, aware, strict=True):
        if _literals_holding_structure(body):
            counts["bodies_with_literal_structure"] += 1
        if body != aware_body:
            counts["cuts_moved_by_quote_awareness"] += 1
        blind = [
            _chunk_name(chunk)
            for chunk, is_member in _chunk_walk(body, _MEMBER_HEAD)
            if is_member
        ]
        steered = _split_stepping_over_literals(body)
        if blind != steered:
            counts["splits_moved_by_quote_awareness"] += 1
        entry = decl.get(name)
        if entry is None:
            continue
        owner_names = [item.name for item in entry[1]]
        registered = _chunk_name(open_keys[name][1]) if name in open_keys else None
        if owner_names != [member for member in steered if member != registered]:
            counts["members_moved_on_tree"] += 1
    for site in frontend_calls(web_src(REPO))[0]:
        if site.type_expr.strip().startswith("{") and _literals_holding_structure(site.type_expr):
            counts["inline_exprs_at_risk"] += 1
    counts["members_invented_by_prose"] = sum(
        1
        for _n, _r, body in bodies
        for chunk, _is_member in _chunk_walk(body, _MEMBER_HEAD)
        if re.search(r"//|/\*", chunk)
    )
    assert counts == SPLITTER_BOUNDARY_POPULATION, (
        f"the splitter's blind side is populated on this tree: {counts}"
    )

    planted = _fixture_web(
        tmp_path,
        {
            "Lit.ts": (
                "export interface Lit {\n"
                '  semi: "a;b";\n'
                "  brace: 'a}b';\n"
                "  template: `a{b;c`;\n"
                '  escaped: "a\\"; b";\n'
                '  apos: "it\'s; fine";\n'
                '  nested: { inner: "a;b"; other: number };\n'
                "  tail: string;\n"
                "}\n"
            )
        },
    )
    read = ts_declarations(planted)
    members = {item.name: item.type_text for item in read["Lit"][1]}
    assert list(members) == ["semi", "brace", "template", "escaped", "apos", "nested", "tail"], (
        f"a literal shape truncated the split: {list(members)}"
    )
    assert members["semi"] == '"a;b"'
    assert members["brace"] == "'a}b'"
    assert members["template"] == "`a{b;c`"
    assert members["escaped"] == '"a\\"; b"'
    assert members["apos"] == '"it\'s; fine"'
    assert "a;b" in members["nested"] and "other: number" in members["nested"]
    assert _literals_holding_structure(
        (planted / "Lit.ts").read_text(encoding="utf-8")
    ), "the fixture stopped carrying the structure it plants"


def test_the_body_cut_steps_over_literals(tmp_path: Path) -> None:
    """``_block_after`` counts braces; a ``}`` written in a string used to close the type.

    The fixture is the smallest shape that shows the cost: the first member's literal holds a
    closing brace, so a quote-blind cut ends the body inside the literal and everything after it
    is answered "not declared". The real-tree half is the same counterfactual as the population
    leg, kept here because this leg is the one that would go red if only the cut regressed.
    """
    planted = _fixture_web(
        tmp_path,
        {
            "Cut.ts": (
                "export interface Cut {\n"
                '  left: "a}" | "b{";\n'
                "  right: number;\n"
                "}\n"
                "export interface After { id: string }\n"
            )
        },
    )
    read = ts_declarations(planted)
    assert [item.name for item in read["Cut"][1]] == ["left", "right"], (
        f"a brace in a literal ended the body early: {[i.name for i in read['Cut'][1]]}"
    )
    assert read["Cut"][1][0].type_text == '"a}" | "b{"'
    assert [item.name for item in read["After"][1]] == ["id"]

    bodies = _declaration_bodies(web_src(REPO), _DECLARATION_HEAD)
    aware = _declaration_bodies_quote_aware(web_src(REPO), _DECLARATION_HEAD)
    moved = [
        name
        for (name, _rel, body), (_n, _r, aware_body) in zip(bodies, aware, strict=True)
        if body != aware_body
    ]
    assert not moved, f"stepping over literals moved the body of {moved[:6]}"


def test_the_open_key_types_are_the_chunks_the_splitter_used_to_lose() -> None:
    """Two tables that must move together: the census's losses and the type's open keys.

    #581 filed ``[key: string]: unknown`` as a chunk the splitter threw away. It was never
    thrown away -- it is the declaration saying it admits keys nobody wrote -- so it moved to
    ``OPEN_KEY_TYPES`` and ``MEMBER_CHUNK_LOSSES`` emptied. This leg recomputes the chunk census
    against the reading and *requires* the unread set to be exactly the registered open keys:
    break the exit and the chunk census grows a loss row (arm L5 measured both going red).
    """
    web = web_src(REPO)
    decl = ts_declarations(web)
    open_keys = open_key_types(web)
    assert open_keys == OPEN_KEY_TYPES, f"the open-key table drifted: {open_keys}"
    assert len(MEMBER_CHUNK_LOSSES) + len(OPEN_KEY_TYPES) == 1, (
        f"the one chunk and the one open key: {MEMBER_CHUNK_LOSSES} vs {OPEN_KEY_TYPES}"
    )
    assert not set(MEMBER_CHUNK_LOSSES) & set(OPEN_KEY_TYPES), (
        "a chunk cannot be both a registered loss and an open key"
    )

    unread: dict[str, str] = {}
    for name, _rel, body in _declaration_bodies(web, _DECLARATION_HEAD):
        entry = decl.get(name)
        if entry is None:
            continue
        kept = {item.name for item in entry[1]}
        for chunk, is_member in _chunk_walk(body, _MEMBER_HEAD):
            if is_member and _chunk_name(chunk) not in kept:
                unread[name] = " ".join(chunk.split())
    assert set(unread) == set(OPEN_KEY_TYPES), (
        f"the chunk census and the open-key table disagree: unread={unread} "
        f"open={OPEN_KEY_TYPES}"
    )
    assert all(unread[name] == text for name, (_host, text) in OPEN_KEY_TYPES.items()), (
        f"the registered signature is not the chunk the splitter reads: {unread}"
    )


def test_the_comparison_ledger_accounts_for_every_pair() -> None:
    """Every pair is either compared or named with the reason it is not.

    48 pairs, 44 compared, three payloads that do not fold, one type expression the reader
    cannot open, and -- the row #599 adds -- zero pairs typed by a type that admits any key.
    Before this ledger the four exclusions were invisible: "44 did not drift" and "four I could
    not read" had the same shape on the account.
    """
    _endpoints, pairs, _orphans, declarations = _census()
    open_types = frozenset(open_key_types(web_src(REPO)))
    tally = dict.fromkeys(COMPARISON_LEDGER, 0)
    for pair in pairs:
        reason, _required, _optional = _classify_pair(pair, declarations, open_types)
        tally["compared" if reason is None else reason] += 1
    assert tally == COMPARISON_LEDGER, f"the comparison denominator moved: {tally}"
    assert sum(COMPARISON_LEDGER.values()) == len(pairs), (
        f"the ledger accounts for {sum(COMPARISON_LEDGER.values())} of {len(pairs)} pairs"
    )
    compared = _checked_pairs(pairs, declarations)
    assert len(compared) == COMPARISON_LEDGER["compared"]


def test_the_literal_text_survives_the_member_reading() -> None:
    """Stepping over a literal is a scan, not an erasure -- the K4 hazard made permanent.

    26 declarations carry a string literal in a member's type (``"accept" | "reject"`` and the
    like). The shape mask blanks exactly that text, so a content reading that reached for it
    would answer every one of these types with an empty union. This leg walks the same bodies,
    takes each literal's interior, and requires it verbatim inside the ``type_text`` the owner
    reported -- a floor of 26 because a tree that stopped writing literal unions would make the
    fence vacuous.
    """
    decl = ts_declarations(web_src(REPO))
    literal_decls: set[str] = set()
    missing: list[str] = []
    for name, _rel, body in _declaration_bodies(web_src(REPO), _DECLARATION_HEAD):
        entry = decl.get(name)
        if entry is None:
            continue
        types = {item.name: item.type_text for item in entry[1]}
        for chunk, is_member in _chunk_walk(body, _MEMBER_HEAD):
            if not is_member:
                continue
            head = re.match(r"^\s*(?:readonly\s+)?(\w+)(\?)?\s*:\s*(.+)$", chunk, re.S)
            if head is None:
                continue
            _prose, spans = _ts_tokens(head.group(3))
            for start, stop in spans:
                inner = head.group(3)[start + 1 : stop - 1]
                if not inner:
                    continue
                literal_decls.add(name)
                if inner not in types.get(head.group(1), ""):
                    missing.append(f"{name}.{head.group(1)} lost {inner!r}")
    assert not missing, f"the member reading blanked literal text: {missing[:6]}"
    assert len(literal_decls) >= _MIN_LITERAL_TYPE_DECLARATIONS, (
        f"only {len(literal_decls)} declarations carry a literal in a member type; the 26 "
        f"whose type_text K4 measured being erased are no longer reachable"
    )


def test_an_inline_type_expression_is_masked_before_members_are_read() -> None:
    """L3's ruler: the inline ``{...}`` is a content reading, so prose is blanked first.

    ``members_of_type`` reads an inline expression with ``_block_after``. Without the mask a
    ``}`` written in a comment closes the expression where the comment sits: this fixture
    answers ``id`` and ``tail`` when the prose is blanked, and ``id`` alone when it is not.
    ``_MASK_SITES`` records the topology -- that the inline path calls ``_mask_prose`` -- but a
    roster cannot see a member go missing, which is what the L3 arm measured.
    """
    expr = "{ id: string; /* } */ tail: number; }"
    required, optional, notes = members_of_type(expr, {})
    assert (required, optional, notes) == ({"id", "tail"}, set(), []), (
        "the inline expression lost a member behind prose: "
        f"{(required, optional, notes)}"
    )


def test_prose_cannot_invent_a_member(tmp_path: Path) -> None:
    """⑭: the mask is the only prose rule, so a comment cannot become a field.

    The member reader used to carry its own two ``re.sub`` calls on top of the mask; #599
    deleted them after measuring that nothing reached them. This fixture writes the same
    ``phantom: string;`` in the four comment spellings and requires the reading to answer one
    field: the mask runs first, and nothing after it searches for a second opinion about prose.
    """
    planted = _fixture_web(
        tmp_path,
        {
            "Ghost.ts": (
                "export interface Ghost {\n"
                "  // phantom: string;\n"
                "  /* phantom: string; */\n"
                "  /*\n"
                "     phantom: string;\n"
                "  */\n"
                "  /**\n"
                "   * phantom: string;\n"
                "   */\n"
                "  real: string; /* phantom: string; */\n"
                "}\n"
            )
        },
    )
    read = ts_declarations(planted)
    names = [item.name for item in read["Ghost"][1]]
    assert names == ["real"], f"prose became a member: {names}"
    assert "phantom" not in names


def test_the_mask_leg_asserts_shape_before_it_indexes_by_position() -> None:
    """⑬: a mask that moves columns must fail as an assertion, never as an IndexError.

    ``test_the_mask_blanks_prose_only_and_the_shape_step_blanks_literals_only`` walks the masked
    text by index. #599's K2 arm moved a column and the walk crashed instead of reporting the
    mask, which is a red leg turning into a broken one. The width assertion now runs before the
    first positional read; this leg reads the leg's own source and refuses the old order.
    """
    source = Path(__file__).resolve().read_text(encoding="utf-8")
    module = ast.parse(source)
    leg = next(
        node
        for node in ast.walk(module)
        if isinstance(node, ast.FunctionDef)
        and node.name == "test_the_mask_blanks_prose_only_and_the_shape_step_blanks_literals_only"
    )
    width_lines = [
        node.lineno
        for node in ast.walk(leg)
        if isinstance(node, ast.Assert) and "width_moved" in ast.dump(node.test)
    ]
    walk_lines = [
        node.lineno
        for node in ast.walk(leg)
        if isinstance(node, ast.For)
        and isinstance(node.iter, ast.Call)
        and isinstance(node.iter.func, ast.Name)
        and node.iter.func.id == "enumerate"
        and bool(node.iter.args)
        and isinstance(node.iter.args[0], ast.Name)
        and node.iter.args[0].id == "raw"
    ]
    assert width_lines, "the mask leg no longer asserts that the mask keeps the text's width"
    assert walk_lines, "the mask leg no longer walks the masked text by position"
    assert min(width_lines) < min(walk_lines), (
        f"the width assertion at {min(width_lines)} runs after the positional walk at "
        f"{min(walk_lines)}: a mask that moves columns would crash the leg instead of failing it"
    )

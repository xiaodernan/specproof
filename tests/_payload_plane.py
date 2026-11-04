"""One owner for the plane a payload contract is checked against.

WHY THIS EXISTS. ``apps/web/src/api.ts`` declares, in TypeScript, what the browser
believes a response looks like. ``api/routes/*.py`` publishes, in Python, what the
response actually is. Nothing in the repository compared the two before #543: the
only witness was a hand-rolled regex inside each of four test files, and those four
copies disagreed about what an interface even is (one read ``api.ts`` only, so the
two *private* interfaces in ``agent/pages/AgentSettings.tsx`` were invisible to it).

#542 landed the first real hole found by hand -- a required key the degraded branch
did not answer -- and its D-section leg checks exactly one endpoint. A hole of that
shape, on any other endpoint, is silent today: the browser reads ``undefined`` and
renders it as a zero, an empty string, or a missing card.

THE RULES, each one sentence:

  E1  an endpoint is ``@<router>.<verb>("<path>")`` on a router object the module
      itself declares; the prefix is read from that declaration, never assumed.
  E2  a frontend call site is ``apiGet/Post/Put/Patch/Delete(<Type>?)(<first arg>)``;
      the path is read concatenation-aware -- quoted literals keep their text,
      anything else contributes one ``{}`` slot. A site whose path comes from a
      variable cannot be paired, and says so.
  E3  a pair is ``(verb, normalized path)``. The verb is part of the identity: the
      same path serves a GET list and a POST create with different payloads, and a
      path-only pairing invents mismatches (measured while writing this: it produced
      two false "required-not-published" findings on ``/agent/jobs``).
  E4  the published key set is folded, with a stated depth limit. Foldable: a dict
      literal; a local name bound to one; ``name.update(k=...)`` / ``name["k"] = ...``;
      ``**name`` / ``**call()``; ``return helper(...)`` one module-hop and two hops
      through the import graph. NOT foldable, and reported as unbounded rather than
      guessed: a comprehension whose keys come from data (``public_model_config``),
      a ``|`` whose left side is unbounded, a call into a module we cannot resolve.
  E5  the check is PER BRANCH. A route that answers key set A on the happy path and B
      on the degraded path does not "publish A ∪ B" -- the browser gets whichever it
      got, so every required key must appear in every branch. This is the #542 hole
      and the reason ``total`` over branches would be a weaker rule.
  E6  a consumer is not only a client function. A typed hook that declares its own
      shape and issues exactly one client request inside its body
      (``useRemoteData<T>(path)`` -> ``apiGet<T>(path, signal)``) is a call site whose
      verb is READ from the body, never declared next to the name.
  E7  an argument may be a conditional -- ``jobId ? "/api/v1/jobs/" + id + "/matrix"
      : null`` -- and then exactly one of its branches is a path. The ``?`` of a
      ternary and the ``?`` that opens a query string are the same character, so the
      split happens on a copy whose string literals are masked first. Two path-shaped
      branches are refused, not merged: one site may not be paired with two endpoints.

  E8  the consumer population is not only what a name can reach. An issuer is a
      definition in the client module that writes a transport or writes a client verb or
      writes an issuer, an issuer of the second kind is any other function whose body
      reaches one, and a site is any line that writes one of those names -- so a helper,
      a function that reaches an issuer without being spelled `use*` and a page that
      writes ``fetch`` itself are all in the denominator whether or not
      ``_consumer_names`` can say their names.
Test files under ``__tests__`` are excluded from pairing: they assert against mocks,
so a mismatch there is not a user-visible one. The exclusion is a *counted* rule
(``excluded_call_sites``), so it cannot quietly become the whole population.
"""

from __future__ import annotations

import ast
import re
from collections.abc import Callable, Iterable
from dataclasses import dataclass, field
from pathlib import Path

from tests._scan_walk import product_roots

#: How many module hops a payload fold may follow. Two covers `route -> service -> store`
#: (measured: `/jobs`); three would be guessing.
_PAYLOAD_DEPTH = 2

#: Files that are not consumers of the product's payloads.
_TEST_PATH_PARTS = ("__tests__",)
_TEST_SUFFIXES = (".test.ts", ".test.tsx")

HTTP_VERBS = ("get", "post", "put", "patch", "delete")
#: The client functions, and nothing else. A *hook* is deliberately not listed by name:
#: `hook_readings` decides which `use*` functions are consumers by reading the request
#: out of their bodies, so a lane that writes a second typed hook extends the consumer
#: population without editing the ruler -- and the gate rosters what it then believed.
_CLIENT_VERBS = {
    "apiGet": "get",
    "apiPost": "post",
    "apiPut": "put",
    "apiPatch": "patch",
    "apiDelete": "delete",
}


@dataclass(frozen=True)
class Endpoint:
    module: str
    router: str
    verb: str
    path: str
    handler: str
    line: int

    @property
    def key(self) -> tuple[str, str]:
        return (self.verb, normalize_path(self.path))


@dataclass(frozen=True)
class CallSite:
    file: str
    line: int
    verb: str
    path: str
    type_expr: str
    #: Where the declared type was read from: the call's own generic argument, the
    #: enclosing function's `Promise<T>` return type, or nowhere.
    typed_by: str = "none"
    #: Same-file aliases this argument was rewritten through, in the order used. Empty
    #: unless the path came from a `const name = "/api/..."` rather than a literal.
    via_aliases: tuple[str, ...] = ()
    #: The conditional branch this path was taken from, as written. Empty unless the
    #: argument is a ternary and exactly one of its branches folds to a path.
    via_conditional: tuple[str, ...] = ()
    #: The consumer name that is not an api client when this site was read through it
    #: (`useRemoteData`), empty for a site that came straight from a client call. A hook
    #: that stopped being read loses its sites without failing a floor, so the count
    #: belongs to the register that names the hook.
    via_hook: str = ""

    @property
    def candidates(self) -> tuple[str, ...]:
        return path_candidates(self.path)

    @property
    def key(self) -> tuple[str, str]:
        return (self.verb, self.candidates[0])


@dataclass(frozen=True)
class HookReading:
    """One exported ``use*`` function and the client requests its body issues.

    The verb list is read from the body, in source order: one request makes the hook a
    consumer whose declared shape is its own type argument, two or more mean a call site
    cannot be attributed to one verb, and the gate registers the refusal instead of
    picking the first.
    """

    name: str
    file: str
    line: int
    verbs: tuple[str, ...]


@dataclass(frozen=True)
class BlindSpot:
    """One frontend shape the census recognizes and does not read.

    ``name`` is the hook or the client the shape was found on, ``file`` and ``line`` point
    at the construct, and ``seen`` / ``read`` carry the two counts that a reader cannot
    get from the code without re-deriving them: what the construct holds and what the
    ruler took. Rows are sorted, so a register written against this exit compares
    positionally as well as by name.
    """

    shape: str
    name: str
    file: str
    line: int
    seen: tuple[str, ...]
    read: tuple[str, ...]


@dataclass(frozen=True)
class Pair:
    """One frontend call site and the endpoint that answers it.

    ``exact`` is False when the pairing only worked after dropping a reading of the
    variable-suffix kind -- a slot no ``/`` introduces. The gate registers those
    pairings by name instead of letting them pass for an exact contract.
    """

    site: CallSite
    endpoint: Endpoint
    exact: bool


@dataclass(frozen=True)
class Member:
    name: str
    optional: bool
    type_text: str


@dataclass(frozen=True)
class CallShape:
    """One call-shaped mention of an api client, kept or rejected, with its left window.

    ``window`` is the text the definition guard reads. A gate needs it to check that
    everything the guard rejected *is* a declaration, because the guard is the only
    place where a consumer can disappear without an error (#543 measured eight).
    """

    file: str
    line: int
    name: str
    is_call: bool
    window: str


@dataclass
class Payload:
    """What the fold can say about one handler: per-branch key sets, or why it cannot.

    ``branches`` is empty exactly when every return was unbounded.

    ``conditional`` names the fold's one known overstatement. Keys added by
    ``name.update(...)`` / ``name["k"] = ...`` merge into every branch, because
    telling "set on both the try and the except arm" (so always present) from "set
    only inside one `if`" (so sometimes absent) needs control-flow paths this owner
    does not build. ``conditional`` records the keys that were mutated from a nested
    statement, so the gate can *roster* the overstatement instead of pretending it
    does not exist: a hole of the "only published on one control path" shape is out of
    this number's reach, and is registered as such rather than claimed as covered.
    """

    branches: list[set[str]] = field(default_factory=list)
    unbounded: list[str] = field(default_factory=list)
    conditional: set[str] = field(default_factory=set)

    @property
    def published(self) -> set[str]:
        out: set[str] = set()
        for keys in self.branches:
            out |= keys
        return out

    @property
    def always(self) -> set[str]:
        """Keys every branch publishes -- the only set a frontend may treat as present."""
        if not self.branches:
            return set()
        out = set(self.branches[0])
        for keys in self.branches[1:]:
            out &= keys
        return out


@dataclass(frozen=True)
class OptionalBand:
    """One endpoint's reading of the keys the frontend marks optional.

    The bands answer three different questions and only the first is a promise:

    ``always``     -- every branch publishes it, the fold merged none of it in from a
                      nested statement, and ``complete`` says the branch list is all the
                      handler's exits. This is the set a frontend may stop defending.
    ``overstated`` -- in ``always`` only because ``Payload.conditional`` merged it in: the
                      fold cannot tell "set on both arms" from "set inside one ``if``", so
                      these keys are present on some paths and are rostered apart.
    ``sometimes``  -- published on some branches and not others. The intersection may not
                      report it and the union may not swallow it; population 0 today, and
                      an arm proves the band is not a decorative zero.
    ``absent``     -- no branch publishes it and nothing merged it: the frontend is
                      defending against a key that cannot arrive.

    One row per *endpoint*, not per call site: five of the speakable sites are two
    readings of the same route, and a roster of routes is what the leg compares. Rows are
    sorted, so a register compares positionally as well as by name.
    """

    verb: str
    path: str
    file: str
    line: int
    always: tuple[str, ...]
    overstated: tuple[str, ...]
    sometimes: tuple[str, ...]
    absent: tuple[str, ...]
    complete: bool


@dataclass(frozen=True)
class ReturnAccount:
    """Whether the branch list a payload reports is all the exits the handler has.

    ``own_returns`` counts the ``return`` statements in the handler's own scope; a
    ``return`` inside a nested ``def``/``lambda`` belongs to that callable, not to the
    response. ``branches`` is what the fold reported. The two differ for two reasons, and
    telling them apart is the entire row: the fold *said* so (``unbounded`` names the
    return it refused) or it stayed silent -- it read one exit and reported a census.

    ``-1`` means the handler could not be found in its module: not zero returns, and never
    a number the fuse may read as "the fold saw everything".
    """

    verb: str
    path: str
    module: str
    handler: str
    own_returns: int
    branches: int
    unbounded: tuple[str, ...]

    @property
    def complete(self) -> bool:
        """The one condition under which ``Payload.always`` is a proof rather than a read."""
        return self.branches == self.own_returns and not self.unbounded


def _own_return_count(root: Path, endpoint: Endpoint) -> int:
    """`return` statements in the handler's own scope, nested callables excluded.

    Reuses ``_own_nodes`` -- the walker the fold itself uses to collect bindings -- rather
    than writing a second traversal. A second walker would be a second definition of "the
    handler's own body", and the fuse and the fold would then be able to disagree about
    which statements they are reading, which is the drift this whole plane exists to make
    loud.
    """
    module_path = root / (endpoint.module.replace(".", "/") + ".py")
    tree = _parse(module_path)
    if tree is None:
        return -1
    handler = _find_function(tree, endpoint.handler)
    if handler is None:
        return -1
    return sum(1 for node in _own_nodes(handler) if isinstance(node, ast.Return))


def _speakable_endpoints(root: Path) -> list[tuple[Pair, set[str], set[str], Payload]]:
    """Paired endpoints whose both sides have a readable shape, one entry per endpoint.

    The gate's ``_checked_pairs`` filters the same way per *site*; these two registers are
    rosters of *routes*, so a path paired by two call sites must not appear twice. The
    site that survives is the first in (verb, path, file, line) order, which is why the
    sort happens before the dedup and not after.
    """
    pairs, _orphan = pairings(root)
    declarations = ts_declarations(web_src(root))
    ordered = sorted(
        pairs,
        key=lambda p: (
            p.endpoint.verb,
            normalize_path(p.endpoint.path),
            p.site.file,
            p.site.line,
        ),
    )
    seen: set[tuple[str, str]] = set()
    out: list[tuple[Pair, set[str], set[str], Payload]] = []
    for pair in ordered:
        required, optional, notes = members_of_type(pair.site.type_expr, declarations)
        if notes or not (required or optional):
            continue
        key = pair.endpoint.key
        if key in seen:
            continue
        seen.add(key)
        out.append((pair, required, optional, payload_of(root, pair.endpoint)))
    return out


def optional_publish_bands(root: Path) -> list[OptionalBand]:
    """Axis (c): what a key the frontend declares *optional* actually is.

    Axis (a) (#542) asks whether a required key really arrives. Axis (b) (#543/#544) asks
    whether a published key was ever declared. The third direction had no reading at all,
    so the one place in the frontend that records a decision in prose -- ``api.ts`` making
    ``JobsPage.total`` required, with a comment explaining that reading that field as a
    count told a workspace with 57 verifications that it had 1 -- could be contradicted by
    a page that still writes ``total?: number`` and turns the missing key into ``null``,
    with nothing in the census able to say so.

    Endpoints the fold refused to bound are absent from this register: with no branch list
    there is no intersection, and a band of "unknown" would read like a zero. They are
    counted where they are named (#543's unbounded roster), and ``return_accounting`` is
    what keeps that skip from hiding a branch list that was only half read.
    """
    rows: list[OptionalBand] = []
    for pair, _required, optional, payload in _speakable_endpoints(root):
        if payload.unbounded:
            continue
        endpoint = pair.endpoint
        intersection = set.intersection(*payload.branches)
        published = set().union(*payload.branches)
        merged_in = (optional & intersection) & payload.conditional
        provable = (optional & intersection) - merged_in
        some = (optional & published) - intersection - payload.conditional
        nowhere = optional - published - payload.conditional
        rows.append(
            OptionalBand(
                verb=endpoint.verb,
                path=normalize_path(endpoint.path),
                file=pair.site.file,
                line=pair.site.line,
                always=tuple(sorted(provable)),
                overstated=tuple(sorted(merged_in)),
                sometimes=tuple(sorted(some)),
                absent=tuple(sorted(nowhere)),
                complete=_own_return_count(root, endpoint) == len(payload.branches),
            )
        )
    return rows


@dataclass(frozen=True)
class ConsumerDefence:
    """Axis (d): what the call site's own body does with a key the route publishes.

    Axes (a)-(c) all read the *declaration*: a required key a branch forgot, a published key
    nobody declared, an optional key that always arrives. None of them reads the fourth place
    the same payload is written down -- the consumer. That gap has a cost in both directions:
    a page may guard a key the type says cannot be missing (so the guard is invisible to
    ``tsc`` and deleting it is silent), and a page may read a key the type never declares
    behind a guard that is the only reason the bug stays latent.

    One row per defended key at a site whose consumer sits inside the statement; a row with an
    empty ``key`` for every site that yields no defence, so "looked and found nothing" and "could
    not look" stay distinguishable and both are counted. ``declared`` is how the site's own type
    spells the key and ``published`` is the axis-(c) word for what the route does with it, so the
    join that used to need both sides of the fold is inside the row.

    A site is ``reached`` when the response is handed to code inside the same statement -- in
    this population that is ``.then(``, and nothing else: an ``await`` whose result is read in the
    *next* statement is outside the region, however many lines the call itself spans. The test is
    on the payload's path, not on the region's length, because a request written across four
    argument lines extends the region without ever reaching the consumer, and counting those as
    reads would report a census of 25 sites where only 8 carry a consumer.
    """

    verb: str
    path: str
    file: str
    line: int
    key: str
    kind: str
    declared: str
    published: str
    reached: bool
    span: int


def _mask_prose(text: str) -> str:
    """``//`` and ``/* ... */`` out, in place -- the one prose rule every TS reader shares.

    Length, newline count and columns are all preserved, so an offset in the masked text is the
    same offset in the file: a reader may decide code-ness here and still slice its content out of
    the original. Literals are stepped over, never blanked, because a route path *is* a string
    literal -- #555 measured what a mask that erased them costs (48 call sites read as 0).

    The block-comment branch is the reason this function exists. The mask it replaces knew only
    ``//``, applied per line, so a ``/* ... */`` opened on one line and closed on another stayed
    code at every granularity: its ``;`` ended a member chunk in ``ts_declarations``, which lost
    six real fields, and its text could be read as a consumer site by a lens that never asked who
    wrote it.
    """
    out = list(text)
    size = len(text)

    def blank(at: int) -> None:
        if text[at] != "\n":
            out[at] = " "

    i = 0
    while i < size:
        if text.startswith("//", i):
            j = i
            while j < size and text[j] != "\n":
                blank(j)
                j += 1
            i = j
        elif text.startswith("/*", i):
            end = text.find("*/", i + 2)
            stop = size if end < 0 else end + 2
            for j in range(i, stop):
                blank(j)
            i = stop
        elif text[i] in "'\"`":
            i = _end_of_literal(text, i)
        else:
            i += 1
    return "".join(out)


def _end_of_literal(text: str, start: int) -> int:
    """The index just past the literal that opens at ``start``.

    ``'`` and ``"`` end at their quote or at the line -- an apostrophe in prose that survived a
    partial mask must not swallow the rest of the file. A backtick runs to its own backtick and may
    cross lines, which is why the mask is applied to whole text and not line by line.
    """
    quote = text[start]
    i = start + 1
    while i < len(text):
        ch = text[i]
        if ch == "\\":
            i += 2
            continue
        if ch == quote:
            return i + 1
        if ch == "\n" and quote in "'\"":
            return i
        i += 1
    return i


def _blank_literals(text: str) -> str:
    """The inside of every literal in already-prose-free text, blanked in place."""
    out = list(text)
    i = 0
    while i < len(text):
        if text[i] in "'\"`":
            end = _end_of_literal(text, i)
            for j in range(i + 1, max(i + 1, end - 1)):
                if text[j] != "\n":
                    out[j] = " "
            i = end
        elif text[i] == "\\":
            i += 2
        else:
            i += 1
    return "".join(out)


def _mask_typescript(text: str) -> str:
    """Prose out, then string interiors out -- the *shape* reading, and only that.

    The rule #544 set for the path fold, applied to a consumer body: the reading counts code. It
    no longer deletes characters, so a column in the result is a column in the file, and no caller
    needs to mask line by line to keep its line numbers.

    No lens that reads content back out may use this: the payload path, an alias's target and a
    declared type's union members all live inside literals, which is exactly what this mask erases.
    Those read `_mask_prose`, and a call-shape test on top of it blanks literals only to answer a
    yes/no question.
    """
    return _blank_literals(_mask_prose(text))


#: Bracket pairs the region walk keeps balanced, in the order it reports them.
_TS_PAIRS = (("(", ")"), ("[", "]"), ("{", "}"))


def _consumer_region(lines: list[str], start: int) -> tuple[str, int]:
    """The statement a call site begins, extended while the following line continues it.

    ``lines`` are the file's masked lines (`_ts_masked_lines`), so what this walk calls "the next
    line" is already the next line of code: a comment between the request and its ``.then`` neither
    extends the region nor ends it as itself.

    An ``apiGet`` call puts its consumer on the *next* line (``.then((data) => ...)``), so a
    single-line read sees the request and never the defence. The extension keeps going while
    the expression is still open or the next line starts with the dot of a method chain. That
    brings a ``.then`` callback inside the region; it cannot bring in the statements after an
    ``await``, which is why the caller reports reach separately instead of trusting the span.
    """
    parts: list[str] = []
    depth = 0
    index = start
    while index < len(lines):
        line = lines[index]
        parts.append(line)
        depth += sum(line.count(open_) - line.count(close) for open_, close in _TS_PAIRS)
        following = lines[index + 1].lstrip() if index + 1 < len(lines) else ""
        continues = following.startswith((".", "?.", ":"))
        if depth <= 0 and not continues:
            break
        index += 1
    return "\n".join(parts), index - start + 1


def _defence_kind(before: str, after: str, chained: bool) -> str:
    """Which absence-handling shape surrounds one member access, or ``""`` for a plain read.

    Tested in this order, and the order is the definition: ``typeof data?.total === "number"``
    is a type test that *also* uses ``?.``, and counting it twice would make the register
    report a guard that is one expression.

    ``logical-or`` was added by #553 and is ranked **last**, after ``ternary``: it can name only
    an access nothing else claimed. ``data.jobs || []`` is a fallback on absence -- the
    campaign's own defect class, a missing key answered as "there are none" -- but a shape that
    outranked ``?.`` would relabel ``data?.jobs || []`` and move #552's register without one
    consumer changing.
    """
    if re.search(r"typeof\s*$", before):
        return "typeof"
    if after.lstrip().startswith("??"):
        return "nullish"
    if re.match(r"\s*[!=]==\s*undefined", after):
        return "undefined"
    if chained:
        return "optchain"
    if re.search(r"Array\.isArray\(\s*$", before):
        return "shape"
    head = after.lstrip()
    if head.startswith("?") and not head.startswith("?."):
        return "ternary"
    if re.match(r"\s*\|\|", after):
        return "logical-or"
    return ""


def _published_word(key: str, payload: Payload) -> str:
    """The axis-(c) word for what the route does with this key, from the same three sets."""
    intersection = set.intersection(*payload.branches) if payload.branches else set()
    merged = (payload.conditional & intersection) if payload.conditional else set()
    if key in intersection - merged:
        return "always"
    if key in merged:
        return "conditional"
    if key in set().union(*payload.branches) - intersection:
        return "sometimes"
    return "nowhere"


def consumer_defences(root: Path) -> list[ConsumerDefence]:
    """Every paired call site, and what its own body does with the keys of its payload.

    A site with no defence still leaves one row, keyed by nothing: the reading found no guard and
    the reading could not look are different claims, and only the second one is a hole in this
    export. ``reached`` follows the payload, not the region's length -- see ``ConsumerDefence``.
    """
    pairs, _orphan = pairings(root)
    fold: dict[tuple[str, int], tuple[set[str], set[str]]] = {}
    for pair, required, optional, _payload in _speakable_endpoints(root):
        fold[(pair.site.file, pair.site.line)] = (required, optional)

    rows: list[ConsumerDefence] = []
    for pair in sorted(pairs, key=lambda p: (p.site.file, p.site.line, p.endpoint.path)):
        site, endpoint = pair.site, pair.endpoint
        lines = _ts_masked_lines(root / site.file)
        region, span = _consumer_region(lines, site.line - 1)
        verb, path = endpoint.verb, normalize_path(endpoint.path)
        reached = ".then(" in region
        found: list[ConsumerDefence] = []
        if reached:
            payload = payload_of(root, endpoint)
            required, optional = fold.get((site.file, site.line), (set(), set()))
            for key in sorted(set(payload.published) | required | optional):
                access = re.compile(r"([A-Za-z_$][\w$]*)\??\.(" + re.escape(key) + r")\b")
                for match in access.finditer(region):
                    chained = region[match.start(2) - 2 : match.start(2)] == "?."
                    kind = _defence_kind(
                        region[max(0, match.start() - 24) : match.start()],
                        region[match.end() : match.end() + 24],
                        chained,
                    )
                    if not kind:
                        continue
                    found.append(
                        ConsumerDefence(
                            verb=verb,
                            path=path,
                            file=site.file,
                            line=site.line,
                            key=key,
                            kind=kind,
                            declared=(
                                "required"
                                if key in required
                                else "optional"
                                if key in optional
                                else "undeclared"
                            ),
                            published=_published_word(key, payload),
                            reached=True,
                            span=span,
                        )
                    )
        if found:
            rows.extend(found)
        else:
            rows.append(
                ConsumerDefence(
                    verb=verb,
                    path=path,
                    file=site.file,
                    line=site.line,
                    key="",
                    kind="",
                    declared="",
                    published="",
                    reached=reached,
                    span=span,
                )
            )
    return rows


#: The heads a ``{`` may belong to. A bare brace is not a block:
#: ``return apiGet<{ job: Job }>(...)`` opens a *type* object literal, and a walk that accepts
#: it reports a function body 400 lines away.
_TS_BLOCK_HEAD = re.compile(r"=>|\bfunction\b|\basync\b|\bfor\b|\bif\b|\btry\b|\bwhile\b")

#: The callee of a hook consumer, e.g. ``useRemoteData<JobsPage>(...)``.
_TS_HOOK_CALLEE = re.compile(r"\buse[A-Z][\w$]*\s*(?:<[^<>()]*>)?\s*\(")
_TS_AWAIT = re.compile(r"(?<![\w$])await\b")
_TS_DESTRUCTURE = re.compile(r"(?:const|let|var)\s*\{")
_TS_PLAIN_BIND = re.compile(r"(?:const|let|var)\s+[A-Za-z_$][\w$]*\s*(?::[^=]+)?=")
_TS_TUPLE_HEAD = re.compile(r"Promise\.all(?:Settled)?\s*\(\s*\[")

#: ``_binding_style``'s answer set, in the order it is tested. The order is the definition: a site
#: that both awaits and sits inside a tuple is a ``tuple-member``, because what decides where its
#: guard can be written is the tuple, not the keyword.
_CONSUMER_BINDING_STYLES = (
    "then-chain",
    "tuple-member",
    "hook",
    "forward",
    "destructuring",
    "discarded",
    "await-binding",
    "promise-bound",
)


def _statement_frame(lines: list[str], index: int, look_back: int = 2) -> str:
    """The site's own statement so far: from the last depth-0 ``;`` above it.

    Where a binding, an ``await`` or a rename has to be written to belong to *this* call. A binding
    can wrap onto the site line and the site line can end the statement, so one line either way is
    not enough; the semicolon boundary is what stops an unrelated ``await`` two lines up from
    promoting a parked promise into an awaited one.
    """
    joined = "\n".join(lines[k] for k in range(max(0, index - look_back), index + 1))
    # A ``;`` ends the statement only at depth 0 and only *before* the frame's own end:
    # ``apiGet<{ a: X[]; b: Y }>(...)`` puts one inside a type argument, and the site's terminating
    # ``;`` would otherwise cut the very binding this function exists to find.
    body = joined.rstrip()
    depth = 0
    boundary = -1
    for position, char in enumerate(body):
        if char in "([{":
            depth += 1
        elif char in ")]}":
            depth -= 1
        elif char == ";" and depth == 0 and position < len(body) - 1:
            boundary = position
    return joined[boundary + 1 :] if boundary >= 0 else joined


def _enclosing_block(lines: list[str], index: int) -> tuple[int, str]:
    """``(span, masked text)`` of the innermost block body around ``index``, or ``(0, "")``.

    Never falls back to the whole file. A silent fallback is how "I did not find it" becomes "there
    is nothing there": the probe that first measured this reading returned the file when the walk
    failed and reported a guard for ``api.ts:991`` that lived hundreds of lines away. An unresolved
    block is its own answer, and the legs count it.
    """
    pending = 0
    openers: list[int] = []
    for i in range(index, -1, -1):
        text = lines[i]
        for offset in range(len(text) - 1, -1, -1):
            if text[offset] == "}":
                pending += 1
            elif text[offset] == "{":
                pending -= 1
                if pending < 0:
                    openers.append(i)
                    pending = 0
    for opener in openers:
        head = lines[opener] + "\n" + lines[max(0, opener - 1)]
        if _TS_BLOCK_HEAD.search(head):
            depth = 0
            for j in range(opener, len(lines)):
                text = lines[j]
                depth += text.count("{") - text.count("}")
                if depth == 0 and j > opener:
                    return j - opener + 1, "\n".join(lines[k] for k in range(opener, j + 1))
    return 0, ""


def _tuple_head(lines: list[str], index: int, look_back: int = 12) -> int:
    """The ``Promise.all([`` a site sits inside, or ``-1``.

    Twelve lines: the longest tuple in this frontend spreads its members over six calls, and a
    member's own arguments can wrap. Beyond that the head is a different statement.
    """
    for i in range(index, max(-1, index - look_back), -1):
        if _TS_TUPLE_HEAD.search(lines[i]):
            return i
    return -1


def _tuple_reaches_then(lines: list[str], head: int) -> bool:
    """Does the tuple's own statement hand its responses over?

    Closed brace-by-brace, then ``.then``: a tuple member's consumer lives on the *closing*
    line (``])`` then ``.then(([a, b]) => ...)``),
    nine lines below the member that produced it, so axis (d)'s statement region misses a reach the
    statement plainly has. ``Promise.allSettled`` has no such line: it always resolves, so the
    ``.value`` guards sit in destructured locals the payload's key names never reach.
    """
    depth = 0
    for j in range(head, len(lines)):
        text = lines[j]
        depth += text.count("(") + text.count("[") + text.count("{")
        depth -= text.count(")") + text.count("]") + text.count("}")
        if depth == 0 and j > head:
            tail = "\n".join(lines[k] for k in range(j, min(len(lines), j + 4)))
            return ".then(" in tail
    return False


def _binding_style(lines: list[str], index: int, region: str) -> str:
    """How this call's response is handed over -- the reason axis (d) can or cannot look at it."""
    if ".then(" in region:
        return "then-chain"
    if _tuple_head(lines, index) >= 0:
        return "tuple-member"
    if _TS_HOOK_CALLEE.search(lines[index]):
        return "hook"
    frame = _statement_frame(lines, index)
    if region.strip().split("\n")[0].startswith("return"):
        return "forward"
    if _TS_DESTRUCTURE.search(frame):
        return "destructuring"
    if not _TS_PLAIN_BIND.search(frame):
        return "discarded"
    return "await-binding" if _TS_AWAIT.search(frame) else "promise-bound"


def _key_accesses(text: str, keys: Iterable[str]) -> list[tuple[str, str, str]]:
    """Every ``obj.key`` read of ``keys`` in ``text``, as ``(obj, key, kind)``.

    ``kind`` comes back empty for a read with no guard around it. One reader for both lenses
    on purpose: axis (d) and the binding census are then the same
    vocabulary seen through two different regions, and a shape added here is a shape the other
    reading gets too. ``chained`` is read off the two characters before the *key*, not before the
    whole match -- a match ends with the key, so slicing at its end returns the key's own tail and
    no optional chain is ever named.
    """
    out: list[tuple[str, str, str]] = []
    for key in sorted(keys):
        access = re.compile(r"([A-Za-z_$][\w$]*)\??\.(" + re.escape(key) + r")\b")
        for match in access.finditer(text):
            chained = text[match.start(2) - 2 : match.start(2)] == "?."
            kind = _defence_kind(
                text[max(0, match.start() - 24) : match.start()],
                text[match.end() : match.end() + 24],
                chained,
            )
            out.append((match.group(1), key, kind))
    return out


@dataclass(frozen=True)
class ConsumerBinding:
    """Axis (d)'s other half: how a site's response is bound, and what each of two lenses sees.

    ``consumer_defences`` answers "what guards does this site's own statement put on this key". It
    reads one region and looks only at sites whose statement contains ``.then(``, and #552 pinned
    that population at 8 of 48. Measured here, on the same pairings, are the two things that number
    was hiding: of those 8, only 2 read a payload key at all, and the other 40 sites are blind for
    reasons that have nothing to do with guards -- ``api.ts`` returns the payload whole (21 sites),
    tuple members wait for the tuple's callback (7), hook consumers hand the read to the hook (3),
    one site renames its key out of the dot-anchored reader's reach, two discard the response, and
    five bind it with ``await`` and then guard below the request.

    So ``style`` says why the statement lens is empty, ``statement_*`` repeats what axis (d) can
    see, and ``block_*`` says what the enclosing block has. The two guard columns are deliberately
    not merged into one table: a key guarded twice in one block, once as ``x?.k`` and once as
    ``x.k ?? y``, is two rows there and one (site, key) in axis (d), and flattening them would
    rewrite #552's rule rather than extend it.
    """

    verb: str
    path: str
    file: str
    line: int
    style: str
    keys: tuple[str, ...]
    statement_reads: tuple[str, ...]
    statement_kinds: tuple[str, ...]
    block_span: int
    block_reads: tuple[str, ...]
    block_kinds: tuple[str, ...]
    tuple_reaches_then: bool


def consumer_bindings(root: Path) -> list[ConsumerBinding]:
    """Every paired site, its binding style, and its two lenses -- no site left without a label.

    One row per paired site, which is the census's own floor: a site that gets no style would be
    silently excluded from the population, and the whole point of the reading is that the blind side
    is counted by *reason*. ``block_span`` is 0 where the walker refused to resolve a block, and
    then ``block_reads`` and ``block_kinds`` are empty because nothing was read -- not because
    there was nothing there.
    """
    pairs, _orphan = pairings(root)
    fold: dict[tuple[str, int], tuple[set[str], set[str]]] = {}
    for pair, required, optional, _payload in _speakable_endpoints(root):
        fold[(pair.site.file, pair.site.line)] = (required, optional)

    out: list[ConsumerBinding] = []
    for pair in sorted(pairs, key=lambda p: (p.site.file, p.site.line, p.endpoint.path)):
        site, endpoint = pair.site, pair.endpoint
        lines = _ts_masked_lines(root / site.file)
        index = site.line - 1
        region, _span = _consumer_region(lines, index)
        block_span, block = _enclosing_block(lines, index)
        payload = payload_of(root, endpoint)
        required, optional = fold.get((site.file, site.line), (set(), set()))
        keys = sorted(set(payload.published) | required | optional)
        statement = _key_accesses(region, keys)
        in_block = _key_accesses(block, keys)
        head = _tuple_head(lines, index)
        out.append(
            ConsumerBinding(
                verb=endpoint.verb,
                path=normalize_path(endpoint.path),
                file=site.file,
                line=site.line,
                style=_binding_style(lines, index, region),
                keys=tuple(keys),
                statement_reads=tuple(f"{obj}.{key}" for obj, key, _kind in statement),
                statement_kinds=tuple(f"{key}:{kind}" for obj, key, kind in statement if kind),
                block_span=block_span,
                block_reads=tuple(f"{obj}.{key}" for obj, key, _kind in in_block),
                block_kinds=tuple(f"{key}:{kind}" for obj, key, kind in in_block if kind),
                tuple_reaches_then=head >= 0 and _tuple_reaches_then(lines, head),
            )
        )
    return out


# ---------------------------------------------------------------------------
# E8 -- the denominator: who can put a request on the wire, read from the graph
#
# The consumer population the whole census is built on is a naming convention:
# `_consumer_names` is the five `api*` verbs plus the `use[A-Z]` hooks whose bodies issue one
# request. #553's arm K8 renamed `useRemoteData` to `fetchRemoteData` and five legs went red --
# four of them legs about other numbers' registers -- because the site left the census, and not
# one line in this repository records how many client calls the frontend has. So the denominator
# itself had no witness. This section reads the same plane a second way, without asking a name:
# an issuer is a definition in the client module whose body reaches a transport, a page-plane
# issuer is any other function whose body reaches one of those, and a site is a line that writes
# one.


#: What actually leaves the browser. A definition that writes one of these is the client
#: module's own transport wrapper, whatever it is called: `fetch`, `EventSource` and
#: `XMLHttpRequest` are the only three ways this frontend can ask the network a question.
_TRANSPORT_RE = re.compile(r"\bfetch\s*\(|\bnew\s+EventSource\b|\bXMLHttpRequest\b")

#: A top-level declaration of a function, in either spelling React allows on this tree.
#: `_HOOK_DEF` reads only the `function use*` form, which is why an arrow hook would widen
#: the consumer population without E6 ever seeing it; the graph reading starts from both.
_TS_FUNC_HEAD = re.compile(r"^(?:export\s+)?(?:async\s+)?function\s+(\w+)", re.M)
_TS_CONST_HEAD = re.compile(r"^(?:export\s+)?(?:const|let)\s+(\w+)\s*=\s*(?:async\s*)?\(", re.M)

#: `import { a, b as c } from "..."`, read up to the closing brace and no further. Read from the
#: *masked* copy on purpose: a specifier is a string literal and masking blanks it, but the
#: reading never asks where an import came from -- it asks which names arrived. The mask is what
#: lets a comment line inside a multi-line brace list stay out of the name list, which is the
#: accident #554's first measurement ran into on `JobDetail.tsx`.
_TS_BRACE_IMPORT = re.compile(r"^import\s+(?:type\s+)?\{([^}]*)\}", re.M)

#: The client module, by name. The reading walks the import graph but the *geography* is a
#: constant, same as `web_src`: one file is the client, and everything else is a caller.
_CLIENT_MODULE = "api.ts"

#: How many rounds the issuer closure may take before the reading reports what it has. This
#: tree converges in two: one productive round, one that adds nothing.
_MAX_CLOSURE_ROUNDS = 8


@dataclass(frozen=True)
class ClientExport:
    """A definition in the client module that can end up putting a request on the wire.

    ``depth`` is graph distance to a transport: 0 writes one itself, 1 reaches one through a
    client verb or through a depth-0 wrapper. ``via`` are the client-module names its body
    writes, so the two stream wrappers are told apart from the seven helpers by the name they
    reach rather than by the word in theirs. ``exported`` is not decoration: a page can only
    import an exported name, so the non-exported rows are where the closure starts and not what
    a caller calls.
    """

    name: str
    file: str
    line: int
    depth: int
    exported: bool
    via: tuple[str, ...]


@dataclass(frozen=True)
class DenominatorSite:
    """One frontend line that either reaches the network or is the definition that does.

    ``callee`` is the word actually written at the site, ``binding`` the name it was imported
    under -- the two differ exactly when the page renamed it on the way in, which is the one
    spelling a name-anchored census cannot follow. ``by_name`` is therefore read off ``callee``,
    not ``binding``: it says whether the *written* word is in the naming ruler's population, so
    an aliased import of a name the ruler owns still reports ``False``. The gap between the two
    denominators is a column rather than an argument, and ``kind`` is the first label the ordered
    vocabulary gives the line.

    A definition line is a row only for an issuer (`issuer-def`), and there it is the row that
    makes the *population* enumerable: the requests it will send are counted at their own lines.

    One line is one row. A line that writes two clients keeps the label the vocabulary ranks
    first, which is a choice: a per-name census would report more rows than there are sites, and
    then the two denominators would no longer be counts of the same thing.
    """

    file: str
    line: int
    callee: str
    kind: str
    by_name: bool
    binding: str


#: Ordered, first match wins -- the label a line gets is the first class whose test holds.
#: ``raw-transport`` comes first because a page that writes `fetch` bypassed the client module
#: entirely and no later label would say so. ``helper`` outranks ``stream`` because a wrapper
#: that both builds a path and opens a stream is first a path builder; the two stream rows on
#: this tree reach only the event-source wrapper, so the precedence is a rule for the case the
#: tree has not written yet. ``internal`` is last because every class above it is about a name
#: *arrived at from outside*, and inside the client module the names are the definitions.
#: ``issuer-*`` is not spelled ``hook-*``: the population is "a frontend function whose body
#: reaches the client module", and only three of this tree's seven carry the `use[A-Z]` shape --
#: the other four are components and a column factory, which is the finding, not a category error
#: the label should paper over.
DENOMINATOR_KINDS = (
    "raw-transport",
    "verb-name",
    "helper",
    "stream",
    "issuer-def",
    "issuer-call",
    "internal",
)


def _ts_masked(ts: Path) -> str:
    """The whole file through `_mask_typescript` once -- prose stops being code.

    Once, not line by line: the per-line loop existed only because the old mask rewrote a line's
    width, so joining its output was how line numbers survived. `_mask_typescript` preserves
    length, newlines and columns now, which means the same call answers the block-comment case the
    per-line shape could not see -- and it means a column in this text is a column in the file.
    """
    return _mask_typescript(ts.read_text(encoding="utf-8"))


def _ts_masked_lines(ts: Path) -> list[str]:
    """`_ts_masked` split into lines, for the readers that key a finding by `(file, line)`.

    Element ``i`` is line ``i + 1`` of the file, which is the arithmetic every caller of these
    helpers already does with `site.line - 1`. The split is on ``\\n``, not `splitlines`, so a
    trailing newline keeps its element and an index into the list is an index into the text.
    """
    return _ts_masked(ts).split("\n")


def _call_re(name: str) -> re.Pattern[str]:
    """A call of ``name`` that is not a member access and not another module's same word.

    ``(?<![\\w.$])`` is the whole rule: `x.apiGet(...)` and `myapiGet(...)` are not this
    function. The name is read before its generic argument or its paren, so `apiGet<{ a: { b:
    string } }>(...)` and `apiGet(...)` are the same site.
    """
    return re.compile(r"(?<![\w.$])" + re.escape(name) + r"\s*[<(]")


def _written_in(text: str, names: Iterable[str]) -> tuple[str, ...]:
    """Which of ``names`` this text calls, sorted -- the graph edge, spelled once."""
    return tuple(sorted(name for name in set(names) if _call_re(name).search(text)))


def _decl_body(masked: str, signature: int) -> str:
    """The text a declaration runs to: its block, or the expression an arrow returns.

    ``_function_body`` takes the next ``{`` after the signature, which for
    ``const f = (p) => g(p)`` is the brace of whatever declaration comes *next* -- so an
    expression-bodied arrow would be read as its successor's body, and inherit that
    function's transports and edges. This tree's client module has no such shape (49
    declarations, all spelled ``function``), which is exactly why the fixture leg writes one.
    """
    after = masked[signature:]
    arrow = re.match(r"\s*=>\s*", after)
    if arrow is not None and not after[arrow.end() :].startswith("{"):
        end = after.find(";", arrow.end())
        return after[arrow.end() :] if end == -1 else after[arrow.end() : end]
    body, _end = _function_body(masked, signature)
    return body


def _ts_declarations(masked: str) -> dict[str, tuple[str, int, bool]]:
    """name -> (body, declaration line, exported?) for one masked TypeScript file.

    First spelling wins, so a name declared twice keeps its first home and every count below
    stays one per name. A signature this cannot walk (`_past_paren` returning -1) is skipped
    rather than guessed at: an unreadable body yields no edges, and an issuer that loses its
    edges leaves the surface roster -- a loud place to fail, which is the point.
    """
    out: dict[str, tuple[str, int, bool]] = {}
    for head in (_TS_FUNC_HEAD, _TS_CONST_HEAD):
        for match in head.finditer(masked):
            name = match.group(1)
            if name in out:
                continue
            # ``match.end()`` sits *after* the parameter list's own ``(`` for a `const` head, and
            # ``_past_paren`` looks for the next ``(`` from there -- which is the first call in the
            # body, not the signature. One character back starts the walk on the right paren.
            signature = _past_paren(masked, match.end() - 1)
            if signature == -1:
                continue
            out[name] = (
                _decl_body(masked, signature),
                masked[: match.start()].count("\n") + 1,
                masked[match.start() : match.start() + 6] == "export",
            )
    return out


def _client_file(root: Path) -> Path:
    """The client module: `apps/web/src/api.ts`, the one file that is not a caller."""
    return web_src(root) / _CLIENT_MODULE


def _brace_imports(masked: str) -> list[tuple[str, str]]:
    """`(local, original)` for every brace import in a masked file, aliases included.

    A `type` prefix is stripped rather than dropped: `import { type Job, apiGet }` arrives in one
    chunk, and the shape half must not swallow the callable half sitting next to it.
    """
    out: list[tuple[str, str]] = []
    for match in _TS_BRACE_IMPORT.finditer(masked):
        for raw in match.group(1).split(","):
            parts = [part.strip() for part in raw.split(" as ")]
            if not parts or not parts[0]:
                continue
            spec = parts[0][5:].strip() if parts[0].startswith("type ") else parts[0]
            if spec and spec.isidentifier():
                out.append((parts[-1], spec))
    return out


def client_surface(root: Path) -> list[ClientExport]:
    """Every client-module definition that reaches a transport, with its distance and its edges.

    The closure is seeded two ways and then walked: a body that writes a transport is depth 0, a
    body that writes a declared verb is depth 1, and a body that writes either reaches the
    transport one hop further. No vocabulary of *helper* names is consulted, which is the point
    -- `downloadCapsule`, `logout` and the two stream wrappers are issuers because of what they
    call, and nothing in this file says so.
    """
    api = _client_file(root)
    if not api.exists():
        return []
    declarations = _ts_declarations(_ts_masked(api))

    depth: dict[str, int] = {}
    for name in sorted(declarations):
        body = declarations[name][0]
        if _TRANSPORT_RE.search(body):
            depth[name] = 0
        elif _written_in(body, _CLIENT_VERBS):
            depth[name] = 1

    rounds = 0
    while rounds < _MAX_CLOSURE_ROUNDS:
        rounds += 1
        grown = False
        for name in sorted(declarations):
            if name in depth:
                continue
            nearer = {
                depth[other] + 1 for other in depth if _call_re(other).search(declarations[name][0])
            }
            if nearer:
                depth[name] = min(nearer)
                grown = True
        if not grown:
            break

    rel = _rel_in_web(web_src(root), api)
    out: list[ClientExport] = []
    for name in sorted(depth):
        body, line, exported = declarations[name]
        out.append(
            ClientExport(
                name=name,
                file=rel,
                line=line,
                depth=depth[name],
                exported=exported,
                via=_written_in(body, depth),
            )
        )
    return out


def _issuers_outside_client(names: Iterable[str], web: Path) -> dict[str, tuple[str, int]]:
    """name -> (defining file, declaration line) for every function whose body reaches a client.

    Deliberately not restricted to the `use[A-Z]` spelling: E6's hook population is a name
    pattern, and a data-fetching function that stopped following it would leave E6's census
    behind while the graph kept its sites. A function that reaches two issuers is in here too --
    the ruler refuses it as a consumer because one type argument cannot serve two requests, and
    this reading counts its sites anyway.
    """
    clients = set(names)
    out: dict[str, tuple[str, int]] = {}
    for ts in _web_sources(web):
        if _is_test_file(ts):
            continue
        rel = _rel_in_web(web, ts)
        for name, (body, line, _exported) in _ts_declarations(_ts_masked(ts)).items():
            if name in clients or not _written_in(body, clients):
                continue
            out.setdefault(name, (rel, line))
    return out


def _denominator_kind(
    binding: str,
    *,
    from_import: bool,
    inside_client: bool,
    at_definition: bool,
    verbs: set[str],
    helpers: set[str],
    streams: set[str],
    issuers: set[str],
) -> str:
    """The first label in `DENOMINATOR_KINDS` whose test this line satisfies, or "" for none.

    ``issuers`` is the graph's own population -- any page function whose body reaches the client
    module -- so ``issuer-def``/``issuer-call`` say where the line sits in such a function, not
    what it is called. E6's `use[A-Z]` pattern is one of the two columns the gate compares against
    this, and the rows it cannot name are the finding rather than a flaw in the walk.
    """
    if from_import:
        if binding in verbs:
            return "verb-name"
        if binding in helpers:
            return "helper"
        if binding in streams:
            return "stream"
        if binding in issuers:
            return "issuer-call"
        return ""
    if inside_client:
        return "internal"
    if binding in issuers:
        return "issuer-def" if at_definition else "issuer-call"
    return ""


def _transport_word(text: str) -> str:
    """Which transport a page wrote, as a callee name."""
    if "XMLHttpRequest" in text:
        return "XMLHttpRequest"
    if "EventSource" in text:
        return "EventSource"
    return "fetch"


def denominator_sites(root: Path) -> list[DenominatorSite]:
    """Every frontend line that writes a client name or a transport -- the denominator, name-free.

    Three classes show up here that the naming ruler cannot see by construction: a helper its
    vocabulary never named, a function that reaches an issuer without the `use[A-Z]` spelling --
    on this tree four of the seven such functions have no hook name at all -- and a page that
    writes `fetch` itself. A fourth class -- an import that renames its callee -- is handled
    rather than measured, because renaming is the edit that #553's arm K8 proved could happen:
    `binding` keeps the exported name, `callee` the one written.

    A name the ruler *does* know can still be under-counted: `useAgentJob` is in
    `_consumer_names`, yet the census has one row for it (the request inside its body) while 11
    pages call it. Those sites are rows here with `by_name=True`, which is what lets the gate
    state the difference as "named, but not counted" rather than "invisible".

    The import's *specifier* is not resolved, only its braces: today every caller of the client
    module spells it `api`, and a page that imported `downloadCapsule` from a mock would be
    counted as a consumer of the real one. That is the same hole #527 recorded about the
    census's roots, and it is registered in the gate rather than papered over here.
    """
    web = web_src(root)
    surface = client_surface(root)
    if not surface:
        return []
    api_rel = surface[0].file
    verbs = set(_CLIENT_VERBS)

    # Both of this frontend's transports are `fetch`, so no transport *word* separates a stream
    # from a helper. The graph does: a stream reaches a transport wrapper that none of the
    # declared client verbs ever reaches, which is a fact about the wire, not about a name.
    wrappers = {row.name for row in surface if row.depth == 0}
    verb_wrappers = {
        name for row in surface if row.name in verbs for name in row.via if name in wrappers
    }
    streams = {
        row.name for row in surface if row.depth > 0 and set(row.via) & (wrappers - verb_wrappers)
    }
    helpers = {
        row.name
        for row in surface
        if row.depth > 0 and row.name not in verbs and row.name not in streams
    }
    issuer_names = {row.name for row in surface}
    page_issuers = _issuers_outside_client(issuer_names, web)
    issuer_def_names = set(page_issuers)
    known = verbs | issuer_names | issuer_def_names
    named = set(_consumer_names(web))

    rows: dict[tuple[str, int], DenominatorSite] = {}

    def add(rel: str, line: int, site: DenominatorSite) -> None:
        found = rows.get((rel, line))
        if found is None or DENOMINATOR_KINDS.index(found.kind) > DENOMINATOR_KINDS.index(
            site.kind
        ):
            rows[(rel, line)] = site

    for ts in _web_sources(web):
        if _is_test_file(ts):
            continue
        rel = _rel_in_web(web, ts)
        masked = _ts_masked(ts)
        inside = rel == api_rel

        imported: dict[str, str] = {}
        for local, spec in _brace_imports(masked):
            if spec in known:
                imported[local] = spec
        bound = dict(imported)
        if inside:
            for name in issuer_names:
                bound.setdefault(name, name)
        for name, (issuer_file, _line) in page_issuers.items():
            if issuer_file == rel:
                bound.setdefault(name, name)

        for local, binding in sorted(bound.items()):
            home = page_issuers.get(binding)
            for site in _call_re(local).finditer(masked):
                line = masked[: site.start()].count("\n") + 1
                kind = _denominator_kind(
                    binding,
                    from_import=local in imported,
                    inside_client=inside,
                    at_definition=home is not None and home == (rel, line),
                    verbs=verbs,
                    helpers=helpers,
                    streams=streams,
                    issuers=issuer_def_names,
                )
                if not kind:
                    continue
                add(
                    rel,
                    line,
                    DenominatorSite(
                        file=rel,
                        line=line,
                        callee=local,
                        kind=kind,
                        by_name=local in named,
                        binding=binding,
                    ),
                )

        if inside:
            continue
        for site in _TRANSPORT_RE.finditer(masked):
            line = masked[: site.start()].count("\n") + 1
            word = _transport_word(site.group(0))
            add(
                rel,
                line,
                DenominatorSite(
                    file=rel,
                    line=line,
                    callee=word,
                    kind="raw-transport",
                    by_name=False,
                    binding="",
                ),
            )

    return [rows[key] for key in sorted(rows)]


def return_accounting(root: Path) -> list[ReturnAccount]:
    """Per speakable endpoint: did the fold read every exit, or only the ones it liked?

    ``Payload.always`` is an intersection over ``branches``, and an intersection is a
    proof only over the complete set of exits. Give it one of a handler's three returns
    and it reports that one branch's keys as "this route always sends these" -- a
    positive claim built on a partial read, which is worse than the empty reads this
    campaign keeps hitting, because an empty read prints as nothing while this one prints
    as a guarantee. The cheapest edit a handler can take, an early ``return``, would move
    every ``always`` number in the repo into that shape and nothing used to check it.

    Rows cover the unbounded endpoints too: the fuse and the unbounded roster are the same
    three rows seen from two sides, and a mismatch that is *not* also in the roster is the
    difference between "I did not read that" and "there is nothing there".
    """
    out: list[ReturnAccount] = []
    for pair, _required, _optional, payload in _speakable_endpoints(root):
        endpoint = pair.endpoint
        out.append(
            ReturnAccount(
                verb=endpoint.verb,
                path=normalize_path(endpoint.path),
                module=endpoint.module,
                handler=endpoint.handler,
                own_returns=_own_return_count(root, endpoint),
                branches=len(payload.branches),
                unbounded=tuple(payload.unbounded),
            )
        )
    return out


def normalize_path(path: str) -> str:
    """`/jobs/{job_id}` and `/jobs/${id}` and `/jobs/{}?x=1` all become `/jobs/{}`."""
    stripped = re.sub(r"\?.*$", "", path)
    out = re.sub(r"\{[^{}]*\}", "{}", stripped)
    out = re.sub(r"/+$", "", out)
    return out or "/"


def path_candidates(raw: str) -> tuple[str, ...]:
    """The keys one call site may pair against, most specific first.

    A gap that is not slash-separated (`"/api/v1/admin/users" + q`, where `q` is a
    query string) and a missing segment (`"/jobs/" + id`) read the same once the
    variable is gone -- but only the second leaves a `/` in front of the slot. So every
    bare gap offers a second reading, and `pairings` records which reading matched: the
    rescue is countable instead of silent, and a site that pairs only on the loose
    reading cannot pass for an exact contract.
    """
    out = [normalize_path(raw)]
    for stem in _bare_stems(raw):
        trimmed = normalize_path(stem)
        if trimmed not in out:
            out.append(trimmed)
    return tuple(out)


def _bare_stems(built: str) -> list[str]:
    """The path taken up to each gap that a `/` does not introduce.

    `"/agent/jobs" + (q ? "?" + q : "")` leaves two slots behind, so a reading that only
    trims a *trailing* slot calls it an orphan and the list route it asks for stays in
    the register as "nobody consumes me". A slash-preceded gap is a real segment and
    gets no rescue: reading `"/jobs/" + id` as `/jobs` would invent a contract no caller
    asked for.
    """
    out: list[str] = []
    for match in re.finditer(r"\{\}", built):
        start = match.start()
        if start == 0 or built[start - 1] == "/":
            continue
        out.append(built[:start])
    return out


# --------------------------------------------------------------------------
# E1 -- the endpoint table


def api_routers(root: Path) -> dict[str, str]:
    """`"module.path:router_var" -> prefix`, for every APIRouter the api/ tree declares."""
    out: dict[str, str] = {}
    for py in sorted((root / "api").rglob("*.py")):
        module = ".".join(py.relative_to(root).with_suffix("").parts)
        tree = ast.parse(py.read_text(encoding="utf-8"))
        for node in tree.body:
            if not (
                isinstance(node, ast.Assign)
                and isinstance(node.value, ast.Call)
                and ast.unparse(node.value.func) == "APIRouter"
            ):
                continue
            prefix = ""
            for kw in node.value.keywords:
                if kw.arg == "prefix" and isinstance(kw.value, ast.Constant):
                    prefix = str(kw.value.value)
            for target in node.targets:
                if isinstance(target, ast.Name):
                    out[f"{module}:{target.id}"] = prefix
    return out


def endpoints(root: Path) -> list[Endpoint]:
    routers = api_routers(root)
    out: list[Endpoint] = []
    for key, prefix in sorted(routers.items()):
        module_name, var = key.split(":")
        py = root / (module_name.replace(".", "/") + ".py")
        tree = ast.parse(py.read_text(encoding="utf-8"))
        for node in tree.body:
            if not isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
                continue
            for dec in node.decorator_list:
                if not (
                    isinstance(dec, ast.Call)
                    and isinstance(dec.func, ast.Attribute)
                    and isinstance(dec.func.value, ast.Name)
                    and dec.func.value.id == var
                    and dec.func.attr in HTTP_VERBS
                    and dec.args
                    and isinstance(dec.args[0], ast.Constant)
                    and isinstance(dec.args[0].value, str)
                ):
                    continue
                out.append(
                    Endpoint(
                        module=module_name,
                        router=var,
                        verb=dec.func.attr,
                        path=prefix + dec.args[0].value,
                        handler=node.name,
                        line=node.lineno,
                    )
                )
    return out


# --------------------------------------------------------------------------
# TS declarations (api.ts is not the only host -- see AgentSettings.tsx)


def _split_members(body: str) -> list[Member]:
    """Top-level `name: type;` pairs in an object-type body, brace/bracket aware."""
    out: list[Member] = []
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
            member = _one_member(buf)
            if member is not None:
                out.append(member)
            buf = ""
        else:
            buf += ch
    member = _one_member(buf)
    if member is not None:
        out.append(member)
    return out


def _one_member(chunk: str) -> Member | None:
    chunk = re.sub(r"/\*.*?\*/", "", chunk, flags=re.S)
    chunk = re.sub(r"//[^\n]*", "", chunk).strip()
    m = re.match(r"^(\w+)(\?)?\s*:\s*(.+)$", chunk, re.S)
    if m is None:
        return None
    return Member(m.group(1), bool(m.group(2)), " ".join(m.group(3).split()))


def _block_after(text: str, open_brace_at: int) -> str:
    """Body of the brace block that starts at `open_brace_at` (the char is a `{`)."""
    depth = 0
    i = open_brace_at
    while i < len(text):
        if text[i] == "{":
            depth += 1
        elif text[i] == "}":
            depth -= 1
            if depth == 0:
                return text[open_brace_at + 1 : i]
        i += 1
    return text[open_brace_at + 1 :]


_DECL_PATTERNS = (
    re.compile(r"^(?:export\s+)?interface\s+(\w+)[^{}]*\{", re.M),
    re.compile(r"^(?:export\s+)?type\s+(\w+)\s*=\s*\{", re.M),
)


def _rel_in_web(web_src: Path, ts: Path) -> str:
    """A repo-facing path for a frontend file, so findings read as `apps/web/src/...`.

    Derived from the tail of `web_src` (`apps/web/src`) rather than from a repo root
    argument, because the two frontend readers take only the source tree; an arm copy
    of the repo keeps the same tail, so the label stays true.
    """
    return f"{'/'.join(web_src.parts[-3:])}/{ts.relative_to(web_src).as_posix()}"


def ts_declarations(web_src: Path) -> dict[str, tuple[str, list[Member]]]:
    """Every interface/type-alias object shape in the frontend, with its host file.

    Non-exported declarations are included on purpose: `ModelConfig` lives in a page
    and is invisible to an `export interface` lens (#543 measures that).
    """
    out: dict[str, tuple[str, list[Member]]] = {}
    for ts in sorted(list(web_src.rglob("*.ts")) + list(web_src.rglob("*.tsx"))):
        rel = _rel_in_web(web_src, ts)
        text = _mask_prose(ts.read_text(encoding="utf-8"))
        for pattern in _DECL_PATTERNS:
            for m in pattern.finditer(text):
                members = _split_members(_block_after(text, m.end() - 1))
                if members:
                    out.setdefault(m.group(1), (rel, members))
    return out


def members_of_type(type_expr: str, decls: dict[str, tuple[str, list[Member]]]) -> tuple[
    set[str], set[str], list[str]
]:
    """(required, optional, notes) for a TS type expression used at a call site."""
    expr = " ".join(type_expr.split())
    if expr.startswith("{"):
        members = _split_members(_block_after(expr, 0))
        return _split_required(members), {m.name for m in members if m.optional}, []
    m = re.fullmatch(r"(\w+)(?:\s*\|\s*null)?(?:\s*\[\s*\])?", expr)
    if m is None:
        return set(), set(), [f"type expression not understood: {expr[:48]!r}"]
    name = m.group(1)
    entry = decls.get(name)
    if entry is None:
        return set(), set(), [f"type {name!r} is not declared in apps/web/src"]
    members = entry[1]
    notes = []
    if expr.endswith("[]"):
        notes.append(f"{name} is an array; the envelope is not this type")
    return _split_required(members), {m.name for m in members if m.optional}, notes


def _split_required(members: list[Member]) -> set[str]:
    return {m.name for m in members if not m.optional}


# --------------------------------------------------------------------------
# E2 -- frontend call sites


#: The client verbs only; the type argument is read by `_call_at`, which balances the
#: angle brackets instead of capturing them with a non-greedy regex. Hook consumers are
#: added per tree by `_consumer_re`, because which hooks qualify is read from their
#: bodies (E6) rather than written here.
_CLIENT_RE = re.compile(
    r"\b(" + "|".join(_CLIENT_VERBS) + r")\b\s*"
)


def _first_arg(text: str, after_paren: int) -> str:
    """The first argument, with the whitespace that belongs to the line-break gone.

    A call written across lines -- ``apiPost<X>(\\n  "/api/v1/..." + id\\n)`` -- opens its
    argument with a newline and closes it with one, and `_path_of_argument` reads any
    text before the first literal (or after the last) that is not a `+` or a space as a
    variable slot. Both halves of that indent folded into `{}`: the leading one made the
    path stop starting with `/`, so the site left the census without a sound (12 of the
    45 path-bearing sites on this tree are written that way, which the R1 arm measured);
    the trailing one left `/jobs/{}/summary{}` behind, which pairs only on the loose
    reading -- so the site survived as a *loose* pairing and the register of loose
    pairings started carrying a whitespace artifact nobody asked for. The B6a arm planted
    a call whose closing paren sat on its own line and the loose leg caught the half of
    this rule that `lstrip` alone had left in place.
    """
    depth = 0
    buf = ""
    for ch in text[after_paren:]:
        if ch in "([{":
            depth += 1
        elif ch in ")]}":
            if depth == 0:
                break
            depth -= 1
        elif ch == "," and depth == 0:
            break
        buf += ch
    return buf.strip()


def _depth0_chooser(arg: str) -> bool:
    """True when the argument chooses or compares at depth 0, outside its literals.

    A conditional or a comparison is not concatenation: the literals on its two sides
    belong to different expressions, and gluing them writes an endpoint no caller named.
    `"/api/v1/x?q" === q ? "/api/v1/a" : null` folded to `/api/v1/x?q{}/api/v1/a{}`,
    which is a path-shaped string the page never wrote and which the census would have
    paired against nothing -- it starts with `/`, so the site was kept and E7 was never
    asked. Depth here means brackets, so a ternary inside `( ... )` stays the
    concatenation slot it has always been: the two loose pairings of #544 and the
    contracts page's `&repo_path=` suffix read through that shape, and the R register
    would go red the day this rule reached for them.
    """
    masked = _mask_literals(arg)
    depth = 0
    i = 0
    while i < len(masked):
        ch = masked[i]
        two = masked[i + 1 : i + 2]
        if ch in "([{":
            depth += 1
        elif ch in ")]}":
            depth = max(0, depth - 1)
        elif depth == 0:
            if masked[i : i + 2] in ("??", "==", "!=", "&&", "||"):
                return True
            if ch == "?":
                if two == ".":
                    i += 2
                    continue
                return True
            if ch == ":" and two != ":":
                return True
        i += 1
    return False


def _path_of_argument(arg: str) -> tuple[str, bool]:
    """Concatenation-aware path. Returns (path, is_variable_built).

    Each non-literal gap becomes one `{}` slot, so `"/jobs/" + encodeURIComponent(id)`
    reads as `/jobs/{}` -- the same shape the backend declares as `/jobs/{job_id}`.
    An argument that chooses at depth 0 hands back no path: the fold gives up and E7
    reads the branch, rather than the ruler inventing a third endpoint out of two.
    """
    if _depth0_chooser(arg):
        return "", True
    quoted = re.finditer(r"(['\"`])(.*?)\1", arg, re.S)
    literals = [(m.start(), m.end(), m.group(2)) for m in quoted]
    out = ""
    pos = 0
    variable = False
    for start, end, content in literals:
        if arg[pos:start].strip(" +"):
            variable = True
            out += "{}"
        out += content
        pos = end
    if arg[pos:].strip(" +"):
        variable = True
        out += "{}"
    out = re.sub(r"\$\{[^{}]*\}", "{}", out)
    return out, variable


#: A path built once and handed to the client by name:
#: `const query = "/api/v1/admin/audit?limit=" + n` then `apiGet<AuditResponse>(query)`.
#: The argument carries no literal, so the fold sees a bare slot and the site is lost.
_ALIAS_RE = re.compile(r"\b(?:const|let|var)\s+([A-Za-z_$][\w$]*)\s*=\s*([\"'`][^;\n]*)")
_LITERAL_RE = re.compile(r"(['\"`])(.*?)\1", re.S)


def _splice_aliases(arg: str, aliases: dict[str, str]) -> tuple[str, tuple[str, ...]]:
    """Alias names rewritten into their folded literals, plus the names that were used.

    Substitution happens outside string literals only. Splicing inside one would turn
    `"/jobs/" + path` into a path and `"/api/v1/x/query"` into a quotation containing
    another quotation -- a malformed path invented by the ruler rather than read from
    the tree, which is the failure mode this reading is most exposed to.
    """
    used: list[str] = []
    pieces: list[str] = []
    pos = 0
    for match in _LITERAL_RE.finditer(arg):
        pieces.append(_splice_chunk(arg[pos : match.start()], aliases, used))
        pieces.append(match.group(0))
        pos = match.end()
    pieces.append(_splice_chunk(arg[pos:], aliases, used))
    return "".join(pieces), tuple(dict.fromkeys(used))


def _splice_chunk(chunk: str, aliases: dict[str, str], used: list[str]) -> str:
    out = chunk
    for name, folded in aliases.items():
        replaced = re.sub(rf"\b{re.escape(name)}\b", '"' + folded + '"', out)
        if replaced != out:
            used.append(name)
            out = replaced
    return out


def _file_aliases(text: str) -> tuple[dict[str, str], tuple[str, ...]]:
    """Same-file path aliases in declaration order, and the names this file refused.

    Resolved transitively: `const jobPath = "/jobs/" + id` then `const artifactPath =
    "/api/v1" + jobPath` folds to `/api/v1/jobs/{}`. Folding each declaration once
    instead reads `jobPath` as a bare slot, produces `/api/v1{}`, and the calls built
    from it pair against nothing -- the R2 arm watched the orphan leg catch exactly
    that.

    Only values that fold to a path enter the table, and a name given a string literal
    more than once in one file is refused rather than guessed at: `let path` is the
    kind of name a second assignment elsewhere in the file would silently re-point, and
    a fold that renamed an unrelated argument would be reporting a contract the caller
    never asked for.
    """
    declared: dict[str, int] = {}
    for name, _rhs in _ALIAS_RE.findall(text):
        declared[name] = declared.get(name, 0) + 1
    table: dict[str, str] = {}
    for name, rhs in _ALIAS_RE.findall(text):
        if declared[name] > 1 or name in table:
            continue
        folded, _built = _path_of_argument(_splice_aliases(rhs.strip(), table)[0])
        if folded.startswith("/"):
            table[name] = folded
    return table, tuple(sorted(name for name, count in declared.items() if count > 1))


_LITERAL_SPAN = re.compile(r"(['\"`])(.*?)\1", re.S)


def _mask_literals(arg: str) -> str:
    """`arg` with the inside of every string literal blanked, the same length.

    A ternary's `?` and the `?` that opens a query string are the same character, and an
    argument usually carries both: `"/api/v1/contracts?status=" + status + (repo ? … )`.
    Masking keeps the indices aligned, so the split found on the copy can be applied to
    the original. The B11 arm of #544 measured the cost of the unmasked reading on the
    alias rule; H2 of the #546 rehearsal measured it here, and it was worse -- the naive
    split read the query string as a condition and cost the contracts pairing.

    C3 separates the two guards and finds the mask **inert on today's population**:
    `_fold_argument` only asks for branches once the literal fold has failed, and the one
    argument that reaches it (`Matrix.tsx:22`) has no `?` inside a literal. The damage the
    rehearsal saw belongs to C3b, which also drops that ordering -- two sites lost
    (`Contracts.tsx:17` and `api.ts:991`'s `/agent/jobs` loose pairing), none gained. The
    mask is paid for by the day a folded argument grows a query string of its own.
    """
    out = list(arg)
    for match in _LITERAL_SPAN.finditer(arg):
        for i in range(match.start() + 1, max(match.start() + 1, match.end() - 1)):
            if out[i] != "\n":
                out[i] = " "
    return "".join(out)


def _conditional_branches(arg: str) -> tuple[str, ...]:
    """The two arms of a depth-0 conditional, or ``()`` when the argument is not one.

    Depth 0 only. An argument like ``"/api/v1/x" + (repo ? "&repo_path=" + q : "")`` has
    its ternary inside parentheses, and splitting that would rewrite a sub-expression no
    caller asked the ruler to read -- the same over-reach that E7's roster exists to
    make visible. ``??`` and ``?.`` are not conditionals.
    """
    masked = _mask_literals(arg)
    depth = 0
    mark = -1
    pending = 0
    for i, ch in enumerate(masked):
        if ch in "([{":
            depth += 1
        elif ch in ")]}":
            depth = max(0, depth - 1)
        elif depth == 0:
            if ch == "?":
                if masked[i + 1 : i + 2] in ("?", "."):
                    continue
                if mark < 0:
                    mark = i
                else:
                    pending += 1
            elif ch == ":" and mark >= 0:
                if pending:
                    pending -= 1
                else:
                    return (arg[mark + 1 : i], arg[i + 1 :])
    return ()


def _fold_argument(
    arg: str, aliases: dict[str, str]
) -> tuple[str, tuple[str, ...], tuple[str, ...]]:
    """(path, the conditional branch it was taken from, the branch paths refused).

    The literal-and-alias fold runs first, so an argument that already spells its path is
    never rewritten by E7. Only a fold that does not produce a path is read as a
    conditional. Two path-shaped arms are a refusal rather than a choice: one call site
    cannot be paired against two endpoints, and taking the first would have the ruler
    invent the contract the caller did not commit to.
    """
    path, _built = _path_of_argument(_splice_aliases(arg, aliases)[0])
    if path.startswith("/"):
        return path, (), ()
    hits: list[tuple[str, str]] = []
    for branch in _conditional_branches(arg):
        folded, _b = _path_of_argument(_splice_aliases(branch, aliases)[0])
        if folded.startswith("/"):
            hits.append((branch.strip(), folded))
    if len(hits) == 1:
        return hits[0][1], (hits[0][0],), ()
    return path, (), tuple(folded for _text, folded in hits)


def conditional_table(
    web_src: Path,
) -> tuple[list[tuple[str, int, str, str]], list[tuple[str, int, tuple[str, ...]]]]:
    """What E7 rewrote -- (file, line, folded path, branch text) -- and what it refused.

    The rows come from the census itself, so a register entry that shaped no site is a
    mismatch the gate can see. The refusals need a second look, because a refused
    argument never becomes a site: without this list, "the rule that gave up" and "the
    rule that found nothing to give up on" would read the same.
    """
    calls, _excluded = frontend_calls(web_src)
    rows = [
        (site.file, site.line, site.path, site.via_conditional[0])
        for site in calls
        if site.via_conditional
    ]
    refused: list[tuple[str, int, tuple[str, ...]]] = []
    pattern = _consumer_re(_consumer_names(web_src))
    for ts in _web_sources(web_src):
        if _is_test_file(ts):
            continue
        rel = _rel_in_web(web_src, ts)
        text = _mask_prose(ts.read_text(encoding="utf-8"))
        aliases, _ambiguous = _file_aliases(text)
        for match in pattern.finditer(text):
            if not _is_call(text, match):
                continue
            found = _call_at(text, match.end())
            if found is None:
                continue
            _path, _used, rejected = _fold_argument(_first_arg(text, found[1]), aliases)
            if rejected:
                line = text[: match.start()].count("\n") + 1
                refused.append((rel, line, rejected))
    return rows, refused


#: A hook consumer's definition. `[ \t]` rather than `\s*` after `^` on purpose: `\s*`
#: swallows the blank line above, so the census reported `useAgentJob` one line early --
#: on the blank, measured while writing this rule. A line that points at nothing is a
#: witness a reader cannot check.
_HOOK_DEF = re.compile(r"^[ \t]*(?:export\s+)?function\s+(use[A-Z][\w$]*)\b", re.M)


def _past_paren(text: str, pos: int) -> int:
    """Index just past the first balanced ``(...)`` at or after ``pos``, or -1."""
    start = text.find("(", pos)
    if start == -1:
        return -1
    depth = 0
    for i in range(start, len(text)):
        if text[i] == "(":
            depth += 1
        elif text[i] == ")":
            depth -= 1
            if depth == 0:
                return i + 1
    return -1


def _function_body(text: str, signature_end: int) -> tuple[str, int]:
    """The text between a function's braces, and the index just past the closing one.

    Braces inside string literals are counted, which on this tree cannot be reached: a
    hook body whose brace count is wrong ends up unreadable, and an unreadable body
    yields no verbs, so the gate's hook register -- not a silently wrong verb -- is what
    changes.
    """
    start = text.find("{", signature_end)
    if start == -1:
        return "", -1
    depth = 0
    for i in range(start, len(text)):
        if text[i] == "{":
            depth += 1
        elif text[i] == "}":
            depth -= 1
            if depth == 0:
                return text[start + 1 : i], i + 1
    return "", -1


def _verbs_in(text: str) -> tuple[str, ...]:
    """The client verbs in a piece of source, in the order they are written.

    One spelling on purpose. The blind-spot census has to compare what a construct holds
    with what the reading took, and two ways of counting the verbs in the same text would
    let those two sides disagree for a reason that is the ruler's own -- the #545
    rehearsal measured its `untyped` counter reading 0 against the gate's register of 1.
    """
    return tuple(
        _CLIENT_VERBS[match.group(1)]
        for match in _CLIENT_RE.finditer(text)
        if _is_call(text, match)
    )


def hook_readings(web_src: Path) -> list[HookReading]:
    """Every ``use*`` function on the frontend that issues a client request.

    E6's population, measured rather than named: a hook is a consumer because its body
    contains an ``api*`` call, and its verb is that call's verb. Two hooks qualify on
    this tree -- `useRemoteData` (one `apiGet`, whose path the caller hands in) and
    `useAgentJob` (one `apiGet`, whose path is built inside). A hook that issues two
    requests is still reported, with both verbs, so the gate can refuse it by name
    instead of reading it as one.
    """
    out: list[HookReading] = []
    for ts in _web_sources(web_src):
        if _is_test_file(ts):
            continue
        rel = _rel_in_web(web_src, ts)
        text = _mask_prose(ts.read_text(encoding="utf-8"))
        for match in _HOOK_DEF.finditer(text):
            sig = _past_paren(text, match.end())
            if sig == -1:
                continue
            body, _end = _function_body(text, sig)
            verbs = _verbs_in(body)
            if not verbs:
                continue
            out.append(
                HookReading(
                    match.group(1),
                    rel,
                    text[: match.start()].count("\n") + 1,
                    verbs,
                )
            )
    return out


#: A `use*` declaration in any spelling the reader does not have. `const useX = () =>`
#: and `async function useX` are React's two most common ways to write the thing this
#: file reads with `_HOOK_DEF`, and both are invisible to it. The census measures the
#: gap instead of closing it, because on today's tree the population is zero: all 14
#: frontend `use*` declarations are plain `function`, so an arrow reading would rewrite
#: nothing and would need a register of its own to say so.
_ANY_HOOK_DEF = re.compile(
    r"^[ \t]*(?:export\s+)?(?:default\s+)?(async\s+)?(function|const|let|var)\s+(use[A-Z][\w$]*)\b",
    re.M,
)

#: The line a top-level declaration starts on, so a hook's own region can be bounded
#: without trusting the brace counting below. An unbounded region reads past the end of
#: a short hook into whatever the next declaration requests, and the first rehearsal of
#: this census reported two phantom consumers that way.
_TOP_BOUNDARY = re.compile(
    r"^(?:export\s+)?(?:default\s+)?(?:async\s+)?"
    r"(?:function|const|let|var|class|interface|type|enum)\s",
    re.M,
)


def _region_of(text: str, bounds: list[int], start: int) -> str:
    """One top-level declaration's own text, up to the next declaration's head."""
    later = [b for b in bounds if b > start]
    return text[start : later[0]] if later else text[start:]


def ruler_blind_spots(web_src: Path) -> list[BlindSpot]:
    """Every frontend shape the ruler recognizes and does not read, measured.

    ``seen`` is what the construct holds -- the client verbs inside the declaration's own
    region, or the path-shaped literals inside a conditional arm -- and ``read`` is what
    the census took, which is `()` for a hook spelling `_HOOK_DEF` cannot match and for a
    body that was swallowed by its return annotation. A row whose two tuples differ is a
    consumer or a site the census lost; a row whose two agree is a shape that costs
    nothing today, which is the thing a reader deserves to see rather than re-derive.

    The five shapes and their measured populations on this tree:

    * `arrow-hook` and `async-hook` -- 0 rows. Population 0, and the reading that would
      fill them is what ⓮ turned down for the same reason.
    * `annotation-swallowed-body` -- 3 rows, all with `seen == read == ()`:
      `identity/useIdentityAccess.ts:10`, `pages/Audit.tsx:59`, `pages/Billing.tsx:132`.
      Each declares `: { checked: boolean; ... }`, and `_function_body` takes that
      brace pair as the body, so the hook is not a consumer. None of the three issues a
      request -- each hands off to `useRoleAccess` -- so nothing is lost today, and the
      row is the reason the next reader will not have to find that out by hand.
      The test is the closing index the ruler itself returned: a declaration whose body
      was really read ends where its region ends. The naive test ("a `:` sits between the
      signature and the first brace") measured 8 rows, and the 5 false ones are
      annotations without braces, `hooks/navigate.ts:10`'s `: (path: string) => void`
      among them.
    * `nested-conditional-arm` -- 0 rows. E7 splits a depth-0 conditional once, so an arm
      that is itself a conditional is read as one expression: the fixture
      `jobId ? (inner ? "/api/v1/a" : "/api/v1/b") : "/api/v1/c"` keeps the site
      `/api/v1/c` and reports nothing about the two paths that sat in the other arm. The
      one real ternary on this tree is not nested.
    * `glued-across-depth0-operator` -- 0 rows, and this one is F1's own safety net. A
      depth-0 chooser now yields no path, so an argument whose arms are all variables
      (`kind === "a" ? queryA : queryB`) leaves the census silently; the row says so
      instead of leaving the site missing. Today the only depth-0 chooser on the tree is
      `pages/Matrix.tsx:22`, whose arm is a path, so the fold still lands.
    """
    # `read` is asked of the reading, never written down as the blindness. An exit that
    # hardcoded `()` for the two hook spellings would keep reporting them as blind on the
    # day `_HOOK_DEF` learned to read them, and the register would go stale in the one
    # direction it exists to point at.
    taken = {(r.name, r.file): r.verbs for r in hook_readings(web_src)}
    out: list[BlindSpot] = []
    for ts in _web_sources(web_src):
        if _is_test_file(ts):
            continue
        rel = _rel_in_web(web_src, ts)
        text = _mask_prose(ts.read_text(encoding="utf-8"))
        bounds = [m.start() for m in _TOP_BOUNDARY.finditer(text)]
        for match in _ANY_HOOK_DEF.finditer(text):
            is_async, kind, name = bool(match.group(1)), match.group(2), match.group(3)
            line = text[: match.start()].count("\n") + 1
            region = _region_of(text, bounds, match.start())
            seen = _verbs_in(region)
            got = taken.get((name, rel), ())
            if kind != "function":
                out.append(BlindSpot("arrow-hook", name, rel, line, seen, got))
                continue
            if is_async:
                out.append(BlindSpot("async-hook", name, rel, line, seen, got))
                continue
            signature = _past_paren(text, match.end())
            if signature == -1:
                continue
            body, end = _function_body(text, signature)
            read = _verbs_in(body)
            tail = region[end - match.start() :] if end != -1 else ""
            swallowed = end != -1 and tail.strip().strip(";").strip() != ""
            if swallowed or read != seen:
                out.append(
                    BlindSpot("annotation-swallowed-body", name, rel, line, seen, read)
                )

    pattern = _consumer_re(_consumer_names(web_src))
    for ts in _web_sources(web_src):
        if _is_test_file(ts):
            continue
        rel = _rel_in_web(web_src, ts)
        text = _mask_prose(ts.read_text(encoding="utf-8"))
        aliases, _ambiguous = _file_aliases(text)
        for match in pattern.finditer(text):
            if not _is_call(text, match):
                continue
            found = _call_at(text, match.end())
            if found is None:
                continue
            arg = _first_arg(text, found[1])
            line = text[: match.start()].count("\n") + 1
            spliced = _splice_aliases(arg, aliases)[0]
            path, branch, rejected = _fold_argument(arg, aliases)
            if (
                _depth0_chooser(spliced)
                and not path.startswith("/")
                and not branch
                and not rejected
            ):
                out.append(
                    BlindSpot("glued-across-depth0-operator", match.group(1), rel, line, (), ())
                )
            for arm in _conditional_branches(spliced):
                folded, _built = _path_of_argument(_splice_aliases(arm, aliases)[0])
                if folded.startswith("/"):
                    continue
                held = tuple(
                    literal.group(2)
                    for literal in _LITERAL_SPAN.finditer(arm)
                    if literal.group(2).startswith("/")
                )
                if held:
                    out.append(
                        BlindSpot("nested-conditional-arm", match.group(1), rel, line, held, ())
                    )
    return sorted(out, key=lambda spot: (spot.shape, spot.file, spot.line, spot.name))


def _consumer_names(web_src: Path) -> tuple[str, ...]:
    """Client functions, plus every hook whose body issues exactly one request.

    A hook with two requests is not a consumer: its type argument would be handed to
    whichever call the ruler picked, and an invented pairing is worse than a missing one.
    """
    single = tuple(
        r.name for r in hook_readings(web_src) if len(r.verbs) == 1
    )
    return (*_CLIENT_VERBS, *sorted(set(single)))


def _consumer_re(names: Iterable[str]) -> re.Pattern[str]:
    return re.compile(
        r"\b(" + "|".join(re.escape(name) for name in names) + r")\b\s*"
    )


def _hook_verbs_by_name(web_src: Path) -> dict[str, str]:
    return {r.name: r.verbs[0] for r in hook_readings(web_src) if len(r.verbs) == 1}


def _read_angle(text: str, start: int) -> tuple[str, int] | None:
    """The balanced `<...>` block at `start`, returning (inner text, index just past it).

    A non-greedy regex capture stops at the *first* `>`, which silently truncates a
    nested generic (`apiGet<{ job: { id: string; status: string } }>(...)` read as
    `{ job: { id: string; status: string ` -- a type whose members are then invented
    from a fragment). `=>` is skipped because in a type position it is an arrow, not a
    closer.
    """
    if start >= len(text) or text[start] != "<":
        return None
    depth = 0
    i = start
    while i < len(text):
        ch = text[i]
        if ch == "<":
            depth += 1
        elif ch == ">":
            depth -= 1
            if depth == 0:
                return text[start + 1 : i], i + 1
        elif ch == "=" and text[i : i + 2] == "=>":
            i += 1
        i += 1
    return None


def _promise_annotation(text: str, call_start: int) -> str:
    """The enclosing declaration's `Promise<T>`, when the call itself is untyped.

    `createVerification(...): Promise<{ job_id: string; status: string }>` followed by
    `apiPost("/jobs", payload)` declares a real contract one line up; reading only the
    call's generic argument would drop the app's most-used endpoint from the census.
    Accepted only while no other `function` / arrow sits between the annotation and the
    call, so the type cannot be borrowed from a finished sibling scope -- an untyped
    site whose value is genuinely discarded (a login probe) stays untyped, and the gate
    counts it instead of guessing.
    """
    index = text.rfind("): Promise<", 0, call_start)
    if index == -1:
        return ""
    read = _read_angle(text, index + len("): Promise"))
    if read is None:
        return ""
    between = text[read[1] : call_start]
    if "function " in between or "=>" in between:
        return ""
    return read[0].strip()


def _call_at(text: str, pos: int) -> tuple[str, int] | None:
    """`(type argument, index just past the opening paren)` for a client call at `pos`."""
    type_expr = ""
    if pos < len(text) and text[pos] == "<":
        read = _read_angle(text, pos)
        if read is None:
            return None
        type_expr, pos = read[0].strip(), read[1]
    if pos >= len(text) or text[pos] != "(":
        return None
    return type_expr, pos + 1


def _web_sources(web_src: Path) -> list[Path]:
    return sorted(list(web_src.rglob("*.ts")) + list(web_src.rglob("*.tsx")))


def _is_test_file(ts: Path) -> bool:
    return any(part in _TEST_PATH_PARTS for part in ts.parts) or ts.name.endswith(_TEST_SUFFIXES)


def frontend_calls(web_src: Path) -> tuple[list[CallSite], int]:
    """(pairs candidates, excluded test-file sites).

    The pattern is built per tree: the client functions plus the hooks E6 qualifies. The
    verb of a hook site is the verb read out of that hook's body, so no name in this
    file carries a verb the ruler was told to believe.
    """
    out: list[CallSite] = []
    excluded = 0
    names = _consumer_names(web_src)
    pattern = _consumer_re(names)
    hook_verbs = _hook_verbs_by_name(web_src)
    for ts in _web_sources(web_src):
        rel = _rel_in_web(web_src, ts)
        text = _mask_prose(ts.read_text(encoding="utf-8"))
        aliases, _refused = _file_aliases(text)
        is_test = _is_test_file(ts)
        for match in pattern.finditer(text):
            if not _is_call(text, match):
                continue
            found = _call_at(text, match.end())
            if found is None:
                continue
            type_expr, after_paren = found
            name = match.group(1)
            path, used_alias = _splice_aliases(_first_arg(text, after_paren), aliases)
            folded, branch, rejected = _fold_argument(path, aliases)
            if not folded.startswith("/") or rejected:
                continue
            if is_test:
                excluded += 1
                continue
            typed_by = "generic" if type_expr else "none"
            if not type_expr:
                type_expr = _promise_annotation(text, match.start())
                if type_expr:
                    typed_by = "return-annotation"
            line = text[: match.start()].count("\n") + 1
            out.append(
                CallSite(
                    rel,
                    line,
                    _CLIENT_VERBS.get(name) or hook_verbs[name],
                    folded,
                    type_expr,
                    typed_by,
                    used_alias,
                    branch,
                    name if name in hook_verbs else "",
                )
            )
    return out, excluded


def alias_table(web_src: Path) -> tuple[list[tuple[str, str, str, int]], list[tuple[str, str]]]:
    """What the alias reading consumed: (file, name, folded path, sites) and refusals.

    This is the first rule in the owner that rewrites somebody else's code into a path,
    so the population it feeds has to be countable in both directions: a table entry
    that shapes zero sites shows up here with `0`, and a name the fold refused to trust
    is listed rather than dropped. A narrowing alias rule does not fail; it hands the
    unpaired-endpoint roster a stale list and stays green.
    """
    calls, _excluded = frontend_calls(web_src)
    rows: list[tuple[str, str, str, int]] = []
    refused: list[tuple[str, str]] = []
    for ts in _web_sources(web_src):
        if _is_test_file(ts):
            continue
        rel = _rel_in_web(web_src, ts)
        table, ambiguous = _file_aliases(_mask_prose(ts.read_text(encoding="utf-8")))
        for name in sorted(table):
            sites = sum(1 for site in calls if site.file == rel and name in site.via_aliases)
            rows.append((rel, name, table[name], sites))
        refused.extend((rel, name) for name in ambiguous)
    return rows, refused


#: A declaration keyword that immediately precedes the client name declares *it*; one
#: that merely appears further back does not. Unanchored, `"const data = await
#: apiGet<X>(...)"` reads like a definition. The A12 arm measured the cost of that
#: reading on this tree: eight path-bearing mentions were judged declarations -- five of
#: them product census sites (`const answer = apiGet<{ principal ... }>("/auth/me")`,
#: `const updated = await apiPost<ModelConfig>(...)`, and three more), which is why the
#: census read 23 sites instead of 28, and three inside `__tests__`, which is why the
#: excluded count read 1 instead of 4. A tool that loses population does not fail; it
#: hands the roster leg a stale list and stays green.
_DECL_HEAD = re.compile(r"\b(?:function|const|let|var)$")


def _is_call(text: str, m: re.Match[str]) -> bool:
    """A definition line (`export async function apiGet<T>(...)`) is not a call site."""
    head = text[max(0, m.start() - 40) : m.start()].rstrip()
    return _DECL_HEAD.search(head) is None


def call_shapes(web_src: Path) -> list[CallShape]:
    """Every call-shaped mention of a consumer in a product file, kept or rejected.

    ``frontend_calls`` returns the survivors; this returns the whole population so a
    gate can audit the guard itself instead of trusting it. Test files are left out
    because their mentions are counted as an exclusion, not as consumers. Hook consumers
    are included, which is how a hook's own ``export function`` line becomes a shape the
    definition guard has to answer for.
    """
    out: list[CallShape] = []
    pattern = _consumer_re(_consumer_names(web_src))
    for ts in sorted(list(web_src.rglob("*.ts")) + list(web_src.rglob("*.tsx"))):
        if any(part in _TEST_PATH_PARTS for part in ts.parts):
            continue
        if ts.name.endswith(_TEST_SUFFIXES):
            continue
        rel = _rel_in_web(web_src, ts)
        text = _mask_prose(ts.read_text(encoding="utf-8"))
        for match in pattern.finditer(text):
            if text[match.end() : match.end() + 1] not in ("<", "("):
                continue
            out.append(
                CallShape(
                    file=rel,
                    line=text[: match.start()].count("\n") + 1,
                    name=match.group(1),
                    is_call=_is_call(text, match),
                    window=text[max(0, match.start() - 40) : match.start()].rstrip(),
                )
            )
    return out


# --------------------------------------------------------------------------
# E4 -- the payload fold


def _keys_of_dict(
    node: ast.Dict, resolve: Callable[..., set[str] | None]
) -> set[str] | None:
    """Top-level literal keys of a dict expression, following `**` through `resolve`."""
    out: set[str] = set()
    for key, value in zip(node.keys, node.values, strict=True):
        if key is None:
            got = resolve(value)
            if got is None:
                return None
            out |= got
        elif isinstance(key, ast.Constant) and isinstance(key.value, str):
            out.add(key.value)
        else:
            return None
    return out


def payload_of(root: Path, endpoint: Endpoint) -> Payload:
    """What the endpoint publishes, per return branch, or why the fold stopped."""
    module_path = root / (endpoint.module.replace(".", "/") + ".py")
    tree = ast.parse(module_path.read_text(encoding="utf-8"))
    handler = _find_function(tree, endpoint.handler)
    if handler is None:
        return Payload(unbounded=[f"handler {endpoint.handler} not found"])
    return _payload_of_function(_build_fold(root, module_path, handler, tree), 0)


def _find_function(tree: ast.AST, name: str) -> ast.FunctionDef | ast.AsyncFunctionDef | None:
    for node in ast.walk(tree):
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)) and node.name == name:
            return node
    return None


@dataclass(frozen=True)
class _Fold:
    """One fold target: a function, the module that holds it, and the repo root.

    Threading the root instead of reading a module-level global is deliberate: a gate
    that runs against a copied tree (an arm worktree) must fold against *that* tree,
    and a process-wide `Path.cwd()` hint would make the answer depend on which test
    ran last.

    ``types`` is how a receiver name becomes a class: `{parameter: Type}` from
    annotations plus `{local: Type}` from `name = Type(...)` and `self.attr = Type(...)`.
    Without it `service.list_jobs(...)` is an unresolvable call, the fold stops at the
    route, and every cross-module payload reads as "unbounded" -- a gate that never
    says anything.
    """

    root: Path
    module_path: Path
    fn: ast.FunctionDef | ast.AsyncFunctionDef
    tree: ast.Module
    class_name: str | None
    types: dict[str, str]


def _build_fold(
    root: Path,
    module_path: Path,
    fn: ast.FunctionDef | ast.AsyncFunctionDef,
    tree: ast.Module,
) -> _Fold:
    class_name = _class_of_module(tree, fn)
    types = _receiver_types(fn, tree)
    if class_name is not None:
        # `self._store.search_jobs(...)` is typed in the constructor, not in the
        # method: without the class's own `__init__`, every service-layer hop would
        # read as unresolvable and the fold would stop at the route.
        for key, value in _class_attribute_types(tree, class_name).items():
            types.setdefault(key, value)
    return _Fold(
        root=root,
        module_path=module_path,
        fn=fn,
        tree=tree,
        class_name=class_name,
        types=types,
    )


def _class_attribute_types(tree: ast.Module, class_name: str) -> dict[str, str]:
    """`self.attr = Cls()` / `self.attr: Cls` facts from every constructor of the class."""
    out: dict[str, str] = {}
    for node in ast.walk(tree):
        if not (isinstance(node, ast.ClassDef) and node.name == class_name):
            continue
        for inner in node.body:
            if not isinstance(inner, (ast.FunctionDef, ast.AsyncFunctionDef)):
                continue
            if inner.name != "__init__":
                continue
            for key, value in _receiver_types(inner, tree).items():
                if key.startswith("self."):
                    out.setdefault(key, value)
    return out


def _class_of_module(tree: ast.Module, fn: ast.AST) -> str | None:
    for node in ast.walk(tree):
        if isinstance(node, ast.ClassDef):
            for inner in node.body:
                if inner is fn:
                    return node.name
    return None


def _strip_optional(text: str) -> str:
    """`MySQLStore | None` / `Optional[MySQLStore]` -> `MySQLStore`."""
    text = re.sub(r"Optional\[(.+)\]", r"\1", text)
    parts = [p.strip() for p in text.split("|") if p.strip() and p.strip() != "None"]
    return parts[0] if len(parts) == 1 else ""


def _class_of_expr(expr: ast.expr | None) -> str | None:
    """The class an expression produces, when the expression says so plainly."""
    if expr is None:
        return None
    if isinstance(expr, ast.Call):
        return ast.unparse(expr.func)
    if isinstance(expr, ast.BoolOp):
        for value in expr.values:
            got = _class_of_expr(value)
            if got:
                return got
        return None
    if isinstance(expr, ast.IfExp):
        return _class_of_expr(expr.body) or _class_of_expr(expr.orelse)
    if isinstance(expr, ast.Await):
        return _class_of_expr(expr.value)
    return None


def _receiver_types(
    fn: ast.FunctionDef | ast.AsyncFunctionDef, tree: ast.Module
) -> dict[str, str]:
    types: dict[str, str] = {}
    for arg in list(fn.args.posonlyargs) + list(fn.args.args) + list(fn.args.kwonlyargs):
        if arg.annotation is not None:
            name = _strip_optional(ast.unparse(arg.annotation))
            if name:
                types[arg.arg] = name
    for node in _own_nodes(fn):
        if isinstance(node, ast.Assign):
            for target in node.targets:
                if isinstance(target, ast.Name):
                    got = _class_of_expr(node.value)
                    if got:
                        types[target.id] = got
                elif (
                    isinstance(target, ast.Attribute)
                    and isinstance(target.value, ast.Name)
                    and target.value.id == "self"
                ):
                    got = _class_of_expr(node.value)
                    if got:
                        types[f"self.{target.attr}"] = got
        elif (
            isinstance(node, ast.AnnAssign)
            and isinstance(node.target, ast.Attribute)
            and isinstance(node.target.value, ast.Name)
            and node.target.value.id == "self"
        ):
            name = _strip_optional(ast.unparse(node.annotation))
            if name:
                types[f"self.{node.target.attr}"] = name
    for node in tree.body:
        if isinstance(node, ast.Assign):
            for target in node.targets:
                if isinstance(target, ast.Name):
                    got = _class_of_expr(node.value)
                    if got:
                        types.setdefault(target.id, got)
    return types


def _own_nodes(fn: ast.FunctionDef | ast.AsyncFunctionDef) -> list[ast.AST]:
    """Nodes that belong to `fn` itself, not to a closure defined inside it.

    A closure that builds the payload is a separate branch set: counting its returns
    as this handler's would report keys the handler never returns.
    """
    stack = list(ast.iter_child_nodes(fn))
    out: list[ast.AST] = []
    while stack:
        node = stack.pop()
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef, ast.Lambda)):
            continue
        out.append(node)
        stack.extend(ast.iter_child_nodes(node))
    return out


def _payload_of_function(fold: _Fold, depth: int) -> Payload:
    bindings: dict[str, list[ast.expr]] = {}
    mutations: dict[str, set[str]] = {}
    conditional_by_name: dict[str, set[str]] = {}
    nodes = sorted(
        _own_nodes(fold.fn),
        key=lambda n: (getattr(n, "lineno", 0), getattr(n, "col_offset", 0)),
    )
    body_statements = {id(node) for node in fold.fn.body}
    for node in nodes:
        targets: list[ast.expr] = []
        value: ast.expr | None = None
        if isinstance(node, ast.Assign):
            targets, value = list(node.targets), node.value
        elif (
            isinstance(node, ast.AnnAssign)
            and node.value is not None
            and isinstance(node.target, ast.Name)
        ):
            # `result: dict[str, Any] = {...}` is the service layer's normal way to
            # build a payload; reading only plain Assign made every such handler look
            # unbounded.
            targets, value = [node.target], node.value
        for target in targets:
            if isinstance(target, ast.Name) and value is not None:
                bindings.setdefault(target.id, []).append(value)
            elif (
                isinstance(target, ast.Subscript)
                and isinstance(target.value, ast.Name)
                and isinstance(target.slice, ast.Constant)
                and isinstance(target.slice.value, str)
            ):
                mutations.setdefault(target.value.id, set()).add(target.slice.value)
                if id(node) not in body_statements:
                    conditional_by_name.setdefault(target.value.id, set()).add(target.slice.value)
        if (
            isinstance(node, ast.Call)
            and isinstance(node.func, ast.Attribute)
            and node.func.attr == "update"
            and isinstance(node.func.value, ast.Name)
        ):
            bucket = mutations.setdefault(node.func.value.id, set())
            for keyword in node.keywords:
                if keyword.arg:
                    bucket.add(keyword.arg)
            if id(node) not in body_statements:
                # Reached only inside an `if`/`try`/`except`: the keys are published on
                # some paths, not on every response. See `Payload.conditional`.
                conditional_by_name.setdefault(node.func.value.id, set()).update(
                    keyword.arg for keyword in node.keywords if keyword.arg
                )

    callee_conditional: set[str] = set()

    def resolve(expr: ast.expr, seen: frozenset[str] = frozenset()) -> set[str] | None:
        """Keys of an expression, or None where the fold refuses to guess."""
        if isinstance(expr, ast.Constant) and expr.value is None:
            # `None` publishes no keys; it is a value, not a fold failure. `found:
            # dict | None = None` followed by `found = {...}` is this repo's standard
            # "maybe-absent artifact" shape, and treating the null binding as
            # unbounded would stop the fold at every artifact endpoint.
            return set()
        if isinstance(expr, ast.Dict):
            return _keys_of_dict(expr, resolve)
        if isinstance(expr, ast.Name):
            if expr.id in seen or expr.id not in bindings:
                return None
            out: set[str] = set()
            for bound in bindings[expr.id]:
                got = resolve(bound, seen | {expr.id})
                if got is None:
                    return None
                out |= got
            out |= mutations.get(expr.id, set())
            # A local's conditional keys travel with that local: `document["_console"]
            # = ...` in a handler whose response is `{"job_id": ..., "status": ...}` is
            # not a payload key at all, and a function-wide bag would report it as one.
            callee_conditional.update(conditional_by_name.get(expr.id, set()))
            return out
        if isinstance(expr, ast.BinOp) and isinstance(expr.op, ast.BitOr):
            left, right = resolve(expr.left), resolve(expr.right)
            return None if left is None or right is None else left | right
        if isinstance(expr, ast.Call):
            return _resolve_call(fold, expr, depth, callee_conditional)
        return None

    payload = Payload()
    for node in nodes:
        if not isinstance(node, ast.Return) or node.value is None:
            continue
        if isinstance(node.value, ast.Constant) and node.value.value is None:
            # `return None` is a branch that publishes no keys, not a fold failure: a
            # handler that answers null really does answer nothing, and hiding it
            # inside `unbounded` would let it escape the per-branch rule.
            payload.branches.append(set())
            continue
        keys = resolve(node.value)
        if keys is None:
            payload.unbounded.append(
                f"return {ast.unparse(node.value)[:60]} (line {node.lineno})"
            )
        else:
            payload.branches.append(keys)
    if not payload.branches and not payload.unbounded:
        payload.unbounded.append("handler has no value-returning branch")
    payload.conditional = callee_conditional
    return payload


def _resolve_call(
    fold: _Fold, call: ast.Call, depth: int, callee_conditional: set[str] | None = None
) -> set[str] | None:
    """Follow `helper(...)` into its returns, within `_PAYLOAD_DEPTH` module hops."""
    if depth >= _PAYLOAD_DEPTH:
        return None
    target = _callee(fold, ast.unparse(call.func))
    if target is None:
        return None
    inner_fold = _load_fold(fold.root, target[0], target[1])
    if inner_fold is None:
        return None
    nested = _payload_of_function(inner_fold, depth + 1)
    if nested.branches and not nested.unbounded:
        if callee_conditional is not None:
            # A spread of the helper inherits its "only on some paths" keys: saying
            # `**artifact` always publishes `signed_path` would be a lie the caller
            # cannot see.
            callee_conditional.update(nested.conditional)
        out: set[str] = set()
        for keys in nested.branches:
            out |= keys
        return out
    # A partial answer is not an answer: one branch we cannot fold means the
    # caller's key set is not a fact.
    return None


def _load_fold(root: Path, module_path: Path, name: str) -> _Fold | None:
    """Parse a callee's module and take its function.

    A method and a module-level function can share a name; callers that want a method
    check `_defines_method` first, so this stays the simple "find the def" step.
    """
    tree = _parse(module_path)
    if tree is None:
        return None
    fn = _find_function(tree, name)
    if fn is None:
        return None
    return _build_fold(root, module_path, fn, tree)


def _callee(fold: _Fold, dotted: str) -> tuple[Path, str] | None:
    """Where does `name(...)` / `service.method(...)` / `self.store.method(...)` live?

    Returns (file, function name) or None when the receiver cannot be typed. Naming a
    module here by guesswork would turn the fold's answer into a fiction, so every
    shape either resolves through an import this module actually writes or stops.
    """
    parts = dotted.split(".")
    if len(parts) == 1:
        if _defines(fold.tree, parts[0]):
            return fold.module_path, parts[0]
        # `from providers.config import public_model_config` makes a bare name a
        # cross-module call; refusing it would report the route as unbounded for the
        # wrong reason (the callee's own shape is the real answer).
        for module_path in _imported_candidate_modules(fold):
            if _defines(_parse(module_path), parts[0]):
                return module_path, parts[0]
        return None
    if len(parts) == 2:
        head, leaf = parts
        if head == "self":
            if fold.class_name and _defines_method(fold.tree, fold.class_name, leaf):
                return fold.module_path, leaf
            return None
        receiver = fold.types.get(head)
        if receiver is not None:
            return _locate(fold, receiver, leaf)
        imported = _imported_module(fold, head)
        if imported is not None and _defines(_parse(imported), leaf):
            return imported, leaf
        return None
    if len(parts) == 3 and parts[0] == "self":
        attr = fold.types.get(f"self.{parts[1]}")
        if attr is None:
            return None
        return _locate(fold, attr, parts[2])
    return None


def _locate(fold: _Fold, class_name: str, method: str) -> tuple[Path, str] | None:
    """`VerificationApplicationService` + `list_jobs` -> (file, "list_jobs")."""
    module_path = _class_module(fold, class_name)
    if module_path is None:
        return None
    tree = _parse(module_path)
    if tree is None:
        return None
    if _defines_method(tree, class_name, method):
        return module_path, method
    if _defines(tree, method):
        return module_path, method
    return None


def _class_module(fold: _Fold, class_name: str) -> Path | None:
    """The file that declares `class_name`, following this module's own imports."""
    leaf = class_name.split(".")[-1]
    for module_path in [fold.module_path, *_imported_candidate_modules(fold)]:
        tree = _parse(module_path)
        if tree is None:
            continue
        if any(isinstance(node, ast.ClassDef) and node.name == leaf for node in ast.walk(tree)):
            return module_path
    return None


def _defines(tree: ast.Module | None, name: str) -> bool:
    """A module-level `def name` -- not a method, not a closure."""
    if tree is None:
        return False
    return any(
        isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)) and node.name == name
        for node in tree.body
    )


def _defines_method(tree: ast.Module | None, class_name: str, method: str) -> bool:
    if tree is None:
        return False
    for node in ast.walk(tree):
        if isinstance(node, ast.ClassDef) and node.name == class_name:
            for inner in node.body:
                if (
                    isinstance(inner, (ast.FunctionDef, ast.AsyncFunctionDef))
                    and inner.name == method
                ):
                    return True
    return False


def _parse(module_path: Path) -> ast.Module | None:
    try:
        return ast.parse(module_path.read_text(encoding="utf-8"))
    except (OSError, SyntaxError, UnicodeDecodeError):
        return None


def _imported_candidate_modules(fold: _Fold) -> list[Path]:
    """Every repo module this module imports from, in source order."""
    src = _source(fold.module_path)
    if src is None:
        return []
    out: list[Path] = []
    for match in re.finditer(r"^(?:from|import)\s+([\w.]+)", src, re.M):
        path = _module_path(fold.root, match.group(1))
        if path is not None and path not in out:
            out.append(path)
    for match in re.finditer(r"^from\s+\.([\w.]+)\s+import", src, re.M):
        dotted = match.group(1).replace(".", "/")
        for candidate in (
            fold.module_path.parent / (dotted + ".py"),
            fold.module_path.parent / dotted / "__init__.py",
        ):
            if candidate.exists() and candidate not in out:
                out.append(candidate)
    return out


def _imported_module(fold: _Fold, head: str) -> Path | None:
    """`import a.b as head` / `from a import b` where the head names a module."""
    src = _source(fold.module_path)
    if src is None:
        return None
    for match in re.finditer(r"^(?:from|import)\s+([\w.]+)(?:\s+as\s+(\w+))?", src, re.M):
        dotted, alias = match.group(1), match.group(2)
        if alias == head or dotted.split(".")[-1] == head or dotted == head:
            return _module_path(fold.root, dotted)
    return None


def _module_path(root: Path, dotted: str) -> Path | None:
    """Resolve a dotted import head to a file, inside the derived product plane only.

    The root check is ``tests/_scan_walk.product_roots``, not a list typed here: eight
    hand-copied names are the artifact #541 opened on, and a fold that resolves helpers
    through a private plane would be reporting on a tree of its own making.
    """
    parts = dotted.split(".")
    if parts[0] not in product_roots(root):
        return None
    candidate = root / "/".join(parts)
    if candidate.with_suffix(".py").exists():
        return candidate.with_suffix(".py")
    init = candidate / "__init__.py"
    return init if init.exists() else None


def _source(module_path: Path) -> str | None:
    try:
        return module_path.read_text(encoding="utf-8")
    except (OSError, UnicodeDecodeError):
        return None


def web_src(root: Path) -> Path:
    """The frontend source tree -- one place, so a gate cannot scan half the repo."""
    return root / "apps" / "web" / "src"


def pairings(root: Path) -> tuple[list[Pair], list[CallSite]]:
    """(pairs, call sites that no endpoint answers) -- the verb is part of the identity."""
    table = {ep.key: ep for ep in endpoints(root)}
    calls, _excluded = frontend_calls(web_src(root))
    pairs, orphan = [], []
    for site in calls:
        endpoint = None
        matched = None
        for index, candidate in enumerate(site.candidates):
            endpoint = table.get((site.verb, candidate))
            if endpoint is not None:
                matched = index == 0
                break
        if endpoint is None:
            orphan.append(site)
        else:
            pairs.append(Pair(site, endpoint, bool(matched)))
    return pairs, orphan


__all__ = [
    "CallShape",
    "CallSite",
    "call_shapes",
    "conditional_table",
    "Endpoint",
    "HookReading",
    "hook_readings",
    "Member",
    "Pair",
    "BlindSpot",
    "ConsumerDefence",
    "ConsumerBinding",
    "ClientExport",
    "DenominatorSite",
    "OptionalBand",
    "Payload",
    "ReturnAccount",
    "alias_table",
    "api_routers",
    "endpoints",
    "frontend_calls",
    "members_of_type",
    "normalize_path",
    "pairings",
    "ruler_blind_spots",
    "path_candidates",
    "consumer_defences",
    "consumer_bindings",
    "client_surface",
    "denominator_sites",
    "optional_publish_bands",
    "payload_of",
    "return_accounting",
    "ts_declarations",
    "web_src",
]

"""#284 — what each process does with a refused metrics bind must be readable by the operator.

Three processes hand a port to ``serve_metrics_in_thread`` and they do NOT do the
same thing when the OS refuses the bind:

  agent/worker.py, storage/outbox_relay.py  the refusal is not caught — the
      process stops. Their ports are in ``infra/prometheus/prometheus.yml``, so
      an endpoint nobody can scrape is not something they get to pretend is up.
  storage/invoice_cron.py                   catches ``OSError`` and puts
      ``NOT serving (<the OS's reason>)`` into its own startup line, then keeps
      issuing invoices. Its port is in no roster and its work is idempotent per
      closed month.

#272 and #275 each wrote one half of that sentence into the code and neither
reached the operator: measured over the ops docs, ``NOT serving`` and ``metrics
refresh failed`` were both 0 occurrences (#275's boundary ①, re-measured here by
the census below). And ``docs/operations/DRILLS.md`` asserted the opposite of the
asymmetry — that the cron's仪表 is 「同 outbox relay 形状」.

So this gate reads the CODE's fate for every tracked listener (no hand-written
list of processes: the population comes from ``git ls-files`` plus one AST pass,
the same census shape as #232/#268) and requires the ops documents to agree with
it, per knob.

Case map:
  D1 the listener census is non-empty and really carries both fates
  D2 the carrier roster is an explicit set of ops files, and the ledger
     exclusion hides something (it is a reader list, not a grep artifact)
  D3 every knob's fate, as the code implements it, has a carrier block naming
     that knob and quoting that fate
  D3b a quoted disclosure phrase may only appear in a block that names a
     process the code actually writes it from
  D4 each carrier block also states the port number the code defaults to
  D5 the ownership promise the docs make is bound to the mechanism that makes it
     true (the exclusive-bind override), so reverting the fix reddens the doc gate
  D6 the forbidden-parity clause fires on the 「同 outbox relay 形状」 spelling
  D7 reverse control on synthetic blocks: the classifier is not a substring hunt
     that any mention of the words would satisfy
"""

from __future__ import annotations

import ast
import re
import subprocess
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parent.parent.parent

#: Files an operator is expected to read before operating these processes.
#: Explicit on purpose: #235's gate reded once on a carrier list built from
#: whatever the local disk happened to contain.
CARRIER_FILES = (
    "docs/operations/OBSERVABILITY.md",
    "docs/operations/RUNBOOK.md",
    "docs/architecture/BILLING_DESIGN.md",
)

#: Files that make claims about these processes but are not allowed to satisfy a
#: carrier requirement (a drill log records what was done, it is not a manual).
CLAIM_ONLY_FILES = ("docs/operations/DRILLS.md",)

#: The ledger is excluded from BOTH sets, and D2 proves the exclusion is doing
#: real work rather than hiding a hole: it names these knobs and quotes these
#: spellings more often than any reader doc does.
LEDGER = "docs/operations/DEEP_OPTIMIZATION_PLAN.md"

#: The phrase the ops docs must use for a process that lets the refusal end it.
#: The other fate's phrase is not hand-written here — D3 quotes whatever literal
#: the production handler actually logs, so the code owns its own wording.
STOP_CLAIM = "随绑定失败退出"

#: The spelling that used to be written, and is now forbidden next to a knob:
#: the two shapes are not the same, and the code says which.
FORBIDDEN_PARITY = "同 outbox relay 形状"

_METRICS_CALL = "serve_metrics_in_thread"
_KNOB_SUFFIX = "_METRICS_PORT"
#: ``storage/env_config.py`` readers (#471) — the same env read behind a helper.
_KNOB_HELPERS = ("int_env", "float_env")


def _git_tracked_py() -> list[str]:
    out = subprocess.run(
        ["git", "ls-files", "*.py"],
        cwd=ROOT,
        capture_output=True,
        check=True,
        timeout=180,
    ).stdout.decode("utf-8")
    files = [line for line in out.splitlines() if line]
    assert len(files) > 50, f"tracked-file census collapsed: {len(files)} files"
    return files


def _module_ints(tree: ast.Module) -> dict[str, int]:
    out: dict[str, int] = {}
    for node in tree.body:
        if not isinstance(node, ast.Assign) or len(node.targets) != 1:
            continue
        target = node.targets[0]
        if (
            isinstance(target, ast.Name)
            and isinstance(node.value, ast.Constant)
            and isinstance(node.value.value, int)
        ):
            out[target.id] = node.value.value
    return out


def _getenv_knob(read: ast.Call, consts: dict[str, int]) -> tuple[str, int] | None:
    """A listen-port knob read from the environment, with the default it declares.

    Two spellings carry that relation. ``os.getenv(NAME, DEFAULT)`` is the inline
    read; ``int_env(NAME, DEFAULT)`` / ``float_env(NAME, DEFAULT)`` is the same read
    through ``storage/env_config.py``, which treats a blank value as unset (#471).
    The census charges both, because a scan that only knows the first loses a
    listener the moment its site is converted — and the file keeps calling
    ``serve_metrics_in_thread``, so nothing else in this gate would notice.
    """
    func = read.func
    helper = isinstance(func, ast.Name) and func.id in _KNOB_HELPERS
    if not helper and (getattr(func, "attr", "") != "getenv" or len(read.args) != 2):
        return None
    if helper and len(read.args) != 2:
        return None
    name = read.args[0]
    if not (isinstance(name, ast.Constant) and isinstance(name.value, str)):
        return None
    if not name.value.endswith(_KNOB_SUFFIX):
        return None
    default = read.args[1]
    if helper and isinstance(default, ast.Constant) and isinstance(default.value, int):
        return name.value, default.value
    if helper and isinstance(default, ast.Name):
        resolved = consts.get(default.id)
        assert resolved is not None, (
            f"{name.value} defaults to {default.id} and that is not a module-level "
            "int — the port the process binds has no readable number"
        )
        return name.value, resolved
    if isinstance(default, ast.Constant) and isinstance(default.value, str):
        return name.value, int(default.value)
    if (
        isinstance(default, ast.Call)
        and isinstance(default.func, ast.Name)
        and default.func.id == "str"
        and len(default.args) == 1
        and isinstance(default.args[0], ast.Name)
    ):
        resolved = consts.get(default.args[0].id)
        assert resolved is not None, (
            f"{name.value} defaults to str({default.args[0].id}) and that is not a "
            "module-level int — the port the process binds has no readable number"
        )
        return name.value, resolved
    raise AssertionError(
        f"{name.value}: unexpected getenv default shape "
        f"{ast.dump(default)[:120]}"
    )


def _catches_refusal(node: ast.Try) -> bool:
    """Does this ``try`` swallow the bind refusal?"""
    for handler in node.handlers:
        guard = handler.type
        if isinstance(guard, ast.Name) and guard.id in {
            "OSError",
            "Exception",
            "BaseException",
        }:
            return True
        if isinstance(guard, ast.Tuple) and any(
            isinstance(item, ast.Name)
            and item.id in {"OSError", "Exception", "BaseException"}
            for item in guard.elts
        ):
            return True
    return False


def _inside(try_node: ast.Try, call: ast.Call) -> bool:
    body_lines = {
        line
        for stmt in try_node.body
        for line in range(stmt.lineno, (stmt.end_lineno or stmt.lineno) + 1)
    }
    return call.lineno in body_lines


def _disclosure_literal(try_node: ast.Try) -> str:
    """The stable spelling the refusal branch puts in the log, quoted from code.

    Read from the ``except`` bodies only: a ``NOT serving`` that lives in the
    guarded call region would be some other string, and the sentence the
    operator greps for is the one the refusal branch writes.
    """
    texts = [
        node.value
        for handler in try_node.handlers
        for node in ast.walk(handler)
        if isinstance(node, ast.Constant) and isinstance(node.value, str)
    ]
    if any("NOT serving" in t for t in texts):
        return "NOT serving"
    raise AssertionError(
        "the refusal branch builds a disclosure sentence this gate cannot quote; "
        "the operator-facing wording is what the docs must repeat, so change the "
        "docs in the same edit and teach this probe the new spelling"
    )


def listener_fates() -> dict[str, dict[str, Any]]:
    """knob -> {file, default port, fate, disclosure phrase if it swallows}."""
    out: dict[str, dict[str, Any]] = {}
    definers: list[str] = []
    for rel in _git_tracked_py():
        if rel.startswith("tests/"):
            continue
        path = ROOT / rel
        if not path.is_file():
            continue
        raw = path.read_bytes()
        if _METRICS_CALL.encode() not in raw:
            continue
        tree = ast.parse(raw.decode("utf-8").replace("\r\n", "\n"))
        consts = _module_ints(tree)
        tries = [node for node in ast.walk(tree) if isinstance(node, ast.Try)]
        defines = sum(
            isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef))
            and node.name == _METRICS_CALL
            for node in ast.walk(tree)
        )
        calls = [
            node
            for node in ast.walk(tree)
            if isinstance(node, ast.Call)
            and (
                getattr(node.func, "attr", "") == _METRICS_CALL
                or getattr(node.func, "id", "") == _METRICS_CALL
            )
        ]
        if defines:
            # The definition site is not a listener: a ``def`` is not a call.
            # #232's L2 census charges the same distinction, and its failure
            # mode is this exact crash — the file that hands out the endpoint
            # appearing as a fourth process with no port knob of its own.
            definers.append(rel)
            assert not calls, (
                f"{rel} both defines and calls {_METRICS_CALL}: the census cannot "
                "tell who owns the endpoint from who uses it"
            )
            continue
        assert calls, f"{rel} mentions {_METRICS_CALL} but never calls it"
        knobs = sorted(
            {
                knob
                for node in ast.walk(tree)
                if isinstance(node, ast.Call)
                and (knob := _getenv_knob(node, consts)) is not None
            }
        )
        assert len(knobs) == 1, (
            f"{rel} starts a metrics server and declares {knobs}: one listener "
            "needs exactly one listen-port knob for this census to charge it"
        )
        name, default = knobs[0]
        # A call inside a ``try`` is only swallowed if some handler actually
        # takes the OS's refusal — containment alone would make an unrelated
        # ``except ValueError`` look like a disclosure policy.
        guarded = [
            t for t in tries if _catches_refusal(t) and any(_inside(t, call) for call in calls)
        ]
        fate = "discloses" if guarded else "stops"
        entry = {"file": rel, "default": default, "fate": fate}
        if guarded:
            entry["phrase"] = _disclosure_literal(guarded[0])
        assert name not in out, (
            f"{name} is bound by both {out.get(name, {}).get('file')} and {rel}: two "
            "processes on one knob is the port-stealing bug, not a knob"
        )
        out[name] = entry
    assert out, f"no tracked file outside tests/ calls {_METRICS_CALL}"
    assert len(definers) == 1, (
        f"exactly one module may define {_METRICS_CALL}, got {definers} — with two, "
        "which one enforces port ownership is a question the docs cannot answer"
    )
    return out


def _blocks(rel: str) -> list[str]:
    """The doc cut into the units a reader actually sees.

    Splitting on blank lines alone would merge this repo's runbook: its bullets
    are not blank-separated, so the whole list would be one block and any one
    sentence in it would vouch for every knob. A new bullet, table row or heading
    starts a unit; an indented continuation line belongs to the one it wraps.
    """
    path = ROOT / rel
    assert path.is_file(), f"{rel} moved; this gate would silently stop reading it"
    text = path.read_text(encoding="utf-8").replace("\r\n", "\n")
    blocks: list[str] = []
    current: list[str] = []
    for line in text.splitlines():
        if not line.strip():
            if current:
                blocks.append("\n".join(current))
                current = []
            continue
        if re.match(r"^[-*|#]", line):
            if current:
                blocks.append("\n".join(current))
            current = [line]
        else:
            current.append(line)
    if current:
        blocks.append("\n".join(current))
    return blocks


def _blocks_named(knob: str, files: tuple[str, ...]) -> list[tuple[str, str]]:
    """(file, block) for every block of those docs that names the knob."""
    return [(rel, block) for rel in files for block in _blocks(rel) if knob in block]


def _lines_named(rel: str, needle: str) -> list[tuple[int, str]]:
    """Physical lines containing ``needle`` — a table row is one line, a wrapped
    bullet is several, and only the line can point a reader at the sentence."""
    path = ROOT / rel
    assert path.is_file(), f"{rel} moved; this gate would silently stop reading it"
    text = path.read_text(encoding="utf-8").replace("\r\n", "\n")
    return [(n, line) for n, line in enumerate(text.splitlines(), 1) if needle in line]


def _carrier_blocks(knob: str) -> list[tuple[str, str]]:
    """Only the reader roster can carry a disclosure; a drill log cannot."""
    return _blocks_named(knob, CARRIER_FILES)


# ───────────────────────────────────────────── D1 ─────────────────────────────────────────────
def test_the_listener_census_carries_both_fates() -> None:
    """The asymmetry is a property of the code, not of this file's prose.

    D3 can only mean something if the population has more than one fate in it:
    a census that found three identical fates would be satisfied by one doc
    sentence repeated three times.
    """
    fates = listener_fates()
    by_fate: dict[str, list[str]] = {}
    for knob, info in fates.items():
        by_fate.setdefault(str(info["fate"]), []).append(knob)
    assert len(by_fate) > 1, (
        f"every listener handles a refused bind the same way ({by_fate}): the docs "
        "then describe one policy, and this gate's per-knob requirement is theatre"
    )
    for fate, knobs in sorted(by_fate.items()):
        assert knobs, f"{fate} bucket is empty"
    assert {"stops", "discloses"} == set(by_fate), (
        f"the classifier produced {sorted(by_fate)}; the fates this gate quotes are "
        "stops (the refusal ends the process) and discloses (it is swallowed and "
        "logged) — a third word means the classifier changed"
    )


# ───────────────────────────────────────────── D2 ─────────────────────────────────────────────
def test_the_carrier_roster_is_explicit_and_its_exclusion_hides_something() -> None:
    """Who is allowed to satisfy a carrier requirement, and why the ledger is not.

    #275 measured that a doc census over ``docs/**`` is fed by every ledger
    section that writes 「这句没文档」 — the accounting file quoting a sentence
    inflates its own carrier count. So the roster is declared, and the exclusion
    is charged rather than trusted.
    """
    for rel in (*CARRIER_FILES, *CLAIM_ONLY_FILES):
        assert (ROOT / rel).is_file(), f"{rel} is in the roster but not on disk"
    assert LEDGER not in CARRIER_FILES and LEDGER not in CLAIM_ONLY_FILES, (
        "the ledger is in the reader roster: a section that records a missing doc "
        "sentence would then become the sentence's carrier"
    )
    fates = listener_fates()
    phrases = sorted(
        {str(info["phrase"]) for info in fates.values() if info["fate"] == "discloses"}
    )
    ledger = (ROOT / LEDGER).read_text(encoding="utf-8")
    named = [knob for knob in fates if knob in ledger]
    quoted = [p for p in phrases if p in ledger] + [STOP_CLAIM] * (STOP_CLAIM in ledger)
    assert named and quoted, (
        f"the ledger exclusion is a slot for nothing: it names {named} of the "
        f"knobs and quotes {quoted} of the disclosure phrases. Delete the "
        "exclusion instead of pretending it protects a hole."
    )
    carriers = {knob: len(_carrier_blocks(knob)) for knob in fates}
    assert all(v >= 1 for v in carriers.values()), (
        f"a knob with zero reader-doc carriers: "
        f"{sorted(k for k, v in carriers.items() if v == 0)}"
    )


# ───────────────────────────────────────────── D3 ─────────────────────────────────────────────
def test_each_knob_carrier_block_states_the_fate_the_code_actually_implements() -> None:
    """The doc sentence and the ``run_forever`` branch must carry the same verdict.

    Quoted phrases come from the code: ``NOT serving`` is read off the cron's own
    handler, and only a process the classifier sees as unguarded has to say
    「随绑定失败退出」.
    """
    fates = listener_fates()
    for knob, info in sorted(fates.items()):
        want = STOP_CLAIM if info["fate"] == "stops" else str(info["phrase"])
        rows = _carrier_blocks(knob)
        assert rows, f"{knob} is named by no reader-doc block at all"
        agreed = [rel for rel, block in rows if want in block]
        assert agreed, (
            f"{info['file']} handles a refused {knob} bind by "
            f"{info['fate']} — the doc has to say {want!r} in the block that names "
            f"the knob; carriers found: {[rel for rel, _ in rows]}"
        )


# ─────────────────────────────────────────── D3b ───────────────────────────────────────────
def test_a_disclosure_phrase_is_only_quoted_next_to_a_process_that_writes_it() -> None:
    """The other half of the same charge, keyed on the phrase instead of the knob.

    「worker 绑定被拒时会记 NOT serving」 is a lie an operator can only discover
    by grepping for a line that is never written. Checking per knob would catch
    it (WORKER's own block), but only as long as the false sentence stays inside
    that block; this clause fires wherever the phrase appears while naming none
    of the processes that emit it.
    """
    fates = listener_fates()
    owners: dict[str, list[str]] = {}
    for knob, info in fates.items():
        want = STOP_CLAIM if info["fate"] == "stops" else str(info["phrase"])
        owners.setdefault(want, []).append(knob)
    assert len(owners) > 1, f"one phrase for every fate ({owners}): nothing to distinguish"
    offenders: list[str] = []
    for rel in (*CARRIER_FILES, *CLAIM_ONLY_FILES):
        for block in _blocks(rel):
            for phrase, knobs in owners.items():
                if phrase in block and not any(knob in block for knob in knobs):
                    offenders.append(f"{rel}: 段落引用 {phrase!r} 而不名 {knobs} 中任何一个")
    assert not offenders, (
        "a doc quotes a disclosure sentence next to a process that never writes it: "
        + "; ".join(offenders)
    )


# ───────────────────────────────────────────── D4 ─────────────────────────────────────────────
def test_each_carrier_block_states_the_port_the_code_defaults_to() -> None:
    """A fate sentence about a port nobody can locate is half a disclosure.

    The number is the code's own literal (resolved through ``str(CONST)`` when
    that is the shipped shape), so a doc that keeps saying 9103 while the module
    moved reds here.
    """
    fates = listener_fates()
    for knob, info in sorted(fates.items()):
        port = str(info["default"])
        want = STOP_CLAIM if info["fate"] == "stops" else str(info["phrase"])
        rows = [(rel, block) for rel, block in _carrier_blocks(knob) if want in block]
        assert rows, f"{knob} has no fate-carrying block to attach its port to"
        # Every fate sentence must locate its own port: a doc that copies the
        # verdict but drops the number leaves the reader to guess which of the
        # three scrape ports the sentence is about.
        missing = [rel for rel, block in rows if port not in block]
        assert not missing, (
            f"{knob}: {info['file']} binds port {port} by default and these "
            f"blocks state the fate without that number: {missing}"
        )


# ───────────────────────────────────────────── D5 ─────────────────────────────────────────────
def test_the_ownership_promise_in_the_docs_is_bound_to_the_mechanism() -> None:
    """「只有一个属主」 is only true while the endpoint asks for the exclusive option.

    #284's fix is a ``server_bind`` override. Reverting it puts Windows back to
    "second process binds, scrape reads the first owner", and the doc sentence
    would then be a confident lie — the worst kind of stale artefact. So the doc
    has to name the module that enforces it, and that module has to still carry
    the mechanism.
    """
    source = (ROOT / "observability" / "metrics_http.py").read_text(encoding="utf-8")
    tree = ast.parse(source)
    override = next(
        (
            node
            for node in ast.walk(tree)
            if isinstance(node, ast.FunctionDef) and node.name == "server_bind"
        ),
        None,
    )
    assert override is not None, (
        "observability/metrics_http.py no longer overrides server_bind; the docs "
        "still promise one owner per metrics port"
    )
    body = ast.unparse(override)
    assert "SO_EXCLUSIVEADDRUSE" in body and "allow_reuse_address" in body, (
        f"server_bind lost the mechanism the docs promise ({body[:160]})"
    )
    promised = [
        rel
        for rel in CARRIER_FILES
        if any(
            "observability/metrics_http.py" in block and "属主" in block
            for block in _blocks(rel)
        )
    ]
    assert promised, (
        "no reader doc ties the single-owner promise to the module that enforces "
        "it, so an operator reading a port collision has nothing to grep"
    )


# ───────────────────────────────────────────── D6 ─────────────────────────────────────────────
def test_no_doc_claims_the_two_bind_policies_have_one_shape() -> None:
    """The 「同 outbox relay 形状」 spelling, charged as a defect.

    Written before the fix existed, it was true of the port number and the
    daemon-thread shape and false of the one thing an operator needs when the
    bind is refused. It is forbidden on any LINE that also names a listen-port
    knob — line-scoped on purpose: a markdown block here can span a whole table
    row plus the bullets around it, and a gate that charges at block size sends
    the reader to a sentence that is not the one at fault.

    The second half is the anti-paraphrase belt: a row that retracts a shape
    claim has to quote the code's own verdict, so deleting the bad spelling and
    writing 「形状不同」 in its place does not pass.
    """
    fates = listener_fates()
    hits = [
        f"{rel}:{n}"
        for rel in (*CARRIER_FILES, *CLAIM_ONLY_FILES)
        for n, line in _lines_named(rel, FORBIDDEN_PARITY)
        if any(knob in line for knob in fates)
    ]
    assert not hits, (
        "a doc claims the cron's metrics endpoint is the same shape as the "
        "relay's; the relay stops on a refused bind and the cron logs NOT serving "
        f"and keeps running: {hits}"
    )
    for rel in CLAIM_ONLY_FILES:
        for n, line in _lines_named(rel, "订正"):
            named = [knob for knob in fates if knob in line]
            if not named:
                continue
            for knob in named:
                info = fates[knob]
                want = STOP_CLAIM if info["fate"] == "stops" else str(info["phrase"])
                assert want in line, (
                    f"{rel}:{n} retracts a claim about {knob} but never states what "
                    f"the code does ({want!r}, read off {info['file']}); a correction "
                    "without the true sentence leaves the reader with two claims"
                )


# ───────────────────────────────────────────── D7 ─────────────────────────────────────────────
def test_the_classifier_is_selective_not_a_substring_hunt() -> None:
    """Reverse control on synthetic blocks.

    Without this, a doc that merely contains the words somewhere — a table of
    contents, a quoted log line — would satisfy every leg above.
    """
    cron_knob = "INVOICE_CRON_METRICS_PORT"
    good = f"{cron_knob} (9103): 端口不在名册上，启动日志记 \"NOT serving (原因)\" 并继续开票。"
    bad_shape = "另见 INVOICE_CRON_METRICS_PORT 一节，指标端点与 relay 同形状。"
    unrelated = "WORKER_METRICS_PORT 与 OUTBOX_RELAY_METRICS_PORT 都在名册上。"

    def matches(block: str, phrase: str) -> bool:
        return cron_knob in block and phrase in block

    assert matches(good, "NOT serving"), "the admissible shape must be admissible"
    assert not matches(bad_shape, "NOT serving"), (
        "a block that names the knob but hedges about the shape must not count"
    )
    assert cron_knob not in unrelated, (
        "the classifier keyed on a knob the block never names — it is grepping "
        "the whole file, not a block"
    )

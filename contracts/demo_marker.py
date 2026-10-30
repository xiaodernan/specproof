"""The one owner of the marker that separates seeded demo data from real work.

``summary.retrieval_note`` is the only field the database is asked about when it
decides whether a verification job is sample data. ``storage/mysql.py`` answers
with a computed column::

    CASE WHEN JSON_VALID(summary) THEN COALESCE(LOCATE(prefix, JSON_UNQUOTE(
        JSON_EXTRACT(summary, '$.retrieval_note'))) = 1, 0) ELSE 0 END AS is_demo

and ``apps/web`` renders ``is_demo`` as the 演示 badge, next to a sentence that
promises "标有“演示”的记录为示例数据" (``Dashboard.tsx``). So the marker's *text*
is a wire contract between a seeding script and a SQL predicate, and before #525
it was written down three times in two files with nothing tying them together:
the seeder's literal, and one copy inside each of the two SELECT lists.

The failure that coupling invites is asymmetric, and that asymmetry is the whole
reason for an owner instead of a comment. A rename on the read side does not
crash anything — it makes every seeded row answer ``is_demo = 0``, and three
fabricated verifications with downloadable certificates and a BLOCKED verdict
start rendering as ordinary, unlabeled real work. The fake comes out looking
like the thing it was invented to imitate.

#525 collapses the copies: the prefix lives here once, reaches MySQL as a bound
parameter of the statement that tests it (so the marker appears nowhere in
executed SQL text), and the seeded note is built from it by
``seeded_demo_note`` — which is what keeps the prefix at position 1, the only
position ``LOCATE(...) = 1`` accepts.

#542 moves the *predicate* here as well, one plane further out. #526's roster
ended at "which reads ship a job row", and it wrote the reason down: an aggregate
"has no row to label; adding the column there would mean paying for a predicate
whose result nobody can read". That line is drawn along the wrong axis — the page
also renders bare numbers (``COUNT(*) AS n`` folded into 累计验收 / 验收通过 /
发现风险 and the hourly ``COUNT(*)``/``SUM(failed)`` folded into 交付动态), and a
number that has already summed the seeded rows in cannot be labelled afterwards.
So the same answer now leaves the database in three shapes, all spelled from the
one flag below: ``IS_DEMO_COLUMN`` labels a row, ``IS_DEMO_COUNT`` and
``IS_DEMO_FAILED`` count rows inside a ``GROUP BY``. The read that still does not
ask is ``search_jobs``' ``COUNT(*) AS total`` — and for a reason that is not the
old one: that number is the population of the page it returns, and the seeded
rows on that page each carry their own badge, so excluding them there would make
the count disagree with the rows beside it.

Keeping these as exported fragments is what makes the question askable. A read
that forgot to re-type the expression was invisible — it returns a job the UI
cannot label, or a count that has already summed the sample rows in, and neither
is an error anywhere; as one owner with three spellings, "which reads answer it,
and in which shape" becomes a question a gate can put to a call graph.

The ``COALESCE`` is #526's, not decoration. ``JSON_EXTRACT`` answers SQL ``NULL``
for a summary that is valid JSON without a ``retrieval_note`` key, ``LOCATE(x,
NULL)`` is ``NULL``, and ``NULL = 1`` is ``NULL`` — so the bare predicate could
put ``NULL`` in a column the type calls ``boolean | number``. Neither writer
produces that shape today (both always set the note), so this is latent; the
column is a promise to the page, and ``ELSE 0`` already says the same thing for
the invalid-JSON branch. A computed column that can answer three values under a
two-value type is the kind of gap that gets closed by measurement, not by luck.

Not folded in, deliberately, because they are different questions that happen to
share an answer shape, and one rename must not move all of them:
``api/agent_runtime.py`` decides ``is_demo = not repo_path.strip()`` for the
agent console — a different table (``agent_jobs``) that never reaches this
predicate — and its seeded counterpart is gated on the decoration token
(``test_seed_demo.py`` asserts ``DEMO_MARK in SEED_AGENT_TASK_NAME``), while
``agent/nodes/generate_counterexamples.py``'s ``_is_demo_repo`` asks whether a
workspace is the bundled Spring fixture (gated by
``test_llm_counterexample_path_actually_runs.py``). The SQL predicate and the
note that feeds it are the pair with nothing on either side, which is what this
module closes.
"""

from __future__ import annotations

#: The prefix a seeded summary's ``retrieval_note`` must start with. This is the
#: whole vocabulary of the demo marker; adding a second spelling here would put
#: the drift back where #525 found it.
DEMO_NOTE_PREFIX = "seeded demo"

#: The demo predicate, without an alias: one ``%s``, bound to ``DEMO_NOTE_PREFIX``.
#:
#: It is a *fragment*, not a statement, because it has to sit inside a SELECT list
#: that each read owns for other reasons — the list, the ``WHERE`` tenant
#: predicate, the ``ORDER BY`` and the window all differ between the reads that
#: use it. Only the ``%s`` is shared: the caller binds ``DEMO_NOTE_PREFIX`` and
#: must put that argument *before* every other argument, because the SELECT list
#: is textually earlier than the WHERE clause it also parameterises (#525 pins
#: that ordering for the two window reads; #526's and #542's gates derive the
#: population, so a read cannot be quietly forgotten).
#:
#: The three shapes below are the only spellings, so that a rename moves the
#: badge and the statistic together. An alias typed once and re-typed N times is
#: how two spellings of a key drift apart, and the key — not the expression — is
#: what ``apps/web/src/api.ts`` and the fold in ``api/routes/web.py`` read.
IS_DEMO_FLAG = (
    "CASE WHEN JSON_VALID(summary) THEN "
    "COALESCE(LOCATE(%s, JSON_UNQUOTE("
    "JSON_EXTRACT(summary, '$.retrieval_note'))) = 1, 0) "
    "ELSE 0 END"
)

#: The three shapes are `+`-chains of literals and names, not f-strings, because
#: `tests/unit/test_sql_text_static.py` only folds an imported fragment it can
#: prove is built from string literals. An f-string here reads as a computed
#: value, and every read that imports these would become a finding it has to
#: register — the shape of the owner, not its text, decides that.
IS_DEMO_COLUMN = IS_DEMO_FLAG + " AS is_demo"

#: How many of the rows a ``GROUP BY`` just counted are seeded (#542). The
#: dashboard's visible numbers are read out of an aggregate, so they need the
#: answer as a count — and the fold that subtracts it must be able to tell "no
#: seeded rows" from "this read never asked", which is why this is a column and
#: not a default.
IS_DEMO_COUNT = "SUM(" + IS_DEMO_FLAG + ") AS demo_jobs"

#: The same split for the failure half of the hourly line: ``COUNT`` and
#: ``SUM(failed)`` are rendered beside each other, so an un-split failure count
#: would put a seeded BLOCKED row into a rate next to a clean total.
IS_DEMO_FAILED = (
    "SUM(" + IS_DEMO_FLAG + " AND status IN ('FAILED', 'ERROR')) AS demo_failed"
)


def seeded_demo_note(detail: str) -> str:
    """The ``retrieval_note`` value for seeded rows, marker at position 1.

    ``LOCATE(prefix, note) = 1`` only holds when the note *begins* with the
    prefix, so the join order here is the contract — ``detail`` can say anything
    but cannot move the marker off the front.
    """
    return f"{DEMO_NOTE_PREFIX} {detail}"

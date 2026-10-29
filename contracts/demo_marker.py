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

#526 moves the *column* here too, and that is a different exposure. #525 left
one expression text written inline twice, in the two statements that happened to
publish it; the predicate's answer, though, is asked by four reads (the list
window, the dashboard's recent-jobs window, and both single-row detail reads),
and a fifth that must keep *not* asking it (the COUNT, whose rows are numbers).
Keeping the text in ``storage/mysql.py`` meant every read had to remember to
re-type it, and the ones that forgot were invisible: a read that omits the column
is a read that returns a job the UI cannot label, which is not an error anywhere.
As an exported fragment, "which reads publish the fact" becomes a question a gate
can ask of a call graph instead of a question about a string.

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

#: The computed column that answers the demo question, as one SQL fragment.
#:
#: It is a *fragment*, not a statement, because it has to sit at the end of a
#: SELECT list that each read owns for other reasons — the list, the ``WHERE``
#: tenant predicate, the ``ORDER BY`` and the window all differ between the four
#: reads that use it. Only the ``%s`` is shared: the caller binds
#: ``DEMO_NOTE_PREFIX`` and must put that argument *before* every other argument,
#: because the SELECT list is textually earlier than the WHERE clause it also
#: parameterises (#525 pins that ordering for the two window reads; #526's gate
#: derives the population, so a fifth read cannot be quietly forgotten).
#:
#: ``AS is_demo`` is part of the fragment for the same reason. An alias typed
#: once and re-typed four times is how the two spellings of a key drift apart,
#: and the key — not the expression — is what ``apps/web/src/api.ts`` requires.
IS_DEMO_COLUMN = (
    "CASE WHEN JSON_VALID(summary) THEN "
    "COALESCE(LOCATE(%s, JSON_UNQUOTE("
    "JSON_EXTRACT(summary, '$.retrieval_note'))) = 1, 0) "
    "ELSE 0 END AS is_demo"
)


def seeded_demo_note(detail: str) -> str:
    """The ``retrieval_note`` value for seeded rows, marker at position 1.

    ``LOCATE(prefix, note) = 1`` only holds when the note *begins* with the
    prefix, so the join order here is the contract — ``detail`` can say anything
    but cannot move the marker off the front.
    """
    return f"{DEMO_NOTE_PREFIX} {detail}"

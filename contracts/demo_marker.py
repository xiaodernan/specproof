"""The one owner of the marker that separates seeded demo data from real work.

``summary.retrieval_note`` is the only field the database is asked about when it
decides whether a verification job is sample data. ``storage/mysql.py`` answers
with a computed column::

    CASE WHEN JSON_VALID(summary) THEN LOCATE(prefix, JSON_UNQUOTE(
        JSON_EXTRACT(summary, '$.retrieval_note'))) = 1 ELSE 0 END AS is_demo

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


def seeded_demo_note(detail: str) -> str:
    """The ``retrieval_note`` value for seeded rows, marker at position 1.

    ``LOCATE(prefix, note) = 1`` only holds when the note *begins* with the
    prefix, so the join order here is the contract — ``detail`` can say anything
    but cannot move the marker off the front.
    """
    return f"{DEMO_NOTE_PREFIX} {detail}"

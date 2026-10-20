"""#202 — the jobs list must report the server's TOTAL, never the window size.

The backend already says why, in a comment on the return of `list_jobs`:

    The old fork answered a bare GET /jobs from a SELECT with no COUNT, so that
    response had no `total` and any consumer asking "how many verifications
    exist" could only report the size of the window it happened to fetch.

The route was fixed; the PAGE kept the very fallback that comment describes.
`pages/Jobs.tsx` declared its own `interface JobsPage { jobs: Job[]; total?: number }`
— `total` OPTIONAL — and then did

    setTotal(data.total ?? data.jobs?.length ?? 0);

so any response that omitted `total` would have printed the page size (25) as
"符合筛选的验证", and paginated from it. Latent, not live (the route always sends
`total`), but it is the same shape as the `?status=` ghost filters: a fallback
that turns "I cannot tell you" into a confident wrong number.

The fix removes the possibility, not just the instance: one exported `JobsPage`
in `api.ts` with `total` REQUIRED, and the private weakened copy deleted. This
file pins both ends plus the authority in between.
"""
from __future__ import annotations

import re
from pathlib import Path

REPO = Path(__file__).resolve().parents[2]
MYSQL = REPO / "storage" / "mysql.py"
ROUTE = REPO / "api" / "routes" / "jobs.py"
SERVICE = REPO / "api" / "services" / "verification_service.py"
API = REPO / "apps" / "web" / "src" / "api.ts"
PAGE = REPO / "apps" / "web" / "src" / "pages" / "Jobs.tsx"

_JOBS_PAGE_RE = re.compile(r"export interface JobsPage\s*\{(.*?)\n\}", re.S)


def _source(path: Path) -> str:
    return path.read_text(encoding="utf-8")


def test_the_store_computes_the_total_with_a_count() -> None:
    """The authority: `search_jobs` counts the filtered set itself.

    Scoped to the function body on purpose. The first version asserted the
    string `COUNT(*) AS total` anywhere in the file, and the mutation arm that
    changed search_jobs's own COUNT to `COUNT(id)` SURVIVED — because a second
    query elsewhere in storage/mysql.py carries the same text, so the file-level
    probe stayed satisfied while the number this page shows stopped being a
    count of the set. A witness has to be bound to the thing it witnesses.
    """
    text = _source(MYSQL)
    match = re.search(r"def search_jobs\b.*?\n(?=    def |\Z)", text, re.S)
    assert match, "search_jobs moved — probe broken"
    body = match.group(0)
    assert "COUNT(*) AS total" in body, (
        "search_jobs no longer counts the whole filtered set — the page's number "
        "would be whatever that query happened to return"
    )
    assert '"total": total' in body or "'total': total" in body, (
        "search_jobs computes total but does not return it under that key"
    )


def test_the_route_returns_the_stores_answer_verbatim() -> None:
    """`list_jobs` must hand back the store's dict, not build its own response.

    The store call moved to the application service (Phase 1 put the route
    on it), so the witness is now the service — the property is the same:
    nothing between the store and the page may build its own response, or a
    field the store adds/drops stops reaching the page.
    """
    text = _source(SERVICE)
    match = re.search(r"def list_jobs\b.*?\n(?=    def |\Z)", text, re.S)
    assert match, "the service's list_jobs moved — probe broken"
    body = match.group(0)
    assert "return self._store.search_jobs(" in body, (
        "the service builds its own response; a field added or dropped by the "
        "store would no longer reach the page"
    )


def test_the_shared_type_requires_the_total() -> None:
    """`total` is REQUIRED — the type is what stops a caller inventing a number."""
    match = _JOBS_PAGE_RE.search(_source(API))
    assert match, "api.ts no longer exports JobsPage — probe broken"
    body = match.group(1)
    assert re.search(r"^\s*total:\s*number;", body, re.M), (
        "JobsPage.total must be a required number; optional is what let the page "
        "fall back to the window length"
    )
    assert not re.search(r"^\s*total\?:", body, re.M), (
        "JobsPage.total is optional again — the fallback this gate exists for"
    )


def test_the_page_keeps_no_private_weakened_copy() -> None:
    """One declaration. A second, weaker copy in the page is the whole defect."""
    text = _source(PAGE)
    assert not re.search(r"interface\s+JobsPage", text), (
        "pages/Jobs.tsx declares its own JobsPage again — a private copy can be "
        "weaker than the shared one and nothing would notice"
    )
    assert "type JobsPage" in text, "the page no longer imports the shared type"


def test_the_page_does_not_fall_back_to_the_window_length() -> None:
    """The call site itself: no `?? length` substitution for the total."""
    text = _source(PAGE)
    assert "setTotal(" in text, "the total call site moved — probe broken"
    offenders = [
        line.strip()
        for line in text.splitlines()
        if "setTotal(" in line and "length" in line
    ]
    assert not offenders, (
        "the page substitutes the window length for the server's total: "
        f"{offenders}"
    )
    assert re.search(r"setTotal\(\s*data\.total\s*\)", text), (
        "setTotal no longer takes the server's total directly"
    )

"""Docs coverage gate — the onboarding guides must not advertise fictional pages.

The user guide (`docs/operations/USER_GUIDE.md`, Chinese, plus the English
mirror `docs/operations/EN/USER_GUIDE_EN.md`) tells a newcomer exactly which
routes exist. Before this test existed, the guide listed `/mcp`,
`/admin/identity` and `/readme` — none of which the web app ever mounted.
A new user following the guide would click into a 404. This test re-derives
the truth from `apps/web/src/App.tsx` and fails the build on drift, in both
locales, so the manual cannot silently rot again.
"""

import re
from pathlib import Path

import pytest

REPO = Path(__file__).resolve().parents[2]
APP = REPO / "apps" / "web" / "src" / "App.tsx"
GUIDE_ZH = REPO / "docs" / "operations" / "USER_GUIDE.md"
GUIDE_EN = REPO / "docs" / "operations" / "EN" / "USER_GUIDE_EN.md"

# Routes mounted outside the NAV constant: special-cased in Workspace.
EXTRA_ROUTES = {"guide", "ui-kit", "login"}


def nav_paths() -> list[str]:
    src = APP.read_text(encoding="utf-8")
    start = src.index("const NAV")
    end = src.index("];", start)
    return re.findall(r'\{\s*path:\s*"([a-z-]+)"', src[start:end])


def guide_route_cells(text: str) -> set[str]:
    return set(re.findall(r'\|\s*`(/[A-Za-z0-9_:/-]+)`', text))


@pytest.fixture(scope="module")
def app_routes() -> list[str]:
    paths = nav_paths()
    assert len(paths) >= 18, f"NAV parse collapsed: {paths}"
    assert "jobs" in paths and "settings" in paths
    return paths


@pytest.mark.parametrize("guide", [GUIDE_ZH, GUIDE_EN], ids=["zh", "en"])
def test_every_real_route_is_listed(guide: Path, app_routes: list[str]) -> None:
    text = guide.read_text(encoding="utf-8")
    for path in app_routes + sorted(EXTRA_ROUTES):
        assert f"`/{path}`" in text, f"{guide.name} is missing the real route /{path}"
    assert "`/jobs/new`" in text
    assert "`/jobs/:id`" in text


@pytest.mark.parametrize("guide", [GUIDE_ZH, GUIDE_EN], ids=["zh", "en"])
def test_known_dead_routes_are_not_advertised(guide: Path) -> None:
    text = guide.read_text(encoding="utf-8")
    for dead in ("`/mcp`", "`/readme`", "`/admin/identity`"):
        assert dead not in text, f"{guide.name} still advertises dead route {dead}"


def test_guide_catalogues_are_symmetric(app_routes: list[str]) -> None:
    zh = guide_route_cells(GUIDE_ZH.read_text(encoding="utf-8"))
    en = guide_route_cells(GUIDE_EN.read_text(encoding="utf-8"))
    assert zh == en, f"zh/en guide catalogues diverged: zh-only={zh - en}, en-only={en - zh}"
    for path in app_routes:
        assert f"/{path}" in zh


def test_findings_deep_link_documented() -> None:
    for guide in (GUIDE_ZH, GUIDE_EN):
        assert "#/findings/" in guide.read_text(encoding="utf-8"), guide.name

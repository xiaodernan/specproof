"""Gate: the model credential has ONE reader, and a failed read is not "absent".

WHAT WAS MEASURED (before this unit).  Twenty-three tracked, non-test Python
files name an LLM credential knob (``LLM_BASE_URL`` / ``LLM_API_KEY`` /
``LLM_MODEL`` / ``LLM_PROTOCOL`` / ``LLM_REASONING_EFFORT`` /
``SPECPROOF_MODEL_CONFIG``); twelve of them read one.  ``providers/config.py``
is the owner: it reads the settings file the UI writes
(``.local/llm.json``, relocatable with ``SPECPROOF_MODEL_CONFIG``) and
**lets the environment override it**.  ``agent/nodes/_llm_provider.py`` and
the product go through it.  ``scripts/provider_smoke.py`` did not — it was the
one module in the shipped tree that read a credential off disk *ahead of* the
environment:

    ENV_PATHS = [PROJECT/".env", Path("D:/experim/specproof-phase0/.env"),
                 Path("D:/experim/.env"), PROJECT.parent/"specproof-phase0"/".env",
                 Path(os.getcwd())/".env"]
    for p in ENV_PATHS: _env.update(_load_dotenv(p))          # later beats earlier
    API_KEY = _env.get("LLM_API_KEY", os.environ.get("LLM_API_KEY", ""))   # file beats env

Two inversions of the documented rule, in one file.  ``docs/architecture/
COMPLETION_MAP.md:95`` says the credentials are injected **only** through the
environment and never land on disk; ``save_model_config`` refuses to write the
settings file while any knob is exported, because "the deployment owns it".  A
key the operator exported lost to whichever of those five paths existed last —
including two hardcoded development-machine paths and one derived from
``os.getcwd()`` — and a key configured through the settings UI never reached
this run at all, which is the #503 defect (a key that reaches one consumer and
silently not another) reopened at a third reader.

The repair routes stage 0 through ``load_model_config()`` and records, in the
report itself, which source answered.  Measured on this machine after the
repair — five scenarios, none of which reaches the network:

  nothing configured   -> source='unconfigured', model='' (no phantom model)
  unreadable settings   -> source='unreadable', reason carries the ValueError text
  settings file, no env -> source='local_file'  (the #503 case, now delivered)
  stray .env in cwd     -> source='unconfigured' (the old file-over-env read is gone)
  env + file both set    -> source='environment', env-model wins

WHAT THIS GATE DOES NOT SAY.  It does not say anything reaches the provider.
The refusal paths are what can be run offline, and they are the paths this
defect lived on.  ``evidence/verdict_channels.py:303`` still counts this
script's ``verdict`` as a ``script_report`` channel, not a job verdict.
"""
from __future__ import annotations

import json
import os
import re
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
SCRIPT = ROOT / "scripts" / "provider_smoke.py"
OWNER = "providers/config.py"

KNOBS = ("LLM_BASE_URL", "LLM_API_KEY", "LLM_MODEL", "LLM_PROTOCOL",
         "LLM_REASONING_EFFORT", "SPECPROOF_MODEL_CONFIG",
         "LLM_EMBEDDING_BASE_URL", "LLM_EMBEDDING_API_KEY", "LLM_EMBEDDING_MODEL")

# Ruler a: a knob taken from a dict that falls back to the environment — i.e.
# the file answers first and the environment is the fallback.  This is the
# exact shape of the defect; it is why `_env.get(k, os.environ.get(k))` is a
# precedence statement, not a style choice.
_OVER_ENV_FALLBACK = re.compile(
    r"\w+\.get\(\s*[\"'](?:LLM_[A-Z_]+|SPECPROOF_MODEL_CONFIG)[\"']\s*,\s*os\.environ")
# Ruler b: a private walk over dotenv files.  Deliberately NOT ``load_dotenv(``
# — python-dotenv's own loader fills only what the environment left silent, so
# it is a different relation and is registered below, not banned here.
_DOTENV_WALK = re.compile(r"\bENV_PATHS\b|\b_load_dotenv\b")
# Ruler c: reads through the environment, which the documented rule endorses.
_ENV_READ = re.compile(
    r"(?:os\.getenv|os\.environ\.get|os\.environ\[)\(?\s*[\"']"
    r"(?:LLM_[A-Z_]+|SPECPROOF_MODEL_CONFIG)[\"']"
    r"|envvar=[\"'](?:LLM_[A-Z_]+|SPECPROOF_MODEL_CONFIG)[\"']"
    r"|\"(?:LLM_[A-Z_]+|SPECPROOF_MODEL_CONFIG)\":\s*os\.environ\.get"
    r"|(?:LLM_BASE_URL|LLM_API_KEY|LLM_MODEL)\b\s*\]\s*and\s*os\.environ")
_LIB_DOTENV = re.compile(r"(?<!_)\bload_dotenv\b")
_OWNER_CALL = re.compile(r"from providers\.config import|providers\.config\.|"
                         r"\bload_model_config\b|_ENV_FIELDS")

#: Files that read a credential from disk **ahead of the environment**, with
#: the reason they may.  The population is measured every run; an unregistered
#: member is red and a stale row is red, so the register can neither grow
#: silently nor rot.
OVER_ENV_READERS: dict[str, str] = {}

#: Files that load a dotenv **into the environment** (the environment still
#: wins, so this is a different relation from the one banned above).  Measured
#: empty: two scripts under ``scripts/`` do call ``load_dotenv`` —
#: ``test_c6_junit_diff.py`` and ``test_llm_contract.py`` — and neither names a
#: credential knob, so neither joins this population.  The class stays declared
#: so a future member lands here rather than being mis-sorted into the banned
#: one, which is how the first version of this census read green with the
#: defect still open.
LIB_DOTENV_READERS: dict[str, str] = {}


# ---------------------------------------------------------------------------
# the census, measured from the index
# ---------------------------------------------------------------------------


def _tracked_py() -> list[str]:
    raw = subprocess.run(["git", "ls-files", "-z", "--", "*.py"], cwd=ROOT,
                         capture_output=True).stdout
    return [p.decode("utf-8", "surrogateescape") for p in raw.split(b"\0") if p]


def _is_included(rel: str) -> bool:
    return not (rel.startswith("tests/") or "/tests/" in rel
                or rel.startswith("bench/tasks/"))


def _classify(rel: str) -> str:
    text = (ROOT / rel).read_text(encoding="utf-8", errors="surrogateescape")
    if _OVER_ENV_FALLBACK.search(text) or _DOTENV_WALK.search(text):
        return "over_env"
    if _LIB_DOTENV.search(text):
        return "lib_dotenv"
    if rel == OWNER:
        return "owner"
    if _OWNER_CALL.search(text):
        return "through_owner"
    if _ENV_READ.search(text):
        return "env_only"
    if re.search(r"[\"'](?:LLM_[A-Z_]+|SPECPROOF_MODEL_CONFIG)[\"']"
                 r"|(?:LLM_[A-Z_]+|SPECPROOF_MODEL_CONFIG)\s*=", text):
        return "names_a_knob"
    return "prose"


def _population() -> dict[str, str]:
    return {rel: _classify(rel) for rel in _tracked_py()
            if _is_included(rel) and any(k in (ROOT / rel).read_text(
                encoding="utf-8", errors="surrogateescape") for k in KNOBS)}


# ---------------------------------------------------------------------------
# running the script's offline paths
# ---------------------------------------------------------------------------

_CLEARED = ("LLM_API_KEY", "LLM_BASE_URL", "LLM_MODEL", "LLM_PROTOCOL",
            "LLM_REASONING_EFFORT", "LLM_EMBEDDING_BASE_URL",
            "LLM_EMBEDDING_API_KEY", "LLM_EMBEDDING_MODEL", "SPECPROOF_MODEL_CONFIG")


def _run_script(tmp_path: Path, *, config: Path | None = None,
                env: dict[str, str] | None = None, dotenv: str | None = None) -> dict:
    """Run stage 0 + the refusal path, with this machine's real config fenced out.

    Every call pins ``SPECPROOF_MODEL_CONFIG`` (to a path or to a file that does
    not exist), so a developer's ``.local/llm.json`` cannot leak into a reading.
    """
    tmp_path.mkdir(parents=True, exist_ok=True)
    child = {k: v for k, v in os.environ.items() if k not in _CLEARED}
    child["PYTHONIOENCODING"] = "utf-8"
    child["PYTHONPATH"] = str(ROOT)
    child["SPECPROOF_MODEL_CONFIG"] = str(config if config is not None
                                          else tmp_path / "no-such-config.json")
    child.update(env or {})
    if dotenv is not None:
        (tmp_path / ".env").write_text(dotenv, encoding="utf-8")
    proc = subprocess.run([sys.executable, "-X", "utf8", str(SCRIPT)],
                          cwd=tmp_path, env=child, capture_output=True,
                          text=True, encoding="utf-8", errors="replace", timeout=240)
    out = proc.stdout
    payload, brace = {}, out.find("{")
    if brace >= 0:
        payload = json.loads(out[brace:])
    assert payload, f"the script printed no report:\n{out[-500:]}{proc.stderr[-500:]}"
    assert "config_source" in payload, (
        "the report does not say where the credential came from, so the run "
        f"cannot be audited (keys: {sorted(payload)})")
    return {"exit": proc.returncode, "report": payload, "stdout": out,
            "stderr": proc.stderr}


# ---------------------------------------------------------------------------
# P1 — the census is not collapsed
# ---------------------------------------------------------------------------


def test_the_census_finds_the_population_it_claims_to_cover() -> None:
    classes = _population()
    assert len(classes) >= 20, (
        f"only {len(classes)} tracked non-test files name a credential knob — a "
        "scan that reads nothing reports 'no problem'"
    )
    readers = {r: c for r, c in classes.items() if c != "prose"}
    assert len(readers) >= 8, (
        f"only {len(readers)} files were classified as touching a knob; the "
        "rulers are narrower than the population they claim to sort"
    )
    # The owner must be the owner, and the repaired script must answer through it.
    assert classes[OWNER] == "owner", classes[OWNER]
    assert classes["scripts/provider_smoke.py"] == "through_owner", (
        "the smoke script is no longer going through providers.config")


# ---------------------------------------------------------------------------
# P2 — the disk-over-environment population equals the register, both ways
# ---------------------------------------------------------------------------


def test_reading_a_credential_ahead_of_the_environment_is_registered_or_red() -> None:
    measured = {r for r, c in _population().items() if c == "over_env"}
    unregistered = measured - set(OVER_ENV_READERS)
    stale = set(OVER_ENV_READERS) - measured
    assert not unregistered, (
        f"{sorted(unregistered)} read a credential from disk ahead of the "
        "environment; route it through providers.config or register the reason"
    )
    assert not stale, (
        f"{sorted(stale)} no longer read that way — the register row is a hole "
        "with a name on it now, so delete it"
    )
    for rel, reason in OVER_ENV_READERS.items():
        assert re.search(r"\d|never|because|precedence", reason), (
            f"{rel}: an exemption without a measured reason is not an exemption")
    lib = {r for r, c in _population().items() if c == "lib_dotenv"}
    assert lib == set(LIB_DOTENV_READERS), (
        f"measured {sorted(lib)} but registered {sorted(LIB_DOTENV_READERS)}: the "
        "two disk relations must stay distinguishable, both ways")


# ---------------------------------------------------------------------------
# P3 — the script asks the owner, in the source, for every knob
# ---------------------------------------------------------------------------


def test_the_script_has_no_private_credential_path_left() -> None:
    text = SCRIPT.read_text(encoding="utf-8", errors="surrogateescape")
    assert "load_model_config" in text, "stage 0 no longer asks the owner"
    for banned in ("ENV_PATHS", "_load_dotenv", "D:/experim", "specproof-phase0"):
        assert banned not in text, f"{banned} came back into stage 0"
    assert not _OVER_ENV_FALLBACK.search(text), (
        "a file-over-environment fallback came back")
    # Every knob name still in the file is prose (the refusal message says what
    # it asked for).  None of them may be a read: only the owner maps a knob
    # name to a value.
    assert not _ENV_READ.search(text), (
        "the script reads a knob itself again — that is a second precedence "
        "rule, and it will not agree with the owner's")


# ---------------------------------------------------------------------------
# P4 — nothing configured: honest refusal, no phantom model
# ---------------------------------------------------------------------------


def test_an_unconfigured_run_names_the_source_and_prints_no_chosen_model(
    tmp_path: Path,
) -> None:
    ran = _run_script(tmp_path)
    report = ran["report"]
    assert ran["exit"] == 1 and report["verdict"] == "FAIL"
    assert report["config_source"] == "unconfigured", report["config_source"]
    assert report["model"] == "", (
        "the owner defaults the model name for an unconfigured stack; printing "
        "it here would claim a model this run never chose")
    detail = report["stages"]["1-env"]["detail"]
    assert "unconfigured" in detail and "providers.config" in detail, detail


# ---------------------------------------------------------------------------
# P5 — a read that failed is not answered as "nothing is configured"
# ---------------------------------------------------------------------------


def test_an_unreadable_config_says_the_read_failed(tmp_path: Path) -> None:
    broken = tmp_path / "broken.json"
    broken.write_text("{not json", encoding="utf-8")
    ran = _run_script(tmp_path, config=broken)
    report = ran["report"]
    assert report["config_source"] == "unreadable", report["config_source"]
    assert report["config_error"], "the failure was swallowed"
    detail = report["stages"]["1-env"]["detail"]
    assert "could not be read" in detail, detail
    assert "not configured" not in detail, (
        f"a failed read answered as an absent one: {detail}")


# ---------------------------------------------------------------------------
# P6 — precedence, in all three directions that can be run offline
# ---------------------------------------------------------------------------


def test_precedence_file_reaches_env_wins_stray_dotenv_does_not(tmp_path: Path) -> None:
    # (a) the #503 case, delivered: a key in the settings file reaches this run.
    settings = tmp_path / "llm.json"
    settings.write_text(json.dumps({"base_url": "https://file.example/v1",
                                    "api_key": "", "model": "file-model"}),
                        encoding="utf-8")
    by_file = _run_script(tmp_path / "a", config=settings)
    assert by_file["report"]["config_source"] == "local_file", by_file["report"]
    assert by_file["report"]["model"] == "file-model"

    # (b) the documented rule: the environment overrides the file, field by field.
    by_env = _run_script(tmp_path / "b", config=settings,
                         env={"LLM_BASE_URL": "https://env.example/v1",
                              "LLM_MODEL": "env-model"})
    assert by_env["report"]["config_source"] == "environment"
    assert by_env["report"]["model"] == "env-model", (
        "the file's model won over the one the operator exported")

    # (c) the old bug's exact shape: a .env in the working directory used to be
    #     a credential source found by walking sideways from the repo.
    inert = _run_script(tmp_path / "c", config=None,
                        dotenv="LLM_API_KEY=sk-from-dotenv-file\n"
                               "LLM_BASE_URL=https://x.example/v1\n")
    assert inert["report"]["config_source"] == "unconfigured", inert["report"]
    assert "sk-from-dotenv-file" not in json.dumps(inert["report"]), (
        "a key from a stray .env still reached the run")


# ---------------------------------------------------------------------------
# P7 — who calls this script is measured, and the gap stays on the books
# ---------------------------------------------------------------------------

#: Workflow files that invoke the script, measured every run.  As of #1549
#: (6b2c1b8), exactly one does: `provider-smoke` in `.github/workflows/ci.yml`.
#: It is a `workflow_dispatch`-only job on purpose — the credentials live in
#: a GitHub *environment*, never in the tree, and the three interpolations it
#: carries are the only ones in that file. The bindings (environment declared,
#: the dispatch gate matching `on:`, no secret interpolated into a run:
#: command) are pinned by
#: tests/unit/test_the_provider_smoke_ci_leg_carries_the_branch_job.py, so a
#: red here means the census changed or the job was removed, not that the
#: bindings rotted.
REGISTERED_CALLERS = 1


def test_the_absence_of_a_caller_is_a_measurement_not_an_assumption() -> None:
    callers = sorted(p.as_posix() for p in (ROOT / ".github" / "workflows").glob("*.yml")
                     if "provider_smoke" in p.read_text(encoding="utf-8",
                                                         errors="surrogateescape"))
    assert len(callers) == REGISTERED_CALLERS, (
        f"{callers} now invoke the script — either the run is finally wired into "
        "CI (raise the number and re-measure it) or the census changed"
    )

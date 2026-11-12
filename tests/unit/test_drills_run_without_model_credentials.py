"""The drills start their worker exactly like production does (#1631).

WHY. A drill that "cleans up" the model configuration is not exercising
the same path an operator exercises: the crash-recovery path a drill is
proving has to resume a job that was RUNNING on a real worker, with the
configuration that worker actually had. Emptying the environment does not
also empty the configuration FILE (``providers/config.py``:
``SPECPROOF_MODEL_CONFIG``, default ``.local/llm.json``), so a drill that
thinks it is credential-free is really just a drill running on the
project's configuration anyway -- and the half-clean that looked tidy was
also hiding the fact that the deterministic route short-circuits long
before the stages a crash-recovery drill needs to interrupt.

So the promise is the OPPOSITE one, and it is executable: under the
environment a drill hands its worker, the model configuration resolves
the way it resolves for a real worker -- nothing injected, nothing
rewritten, nothing cleared on the way through. An operator who wants a
credential-free deterministic run can still get one, by removing the file
or pointing SPECPROOF_MODEL_CONFIG elsewhere -- the drill takes the
deterministic route in that case, honestly and visibly.
"""

from __future__ import annotations

import importlib.util
import os
from pathlib import Path
from types import ModuleType

ROOT = Path(__file__).resolve().parents[2]
SCRIPTS = ROOT / "scripts"

#: The drills that start a worker process.
DRILL_SCRIPTS = (
    "drill_outbox_crash.py",
    "drill_worker_kill.py",
)

#: The environment keys the drills must not invent or rewrite. Everything
#: else in os.environ passes through untouched, as it must for production.
DRILL_INVENTED_KEYS = (
    "LLM_API_KEY",
    "LLM_BASE_URL",
    "LLM_MODEL",
    "LLM_REASONING_EFFORT",
    "SPECPROOF_MODEL_CONFIG",
)


def _load(name: str) -> ModuleType:
    path = SCRIPTS / name
    spec = importlib.util.spec_from_file_location(f"_drill_{path.stem}", path)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def _worker_env_under(name: str, env: dict[str, str]) -> dict[str, str]:
    """Compute _worker_env() under a CONTROLLED os.environ."""
    saved = {key: os.environ.get(key) for key in DRILL_INVENTED_KEYS}
    for key in DRILL_INVENTED_KEYS:
        os.environ.pop(key, None)
    os.environ.update(env)
    try:
        module = _load(name)
        return module._worker_env()  # noqa: SLF001 - the seam under test
    finally:
        for key in DRILL_INVENTED_KEYS:
            os.environ.pop(key, None)
        for key, value in saved.items():
            if value is not None:
                os.environ[key] = value


def test_the_drill_injects_no_model_credentials_or_config_path() -> None:
    """Nothing the drill did not inherit may enter the worker's env."""
    for name in DRILL_SCRIPTS:
        env = _worker_env_under(name, {})
        for key in DRILL_INVENTED_KEYS:
            assert key not in env, (
                f"{name} invents {key} for its worker -- the drill stopped "
                "being the same path production runs, and its result stops "
                "being about the thing it claims to measure"
            )


def test_the_drill_passes_the_operators_own_credentials_through() -> None:
    """If the OPERATOR configured a model, the drill's worker uses it.

    The drill is not a sandbox: it runs the product. Credentials the
    operator set are the operator's business, and the drill must not
    silently un-configure what the operator configured -- that was the
    bug this test replaced.
    """
    for name in DRILL_SCRIPTS:
        env = _worker_env_under(
            name,
            {
                "LLM_MODEL": "passthrough-sentinel-model",
                "SPECPROOF_MODEL_CONFIG": "passthrough-sentinel-path",
            },
        )
        assert env.get("LLM_MODEL") == "passthrough-sentinel-model", (
            f"{name} dropped the operator's LLM_MODEL on the floor"
        )
        assert env.get("SPECPROOF_MODEL_CONFIG") == "passthrough-sentinel-path", (
            f"{name} rewrote the operator's SPECPROOF_MODEL_CONFIG"
        )


def test_the_measurement_is_not_vacuous() -> None:
    """The drill scripts are really there and really have the seam."""
    for name in DRILL_SCRIPTS:
        assert (SCRIPTS / name).is_file(), f"{name} is missing"
        module = _load(name)
        assert callable(getattr(module, "_worker_env", None)), (
            f"{name} has no _worker_env() -- the drill does not start a worker "
            "the way this gate expects"
        )

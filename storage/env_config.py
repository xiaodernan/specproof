"""Numeric environment knobs read the way an operator's file is actually written.

A compose file that interpolates a variable nobody set hands the process ``K=``:
a declared knob whose value is empty. ``int(os.getenv("K", "9100"))`` then raises
``ValueError: invalid literal for int() with base 10: ''`` inside the constructor,
before any of the surrounding startup verdicts can be written — the operator gets a
traceback instead of the stack they asked for, and the knob they meant to leave
alone is what killed it.

Production's own convention for the string knobs is already "blank means unset"
(``SPECPROOF_INVOICE_PERIOD`` is read as ``.strip()`` then ``override or fallback``
in ``storage/invoice_cron.py``; ``storage/config_guard.py`` counts ``not value`` as
unset). A numbered knob follows the same convention, so an unset or blank value
yields the documented default.

A value that is neither blank nor a number is a different thing: it is a mistaken
intent, not an absent one. Silently defaulting it would bind a port the operator
never asked for, so it is refused with the knob named, the offending text quoted
and the default it would have used stated.

The census of which shipped reads coerce an env value at all is derived, not
listed here: ``tests/unit/test_numeric_env_knobs_survive_an_empty_assignment.py``
walks the packages ``pyproject.toml`` declares and refuses a bare numeric
coercion that has not gone through this module.
"""

from __future__ import annotations

import os

#: The declared surface. ``tests/unit/test_env_template_binds_the_compose_knobs.py``
#: reads the ``(name, default)`` readers out of this list instead of retyping them,
#: so a helper renamed here stops being recognised by the knob census on the same
#: commit that stops being called — not one commit later.
__all__ = ["EnvKnobError", "float_env", "int_env"]


class EnvKnobError(ValueError):
    """A numeric env knob carries text that is neither blank nor a number."""


def _knob_text(name: str) -> str | None:
    """The knob's value as text, or ``None`` when it declares nothing.

    Both "absent" and "declared empty" mean nothing, because that is what an
    unset ``${VAR:-}`` interpolation says to the process reading it.
    """
    raw = os.getenv(name)
    if raw is None:
        return None
    text = raw.strip()
    return text if text else None


def _refusal(name: str, text: str, default: object) -> str:
    return (
        f"{name}={text!r} is neither blank nor a number. Unset it to get the "
        f"documented default ({default}), or give it a numeric value."
    )


def int_env(name: str, default: int) -> int:
    text = _knob_text(name)
    if text is None:
        return default
    try:
        return int(text)
    except ValueError as exc:
        raise EnvKnobError(_refusal(name, text, default)) from exc


def float_env(name: str, default: float) -> float:
    text = _knob_text(name)
    if text is None:
        return default
    try:
        return float(text)
    except ValueError as exc:
        raise EnvKnobError(_refusal(name, text, default)) from exc

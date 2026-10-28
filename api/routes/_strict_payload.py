"""One fail-closed extra-key rule for the create-request models.

``api/routes/jobs.py`` and ``api/routes/agent_console.py`` each carried a
byte-identical 78-node ``_reject_unknown_fields`` validator that differed only
in which allowlist constant it named (#514 measured that group; this merges
it). Input fail-closing is the same category as the auth guards in
``_guards.py``: with two copies, a fix to one leaves the other route family on
the old rule and nothing goes red — and here the silent half of that is an
execution-directive key reaching a worker.

The class attribute is a ``ClassVar``, so pydantic never turns it into a
payload field; it defaults to the empty set on purpose. A model that forgets to
declare one rejects *every* key it is sent, including its own legal fields,
which fails loudly in development instead of quietly widening the accepted
surface.
"""
from __future__ import annotations

from typing import Any, ClassVar

from pydantic import BaseModel, model_validator


class StrictAllowlistModel(BaseModel):
    """Base for request models that must refuse keys outside a stated allowlist.

    Subclasses declare ``payload_allowlist`` with the documented field names.
    Pydantic's own default silently *drops* extra keys, which is the wrong
    default for a create endpoint: a `command`/`env`/`docker`-style key would
    reach the handler unseen instead of answering 422.
    """

    payload_allowlist: ClassVar[frozenset[str]] = frozenset()

    @model_validator(mode="before")
    @classmethod
    def _reject_unknown_fields(cls, data: Any) -> Any:
        """Refuse any payload key outside ``cls.payload_allowlist``.

        A non-string key is unknown too — `{5: "x"}` must not be laundered into
        an accepted payload by ``str()``-ing the keys for comparison only.
        Non-dict input is passed through and rejected by pydantic itself.
        """
        if isinstance(data, dict):
            unknown = sorted(
                str(key)
                for key in data
                if not isinstance(key, str) or key not in cls.payload_allowlist
            )
            if unknown:
                raise ValueError(f"Unknown field(s): {', '.join(unknown)}")
        return data


__all__ = ["StrictAllowlistModel"]

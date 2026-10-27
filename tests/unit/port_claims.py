"""ONE owner for "which deploy declarations publish this port ON THE HOST".

Why this module exists
-----------------------

The ledger's queue carried a question for a long time: the STATIC predicate
("which deploy declarations occupy this number") and the RUNTIME predicate
("is this number held on this host right now") — should they be merged into
one?  #475 gave the runtime one an owner (``tests/unit/port_probe.py``).  This
module is the deploy-plane owner, and the measurement that answered the
question is recorded here.

THE ANSWER IS NO, and the measurement says why
-----------------------------------------------
The two predicates answer two different questions:

  * deploy plane — "does a file in this repository publish this number on the
    host?"  A fact about the repo.  It holds whether or not anything is
    running.
  * host plane — "is anything holding this number right now?"  A fact about
    this machine, at this instant.  It changes under you.

Merging them would produce a predicate that is wrong in BOTH directions: a
deploy file claims a number even when nothing is running (so a runtime probe
would miss it), and a number can be free now and claimed by a compose file
later (so a static scan cannot certify the host).  Each owner is therefore
scoped to its own plane, and the gate
``tests/unit/test_deploy_port_claims_speak_about_the_host.py`` refuses any
merge: the deploy owner may not probe the host, the host owner may not read
deploy files.

WHAT WAS ACTUALLY BROKEN (measured, not suspected)
---------------------------------------------------
The static predicate lived in ``tests/unit/test_invoice_cron_metrics_leg.py``
as ``_claims_the_number`` and compared ``str(port)`` against each mapping's
``left`` (host side) and ``right`` (container side) as STRINGS.

Every one of the 13 shipped mappings has a TEMPLATED host side
(``${MYSQL_PORT:-3306}``), so a string comparison could never match it.  The
predicate's hits came entirely from the CONTAINER side — the side that lives
in the container's network namespace and cannot collide with a host bind.  And
that is the very side the same file's own boundary note excludes ``expose:``
entries for:

    "``expose:`` entries are not in it because they declare an in-network
     container port, which cannot collide with a bind on the host"

So the predicate did not do what its own docstring said.  E4's docstring says
the thing it wants to catch is "**a host mapping** could take 9103 for
another service"; the implementation could not see a host mapping at all.  A
compose file publishing ``${SOME_PORT:-9103}:9103`` would have been reported
as "0 claims" — a FALSE GREEN on exactly the question E4 exists to ask.

What this module does
----------------------
``host_ports`` reads a mapping's host side the way the HOST sees it:

  ``${VAR:-N}``   the default when the variable is unset  -> N
  ``${VAR-N}``    the same, in the other spelling          -> N
  ``${VAR}``      no default: UNREADABLE, and said so     -> unresolved
  ``${VAR:?msg}`` required, no default: UNREADABLE        -> unresolved
  ``N``           a literal host port                     -> N
  ``A-B``         a range of host ports                   -> the whole range
  ``127.0.0.1:N`` an address prefix plus a host port      -> N
  ``N`` alone     a container-only row: NO host binding   -> nothing

An unreadable host side is REPORTED, never skipped: a row this module cannot
read must not become a row the census silently ignores.  ``deploy_claims``
raises ``UnreadableHostSideError`` rather than answering about a smaller
population than the one it was handed — a "0 claims" reading over a population
it does not cover is the false green this module exists to close, and the
house rule is "refuse, do not certify".  ``expose:`` entries are not read at
all — they never publish a host port — and that exclusion is now stated by
the code rather than only by a comment.
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Any

__all__ = [
    "HostPorts",
    "UnreadableHostSideError",
    "host_ports",
    "deploy_claims",
    "roster_claims",
    "claims",
    "unreadable_host_sides",
]

#: ``${VAR:-default}`` / ``${VAR-default}`` / ``${VAR:?err}`` / ``${VAR?err}``
_TEMPLATE = re.compile(r"^\$\{(?P<name>[A-Za-z_][A-Za-z0-9_]*)(?P<sep>:?[-?])(?P<value>[^}]*)\}$")
#: a plain number
_LITERAL = re.compile(r"^(?P<n>\d+)$")
#: a range of numbers
_RANGE = re.compile(r"^(?P<lo>\d+)-(?P<hi>\d+)$")
#: an IPv4 address used as a host prefix
_IPV4 = re.compile(r"^\d{1,3}(?:\.\d{1,3}){3}$")


@dataclass(frozen=True)
class HostPorts:
    """What one compose mapping publishes on the host.

    ``unresolved`` holds the raw host-side text when it could not be read.
    It is NOT an empty result: an unreadable row is a row the census cannot
    speak about, and the caller has to be told so.
    """

    singles: tuple[int, ...] = ()
    ranges: tuple[tuple[int, int], ...] = ()
    unresolved: str | None = None

    def covers(self, port: int) -> bool:
        """Whether this mapping publishes ``port`` on the host."""
        if port in self.singles:
            return True
        return any(lo <= port <= hi for lo, hi in self.ranges)

    def describe(self) -> str:
        """A human-readable form of what it publishes."""
        if self.unresolved is not None:
            return f"unreadable host side {self.unresolved!r}"
        parts = [str(n) for n in self.singles]
        parts += [f"{lo}-{hi}" for lo, hi in self.ranges]
        return ", ".join(parts) if parts else "no host port"


class UnreadableHostSideError(ValueError):
    """A row whose host side this module cannot read.

    Raised instead of skipped.  A skipped row is a row the census is not
    talking about, and a "0 claims" reading over a population it does not
    cover is the false green this module exists to close.  The house rule is
    "refuse, do not certify": the reader is told the population moved, not
    handed a smaller number than the one it asked about.
    """


def _numbers(text: str) -> HostPorts:
    """Read a host side that is already reduced to its port text."""
    literal = _LITERAL.match(text)
    if literal:
        return HostPorts(singles=(int(literal.group("n")),))
    span = _RANGE.match(text)
    if span:
        lo, hi = int(span.group("lo")), int(span.group("hi"))
        if lo > hi:
            return HostPorts(unresolved=text)
        return HostPorts(ranges=((lo, hi),))
    return HostPorts(unresolved=text)


def host_ports(left: str) -> HostPorts:
    """The host ports a mapping's host side publishes.

    ``left`` is the raw host-side text as the compose file spells it, which
    may carry an address prefix (``127.0.0.1:9103``).
    """
    text = left.strip()
    if not text:
        return HostPorts()
    # an address prefix: the host port is the last segment
    if ":" in text:
        prefix, _, tail = text.rpartition(":")
        if prefix and not _TEMPLATE.match(text) and _IPV4.match(prefix):
            text = tail.strip()
    template = _TEMPLATE.match(text)
    if template is not None:
        sep, value = template.group("sep"), template.group("value").strip()
        if sep in (":-", "-"):
            # a default: ${VAR:-N} and ${VAR-N} both fall back to N
            return _numbers(value)
        # ${VAR} / ${VAR:?msg} / ${VAR?msg}: no default to read
        return HostPorts(unresolved=left.strip())
    return _numbers(text)


def deploy_claims(port: int, mappings: list[dict[str, str]]) -> list[str]:
    """Which compose mappings publish ``port`` on the host.

    The CONTAINER side of a mapping is not a host claim: it names a port
    inside the container's network namespace, which cannot collide with a
    bind on the host.  Reading it as a claim would make this predicate
    report a collision that cannot happen, and — worse — would make it look
    like the predicate can see host mappings at all.

    A row whose host side cannot be read raises :class:`UnreadableHostSideError`
    rather than being skipped: see the class docstring.
    """
    out: list[str] = []
    for row in mappings:
        published = host_ports(row.get("left", ""))
        if published.unresolved is not None:
            raise UnreadableHostSideError(
                f"{row['service']}: host side {published.unresolved!r} cannot be read, so this "
                "population is not one this predicate can speak about"
            )
        if published.covers(port):
            out.append(f"{row['service']} 映射 {row['left']}:{row['right']}")
    return out


def roster_claims(port: int, roster: dict[str, Any]) -> list[str]:
    """Which scrape jobs target ``port``.

    A job that scrapes the number is a claim on it in a different sense than
    a host mapping: it does not hold the port, it reads it.  Both break the
    exempt endpoint's property (unread by anything else), so both are
    reported — and the wording keeps them apart.
    """
    out: list[str] = []
    for job, info in sorted(roster.items()):
        if int(info["port"]) == port:
            out.append(f"名册作业 {job} 抓 {info['host']}:{port}")
    return out


def claims(port: int, roster: dict[str, Any], mappings: list[dict[str, str]]) -> list[str]:
    """Everything that takes ``port`` away from the process that wants it."""
    return roster_claims(port, roster) + deploy_claims(port, mappings)


def unreadable_host_sides(mappings: list[dict[str, str]]) -> list[str]:
    """Every mapping whose host side this module could not read.

    A non-empty result means the census is not talking about the whole
    population, and a "0 claims" reading over it is not evidence.
    """
    out: list[str] = []
    for row in mappings:
        published = host_ports(row.get("left", ""))
        if published.unresolved is not None:
            out.append(f"{row['service']}: {published.unresolved}")
    return out

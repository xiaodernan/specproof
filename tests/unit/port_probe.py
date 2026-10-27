"""ONE owner for "give me a port nobody on this host is holding".

Why this module exists
----------------------

The probe that asks the OS for a free port was written three times, twice
under a name and once inline:

  tests/unit/test_metrics_port_ownership_leg.py                    def _free_port()
  tests/unit/test_scrape_roster_ports_answer_their_own_numbers.py  def _free_port()
  tests/unit/test_invoice_cron_metrics_leg.py                      inline, L172-175

The two named copies were byte-identical (the measurement is in
.scratch/probe475_free_port_copies.py: "IDENTICAL bodies (modulo the
docstring)"). Nothing bound them to each other, so this is the defect class
the project keeps closing in the declaration chain — two readers of one fact
with no gate between them. The queue item that asked for them to be merged
named a file that has never existed in git (``agent/multi_port.py``), so the
task was pointing at nothing.

Why the copies matter at all: every one of them is a TEST FIXTURE deciding
whether a number is free on this host. A fixture that hands out a port
somebody else already holds makes the gate that uses it report "the incumbent
holds this port" — a conclusion about the PRODUCT that is actually a
conclusion about the fixture. The two copies were identical today, so nothing
was wrong yet; that is exactly the condition under which the divergence is
invisible.

What this module does NOT hide
------------------------------

* The probe binds ``127.0.0.1``, while the shipped server binds whatever
  ``_resolve_bind_host()`` returns (wildcard in a container, loopback
  locally). On Linux and on Windows the two agree about what "held" means:
  a wildcard holder also blocks a loopback bind. The probe is therefore a
  statement about the LOOPBACK address, and callers that care about the
  wildcard address should say so rather than inherit this one silently.
* The number is RELEASED before the caller binds it (the probe socket is
  closed). That is a real window: between the close and the caller's bind,
  another process can take the number. It is inherent to "ask for a free
  port, then use it", and it is why the callers below re-read the port they
  actually got (``server_address[1]``) rather than trusting the number.
"""

from __future__ import annotations

import socket

__all__ = ["free_port"]


def free_port() -> int:
    """Ask the OS for a port nothing holds, then hand that number over.

    The socket is closed before returning, so the number is a *suggestion*,
    not a reservation — see the module docstring. Callers that then bind it
    must verify what they actually got.
    """
    probe = socket.socket()
    try:
        probe.bind(("127.0.0.1", 0))
        return int(probe.getsockname()[1])
    finally:
        probe.close()

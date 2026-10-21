"""The demo's tests must run on the JDKs people actually have (#381).

Spring Boot 3.4.3 manages Byte Buddy 1.15.11. Byte Buddy 1.15 cannot
read JDK 25's class files (major version 69), so the inline mock maker
fails with "Mockito cannot mock this class:
org.springframework.amqp.rabbit.core.RabbitTemplate" — and because that
mock is a @MockBean, the whole Spring context fails to load and **every**
demo test dies with "Failed to load ApplicationContext". The demo then
only runs on the JDKs Byte Buddy happened to know about.

Measured on this machine (2026-10-22, `demo/spring-backend`):

- JDK 25, before: 9 tests, 9 errors (the context never loads);
- JDK 25, after:  9 tests, 0 failures, 0 errors (BUILD SUCCESS);
- JDK 17, after:  9 tests, 0 failures, 0 errors (BUILD SUCCESS, with
  `-Djava.version=17` — the flag the pipeline passes so the demo
  compiles for the host JDK).

The fix is two version pins in the demo's pom. This test pins them, so a
Spring Boot upgrade that brings the old Byte Buddy back is caught here
rather than by a demo that cannot start.
"""

from __future__ import annotations

import re
from pathlib import Path

POM = (
    Path(__file__).resolve().parents[2]
    / "demo" / "spring-backend" / "pom.xml"
)

#: The first Byte Buddy line that reads JDK 25's class files (major
#: version 69), and the Mockito release that ships it.
_MIN_BYTE_BUDDY = (1, 17, 0)
_MIN_MOCKITO = (5, 17, 0)


def _version(text: str, name: str) -> tuple[int, ...]:
    match = re.search(rf"<{re.escape(name)}>([^<]+)</{re.escape(name)}>", text)
    assert match, f"the demo's pom does not pin {name}"
    return tuple(int(part) for part in match.group(1).strip().split("."))


def test_the_demo_pins_a_byte_buddy_that_reads_jdk_25() -> None:
    text = POM.read_text(encoding="utf-8")
    assert _version(text, "byte-buddy.version") >= _MIN_BYTE_BUDDY, (
        "Byte Buddy before 1.17 cannot read JDK 25's class files (major "
        "version 69): the inline mock maker then fails to mock "
        "RabbitTemplate and every demo test dies with 'Failed to load "
        "ApplicationContext'"
    )


def test_the_demo_pins_a_mockito_that_ships_that_byte_buddy() -> None:
    text = POM.read_text(encoding="utf-8")
    assert _version(text, "mockito.version") >= _MIN_MOCKITO, (
        "Mockito before 5.17 pulls Byte Buddy 1.15.x, which cannot read "
        "JDK 25's class files"
    )


def test_the_demo_still_declares_the_projects_jdk() -> None:
    """The pins are about the MOCK MAKER, not about the target: the demo
    still compiles for the JDK the project declares."""
    text = POM.read_text(encoding="utf-8")
    assert _version(text, "java.version") == (21,)

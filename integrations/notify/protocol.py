"""Notification connector protocol (first slice).

A connector is anything that can deliver a :class:`Notification` and report
an honest per-send status::

    {name, capabilities, send(notification) -> status}

The only implementations in this slice are the webhook connector
(integrations.notify.webhook.WebhookConnector — Slack / generic-with-HMAC /
Feishu payload dialects) and :class:`DisabledConnector`, the no-op every
unconfigured deployment resolves to via
integrations.notify.webhook.webhook_connector_from_env.
"""

from __future__ import annotations

from dataclasses import dataclass
from enum import StrEnum
from typing import Any, Protocol


class SendStatus(StrEnum):
    """Honest outcome of one send() call."""

    SENT = "sent"
    DISABLED = "disabled"
    FAILED = "failed"


@dataclass(frozen=True, slots=True)
class Notification:
    """One outbound notification.

    event_type is a dotted terminal event name (e.g. verification.blocked);
    text is the plain-text body every sink must be able to render; blocks is
    the optional Slack-block-style rich rendering (a tuple of block dicts);
    job_id correlates the notification with the verification job.
    """

    event_type: str
    title: str
    text: str
    blocks: tuple[dict[str, Any], ...] = ()
    job_id: str = ""


class Connector(Protocol):
    """Delivery contract: {name, capabilities, send(notification) -> status}.

    name identifies the implementation; capabilities is the set of feature
    names the sink supports; send() must return an honest SendStatus and must
    never raise for delivery-level failures (configuration errors may raise).
    """

    name: str
    capabilities: frozenset[str]

    def send(self, notification: Notification) -> SendStatus:
        """Deliver one notification; return the honest per-send status."""
        ...


class DisabledConnector:
    """No-op connector for unconfigured deployments.

    send() returns SendStatus.DISABLED without doing any work — an optional
    integration that is not configured must be a silent no-op, never a
    half-configured sender.
    """

    name = "disabled"
    capabilities: frozenset[str] = frozenset()

    def send(self, notification: Notification) -> SendStatus:
        """Disabled no-op: nothing is delivered, nothing is raised."""
        return SendStatus.DISABLED

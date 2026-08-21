"""GitLab Merge Request Hook parsing.

A Merge Request Hook body is a JSON object with object_kind ==
"merge_request". The fields this slice consumes live under
object_attributes (action, source_branch, target_branch, iid) and
project (id, path_with_namespace, http_url_to_repo).
"""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass
from typing import Any

MERGE_REQUEST_KIND = "merge_request"
ACTIONABLE_MERGE_REQUEST_ACTIONS: frozenset[str] = frozenset({"open", "update"})


class EventParseError(ValueError):
    """Raised when a webhook body is not a well-formed MR event."""


@dataclass(frozen=True)
class MergeRequestEvent:
    """The subset of a Merge Request Hook this integration consumes."""

    action: str
    project_id: int
    project_path: str
    repo_url: str
    source_branch: str
    target_branch: str
    merge_request_iid: int


def _required_str(container: Mapping[str, Any], field: str, section: str) -> str:
    value = container.get(field)
    if not isinstance(value, str) or not value:
        raise EventParseError(
            f"missing or invalid {section}.{field}: expected a non-empty string"
        )
    return value


def _required_int(container: Mapping[str, Any], field: str, section: str) -> int:
    value = container.get(field)
    if isinstance(value, bool) or not isinstance(value, int):
        raise EventParseError(
            f"missing or invalid {section}.{field}: expected an integer"
        )
    return value


def parse_merge_request_event(payload: Mapping[str, Any]) -> MergeRequestEvent:
    """Parse a Merge Request Hook body into a MergeRequestEvent.

    Raises EventParseError for bodies that are not merge_request hooks or
    that miss required fields. The action is carried through verbatim —
    deciding which actions trigger verification is the connector's job.
    """
    if payload.get("object_kind") != MERGE_REQUEST_KIND:
        raise EventParseError(
            "not a merge request event "
            f"(object_kind={payload.get('object_kind')!r})"
        )
    attrs_raw = payload.get("object_attributes")
    project_raw = payload.get("project")
    if not isinstance(attrs_raw, Mapping) or not isinstance(project_raw, Mapping):
        raise EventParseError(
            "merge request event missing object_attributes/project"
        )
    attrs: Mapping[str, Any] = attrs_raw
    project: Mapping[str, Any] = project_raw
    return MergeRequestEvent(
        action=_required_str(attrs, "action", "object_attributes"),
        source_branch=_required_str(attrs, "source_branch", "object_attributes"),
        target_branch=_required_str(attrs, "target_branch", "object_attributes"),
        merge_request_iid=_required_int(attrs, "iid", "object_attributes"),
        project_id=_required_int(project, "id", "project"),
        project_path=_required_str(project, "path_with_namespace", "project"),
        repo_url=_required_str(project, "http_url_to_repo", "project"),
    )

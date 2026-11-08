"""Contract tests for the Alertmanager wiring (PRODUCTION_SPEC §14/§17).

The alert sink exists since 2026-11-08: prometheus.yml gained an `alerting:`
block pointing at `alertmanager:9093`, compose.observability.yml gained a
prom/alertmanager:v0.27.0 service, and the shipped receiver is a documented
null sink (no notifications leave this file's config).

These tests pin the wiring, not the semantics of the alert rules (those are
covered by test_alert_*):
  * alertmanager.yml parses, its route receivers resolve to declared
    receivers, every declared receiver is spelled once, and the shipped
    placeholder receiver carries NO notification configs —
    a null sink that accidentally gained a notification config would
    silently become an unreviewed paging path;
  * prometheus.yml's alerting target hostname equals the compose service
    name, and its rule_files basename exists in the repo;
  * compose.observability.yml pins the alertmanager image by semver tag
    (never :latest), mounts the config read-only, and declares the
    alertmanager-data volume;
  * OBSERVABILITY.md names the same image tag as the compose file.
"""

from __future__ import annotations

import re
from pathlib import Path
from typing import Any

import yaml

ROOT = Path(__file__).resolve().parents[2]
ALERTMANAGER_YML = ROOT / "infra" / "prometheus" / "alertmanager.yml"
PROMETHEUS_YML = ROOT / "infra" / "prometheus" / "prometheus.yml"
COMPOSE = ROOT / "compose.observability.yml"
OBSERVABILITY_MD = ROOT / "docs" / "operations" / "OBSERVABILITY.md"

NULL_RECEIVER = "null"


def _load(path: Path) -> dict[str, Any]:
    data: dict[str, Any] = yaml.safe_load(path.read_text(encoding="utf-8"))
    return data


def _receivers_named(cfg: dict[str, Any]) -> list[str]:
    return [str(r.get("name")) for r in cfg.get("receivers", [])]


def test_alertmanager_yml_parses_and_declares_routes_and_receivers() -> None:
    cfg = _load(ALERTMANAGER_YML)
    assert cfg.get("global", {}).get("resolve_timeout"), "global.resolve_timeout missing"
    route = cfg.get("route")
    assert route and route.get("receiver"), "top-level route.receiver missing"
    names = _receivers_named(cfg)
    assert names == [NULL_RECEIVER], f"expected exactly the null receiver, got {names}"
    assert route["receiver"] in names
    for sub in route.get("routes", []):
        assert sub.get("receiver") in names


def test_the_shipped_receiver_is_a_true_null_sink() -> None:
    cfg = _load(ALERTMANAGER_YML)
    (receiver,) = cfg["receivers"]
    assert receiver["name"] == NULL_RECEIVER
    # A receiver with no notification configs is the documented black hole.
    # Any of these appearing silently would ship an unreviewed paging path.
    forbidden = {
        "slack_configs", "webhook_configs", "pagerduty_configs", "email_configs",
        "opsgenie_configs", "victorops_configs", "pushover_configs", "wechat_configs",
        "sns_configs", "sns_config", "telegram_configs", "discord_configs",
        "msteams_configs",
    }
    leaked = forbidden & set(receiver)
    assert not leaked, (
        f"the shipped null receiver carries notification configs: {sorted(leaked)}; "
        f"wiring a real destination is deliberate — update this gate with the decision"
    )


def test_prometheus_yml_points_alerting_at_the_compose_service() -> None:
    cfg = _load(PROMETHEUS_YML)
    alertmanagers = cfg.get("alerting", {}).get("alertmanagers", [])
    targets = [
        t
        for am in alertmanagers
        for sc in am.get("static_configs", [])
        for t in sc.get("targets", [])
    ]
    assert targets, "prometheus.yml declares no alertmanager target"
    compose = _load(COMPOSE)
    service_names = list(compose.get("services", {}))
    for target in targets:
        host, _, port = str(target).partition(":")
        assert host in service_names, (
            f"prometheus alerting target host {host!r} is not a "
            f"compose service in compose.observability.yml"
        )
        assert port.isdigit(), f"non-numeric port in target {target!r}"


def test_prometheus_rule_files_exist_and_mount_matches() -> None:
    cfg = _load(PROMETHEUS_YML)
    rule_files = cfg.get("rule_files", [])
    assert rule_files, "prometheus.yml declares no rule_files"
    for rf in rule_files:
        assert (ROOT / "infra" / "prometheus" / Path(rf).name).is_file(), (
            f"rule_file {rf} has no matching infra/prometheus file"
        )


def test_compose_pins_the_alertmanager_image_and_mounts_config_readonly() -> None:
    compose = _load(COMPOSE)
    assert "alertmanager-data" in compose.get("volumes", {})
    svc = compose.get("services", {}).get("alertmanager")
    assert svc, "compose.observability.yml has no alertmanager service"
    image = svc.get("image", "")
    match = re.fullmatch(r"prom/alertmanager:v\d+\.\d+\.\d+", image)
    assert match, f"alertmanager image not pinned to a semver tag: {image!r}"
    volume_specs = svc.get("volumes", [])
    read_only = [v for v in volume_specs if str(v).endswith(":ro")]
    assert any("infra/prometheus/alertmanager.yml" in str(v) for v in read_only), (
        "alertmanager.yml must be mounted read-only"
    )
    ports = svc.get("ports", [])
    assert any(str(p).endswith(":9093") for p in ports), "alertmanager must publish 9093"


def test_compose_prometheus_mounts_the_file_promtool_checks() -> None:
    compose = _load(COMPOSE)
    svc = compose["services"]["prometheus"]
    mounts = [str(v) for v in svc.get("volumes", [])]
    assert any("alerts-slo.yml" in v for v in mounts)
    mountpoints = [v.split(":")[1] for v in mounts if len(v.split(":")) >= 2]
    assert "/etc/prometheus/alerts-slo.yml" in mountpoints


def test_observability_doc_names_the_same_image_tag() -> None:
    compose = _load(COMPOSE)
    image = compose["services"]["alertmanager"]["image"]
    md = OBSERVABILITY_MD.read_text(encoding="utf-8")
    assert image in md, (
        "OBSERVABILITY.md does not name the same alertmanager image as the compose file"
    )
    assert "9093" in md

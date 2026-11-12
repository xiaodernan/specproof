"""Four Spring Cloud services must agree on one release train and one wire map.

#1606 added ``services/config-server`` (8888, native backend) and another lane
left ``services/discovery-server`` (8761, standalone Eureka) untracked. The
gateway consumes both: ``spring.config.import: optional:configserver:...`` and
``eureka.service-url.defaultZone``. #1608 lands the second module and wires
both into CI.

Without a reconciliation gate, the failure modes are all silent:

* one pom drifts to a different Boot / Spring Cloud train while CI still says
  "green" (the poms are independent — there is no parent aggregator);
* a config server silently serves nothing because its native backend
  points at the wrong directory, or a standalone registry tries to
  register with itself;
* ``config/gateway.yml`` (what the config server SERVES) drifts from the
  gateway's own defaults, so enabling the config server changes edge behavior;
* a new service appears under ``services/`` that no CI job compiles —
  ``test_ci_runs_the_java_services.py`` already catches this one; this gate
  re-asserts it in the same run so the whole picture is visible together.

Everything here is read from the shipped poms / YAML / workflow, not from a
hand-written copy.
"""

from __future__ import annotations

import subprocess
import xml.etree.ElementTree as ET
from pathlib import Path
from typing import Any

import yaml

_REPO = Path(__file__).resolve().parents[2]
_SERVICES = _REPO / "services"
_NS = {"m": "http://maven.apache.org/POM/4.0.0"}
_EXPECTED_BOOT = "3.4.3"
_EXPECTED_JAVA = "21"
_EXPECTED_CLOUD_TRAIN = "2024.0.1"


def _modules() -> list[Path]:
    out = subprocess.run(
        ["git", "ls-files", "services/*/pom.xml"],
        capture_output=True, text=True, encoding="utf-8", errors="replace",
        check=True, cwd=_REPO,
    ).stdout
    return [_REPO / line.strip() for line in out.splitlines() if line.strip()]


def _pom(path: Path) -> ET.Element:
    return ET.parse(path).getroot()


def _text(root: ET.Element, xpath: str) -> str:
    found = root.find(xpath, _NS)
    return "" if found is None or found.text is None else found.text.strip()


def _yaml(path: Path) -> dict[str, Any]:
    data: object = yaml.safe_load(path.read_text(encoding="utf-8"))
    assert isinstance(data, dict), f"{path} is not a YAML mapping"
    result: dict[str, Any] = {}
    for key, value in data.items():
        result[str(key)] = value
    return result


def _gateway_yaml() -> dict[str, Any]:
    return _yaml(_SERVICES / "gateway" / "src" / "main" / "resources" / "application.yml")


def test_the_module_census_sees_all_four_services() -> None:
    names = sorted(p.parent.name for p in _modules())
    assert names == [
        "config-server", "control-plane", "discovery-server", "gateway",
    ], f"services/ census drifted: {names}"


def test_every_service_shares_one_boot_and_java_version() -> None:
    wrong = []
    for pom in _modules():
        root = _pom(pom)
        boot = _text(root, "m:parent/m:version")
        artifact = _text(root, "m:parent/m:artifactId")
        java = _text(root, "m:properties/m:java.version")
        if (boot, artifact, java) != (
            _EXPECTED_BOOT, "spring-boot-starter-parent", _EXPECTED_JAVA
        ):
            wrong.append(f"{pom.parent.name}: boot={boot} parent={artifact} java={java}")
    assert not wrong, (
        "the four poms are independent (no aggregator parent), so a version "
        f"drift is invisible to Maven itself: {wrong}"
    )


def test_every_declared_spring_cloud_train_is_the_same() -> None:
    trains: dict[str, str] = {}
    for pom in _modules():
        value = _text(_pom(pom), "m:properties/m:spring-cloud.version")
        if value:
            trains[pom.parent.name] = value
    assert trains, "no pom declares a Spring Cloud train — the probe went blind"
    assert set(trains.values()) == {_EXPECTED_CLOUD_TRAIN}, (
        f"the services disagree on their Spring Cloud release train: {trains}"
    )
    assert "gateway" in trains and "config-server" in trains and "discovery-server" in trains


def test_each_registry_service_declares_and_listens_on_its_own_port() -> None:
    """The two new services must not fight over a port or lose their backend.

    The gateway's own config-client / eureka-client wiring is still another
    lane's in-flight work (see the boundary note in the module docstring), so
    this leg deliberately checks the SERVER side only — the part #1608 lands.
    """
    config = _yaml(
        _SERVICES / "config-server" / "src" / "main" / "resources" / "application.yml"
    )
    discovery = _yaml(
        _SERVICES / "discovery-server" / "src" / "main" / "resources" / "application.yml"
    )
    assert int(config["server"]["port"]) == 8888
    assert int(discovery["server"]["port"]) == 8761
    assert config["server"]["port"] != discovery["server"]["port"]

    # A file-backed config server must actually point at the directory that
    # holds gateway.yml, or it boots and serves nothing.
    native = config["spring"]["cloud"]["config"]["server"]["native"]
    assert config["spring"]["profiles"]["active"] == "native"
    assert "classpath:/config/" in str(native["search-locations"])

    client = discovery["eureka"]["client"]
    assert client["register-with-eureka"] is False
    assert client["fetch-registry"] is False, (
        "a single-node registry must not try to register with a peer, or it "
        "fills its own log with failed self-lookups"
    )


def test_the_config_server_serves_the_same_defaults_the_edge_ships() -> None:
    served = _yaml(
        _SERVICES / "config-server" / "src" / "main" / "resources"
        / "config" / "gateway.yml"
    )["specproof"]["gateway"]
    local = _gateway_yaml()["specproof"]["gateway"]

    # mq-events is declared in BOTH places; a drift means enabling the config
    # server silently changes the W190 bus contract at the edge.
    assert served["mq-events"] == local["mq-events"], (
        f"config-server serves {served['mq-events']} but the edge ships "
        f"{local['mq-events']} — same key, two answers"
    )

    properties_java = (
        _SERVICES / "gateway" / "src" / "main" / "java" / "dev"
        / "specproof" / "gateway" / "config" / "GatewayProperties.java"
    ).read_text(encoding="utf-8")
    for key, nested in (
        ("request-size", "RequestSize"),
        ("security-headers", "SecurityHeaders"),
        ("mq-events", "MqEvents"),
    ):
        assert key in served, f"config/gateway.yml stopped serving {key}"
        assert f"class {nested}" in properties_java, (
            f"config-server serves {key} but GatewayProperties has no "
            f"{nested} holder — the setting would be silently ignored"
        )


def test_every_service_has_its_own_ci_maven_leg() -> None:
    workflow = _yaml(_REPO / ".github" / "workflows" / "ci.yml")
    legs = {
        str(step.get("working-directory", "")).strip("/")
        for job in workflow["jobs"].values()
        for step in job.get("steps", [])
        if str(step.get("run", "")).startswith("mvn")
    }
    missing = [p.parent.relative_to(_REPO).as_posix() for p in _modules()
               if p.parent.relative_to(_REPO).as_posix() not in legs]
    assert not missing, (
        f"these services have no CI Maven leg: {missing}. A module nobody "
        "compiles rots silently (see test_ci_runs_the_java_services.py)"
    )

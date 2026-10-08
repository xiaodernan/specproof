"""#220: the Prometheus scrape roster and the deployed alert set are two
hand-maintained halves of the same promise, and nothing read them together.

Measured before writing anything (.scratch/probe220_scrape_roster.py):

* prometheus.yml declares 6 scrape jobs. Three of them were named by an
  ``up{job=...} == 0`` probe (api, worker, outbox-relay); three were not
  (prometheus, otel-collector, rabbitmq).
* Two deployed rules — SpecproofVerifyQueueBacklogHigh and
  SpecproofVerifyDlqNonEmpty — read ``rabbitmq_queue_messages`` /
  ``..._ready``, series that ONLY the rabbitmq job's ``/metrics/per-object``
  rendering produces. PromQL judges nothing over an absent series, so when
  that scrape dies the two rules do not go pending: they go *silent*, during
  the exact incident they exist for. OBSERVABILITY.md had even written the
  mechanism down ("第三方名的真伪只能靠抓取目标 up 与实际查询验证") — but no rule
  read ``up{job="rabbitmq"}``, so the named guard had no reader.
* prometheus.yml's own header comment claimed 「全部为服务名 DNS」 five lines
  above its ``localhost:9090`` entry, and its target inventory listed 5 hosts
  under a 6-job roster (rabbitmq missing).
* OBSERVABILITY.md §1's prometheus row listed 4 host:port targets: it omitted
  rabbitmq:15692 entirely and named its own self-target only as the word
  「自身」. R10 compares host:port tokens, so a target named in prose but not
  written as host:port is charged as an omission — a reader cannot check a
  target they cannot locate.

The unit therefore does three things: adds the missing probe
(SpecproofRabbitMQExporterDown, and #219's exemption list grows by it), puts
the two inventories back in agreement with the config, and gates the pairing
so a future rule cannot read a family whose scrape job nobody watches. The
unprobed jobs are not deleted from the claim — they are declared in
_UNPROBED_JOBS below and each entry's reason is *derived* here, not trusted:
an exemption that stops being true reds, and an exemption that no rule
justifies cannot be added silently.

Case map (used by .scratch/arm220-roster-arms.py):
  R1  roster parse + target shape floors
  R2  prometheus.yml header inventory <-> scrape_configs (bijection by host:port)
  R3  the 「服务名 DNS」 prose claim carves out its own real exception
  R4  every ``up{job=...}`` probe names a declared job (no dead probes)
  R5  probed / _UNPROBED_JOBS partitions the roster, both directions
  R6  each declared gap is backed by derivation, not prose
  R7  every family a rule reads has a declared provider job
  R8  a rule reading a family must have a provider job with a liveness probe
  R9  the guarding probe names the alerts it guards (causal disclosure)
  R10 OBSERVABILITY.md §1 row's target list == the roster
  R11 the "15s 抓取" claim equals global.scrape_interval
  R12 arming: the files this gate reads are the files compose mounts at the
      paths prometheus is started with
  R13 #219's _LIVENESS_RULES exemption list == the probes derived here
"""

from __future__ import annotations

import re
from pathlib import Path

import yaml

ROOT = Path(__file__).resolve().parents[2]
PROM_YML = ROOT / "infra" / "prometheus" / "prometheus.yml"
ALERTS_YML = ROOT / "infra" / "prometheus" / "alerts-slo.yml"
COMPOSE = ROOT / "compose.observability.yml"
OBS = ROOT / "docs" / "operations" / "OBSERVABILITY.md"
GATE_219 = ROOT / "tests" / "unit" / "test_alert_rules_bind_their_own_threshold_table.py"

#: ``host:port`` a job may target without the host being a compose service
#: name. Prometheus scrapes itself through the loopback interface, so the
#: roster's one non-DNS target is declared here and R3 forces the prose claim
#: in prometheus.yml to name it.
_SELF_TARGET_HOSTS = {"localhost"}

#: Which scrape jobs can serve a metric family. A prefix nobody declares makes
#: R7 refuse the rule: an alert on a series no scraped target publishes is a
#: rule that can never fire, and that failure mode is silent by construction.
_FAMILY_OWNERS: dict[str, tuple[str, ...]] = {
    # specproof_* is emitted by observability/metrics.py and served by every
    # process that imports it — the three /metrics jobs running this repo's
    # code. The third-party jobs serve none of it.
    "specproof_": ("api", "worker", "outbox-relay"),
    # rabbitmq_prometheus plugin output; served only by its own job, and only
    # under /metrics/per-object for the per-queue series the alerts select.
    "rabbitmq_": ("rabbitmq",),
}

#: Jobs with no ``up{job=...} == 0`` rule, and the claim that justifies it.
#: R6 re-derives each reason from the config; a reason that stops holding, or
#: a job that quietly gains a probe, reds instead of leaving a stale hiding
#: place (the reach guard every skip list needs).
_UNPROBED_JOBS: dict[str, str] = {
    "prometheus": (
        "self-scrape: prometheus evaluates these rules, so a rule it would "
        "have to fire cannot announce its own death — no remote_write and no "
        "watchdog job exists to carry that signal"
    ),
    "otel-collector": (
        "no deployed rule reads a family this job serves, so its down state "
        "cannot silence an alert"
    ),
}

_PROM_FENCE = re.compile(r"^(?P<header>.*?)^global:", re.S | re.M)
_TARGET_TOKEN = re.compile(r"\b([a-z][a-z0-9.-]*):(\d{2,5})\b")
_LIVENESS_EXPR = re.compile(r'^up\{job="(?P<job>[^"]+)"\} == 0$')
_UP_SELECTOR = re.compile(r'up\{job="(?P<job>[^"]+)"\}')
#: A PromQL identifier that is not a function call. Braces and quoted label
#: matchers are stripped first, so `by`/`without`/`offset` leftovers cannot
#: surface; R7 refuses anything unmapped anyway, so a false token is a red,
#: never a silent pass.
_FAMILY_TOKEN = re.compile(r"\b([a-z][a-z0-9_]{2,})\b")


def _prom_text() -> str:
    return PROM_YML.read_text(encoding="utf-8")


def _prom_config() -> dict[str, object]:
    data = yaml.safe_load(_prom_text())
    assert isinstance(data, dict), f"{PROM_YML.name} did not parse to a mapping"
    return data


def _jobs() -> dict[str, dict[str, object]]:
    """job_name -> {metrics_path, targets}; floored so an empty parse cannot
    make every downstream 'no X found' claim pass about nothing."""
    configs = _prom_config()["scrape_configs"]
    assert isinstance(configs, list), "scrape_configs is not a list"
    out: dict[str, dict[str, object]] = {}
    for entry in configs:
        name = entry["job_name"]
        targets: list[str] = []
        for sc in entry.get("static_configs", []):
            targets.extend(str(t) for t in sc["targets"])
        out[str(name)] = {
            "metrics_path": str(entry.get("metrics_path", "/metrics")),
            "targets": targets,
        }
    assert len(out) >= 6, f"roster parse collapsed: {sorted(out)}"
    for name, info in out.items():
        assert info["targets"], f"{name} scrapes nothing"
    return out


def _rules() -> dict[str, dict[str, str]]:
    data = yaml.safe_load(ALERTS_YML.read_text(encoding="utf-8"))
    out: dict[str, dict[str, str]] = {}
    for group in data["groups"]:
        for rule in group["rules"]:
            if not rule.get("alert"):
                continue
            annotations = rule.get("annotations", {}) or {}
            out[str(rule["alert"])] = {
                "expr": str(rule["expr"]),
                "for": str(rule.get("for", "")),
                "summary": str(annotations.get("summary", "")),
                "description": str(annotations.get("description", "")),
            }
    assert len(out) >= 16, f"rule parse collapsed: {len(out)} rules"
    return out


def _probes() -> dict[str, str]:
    """Liveness rules: probe expr -> the alert that owns it."""
    out = {
        match.group("job"): name
        for name, rule in _rules().items()
        if (match := _LIVENESS_EXPR.match(rule["expr"]))
    }
    assert len(out) >= 4, f"liveness probe parse collapsed: {out}"
    return out


def _dead_probes() -> dict[str, list[str]]:
    """Rules selecting a job that the roster no longer scrapes."""
    jobs = set(_jobs())
    out: dict[str, list[str]] = {}
    for name, rule in _rules().items():
        for job in _UP_SELECTOR.findall(rule["expr"]):
            if job not in jobs:
                out.setdefault(name, []).append(job)
    return out


def _families(expr: str) -> set[str]:
    """Metric families an expr reads, structurally: label matchers and quoted
    strings go first, then every identifier that is not a call."""
    stripped = re.sub(r"\{[^}]*\}", " ", expr)
    stripped = re.sub(r'"[^"]*"', " ", stripped)
    called = re.sub(r"[a-zA-Z_][a-zA-Z0-9_]*\s*\(", "(", stripped)
    return set(_FAMILY_TOKEN.findall(called))


def _owners_of(family: str) -> tuple[str, ...]:
    for prefix, owners in _FAMILY_OWNERS.items():
        if family.startswith(prefix):
            return owners
    return ()


def _header_comment() -> str:
    """The comment block above `global:` — the file's own roster inventory."""
    text = _prom_text()
    fence = _PROM_FENCE.search(text)
    assert fence is not None, "could not locate global:/scrape_configs in prometheus.yml"
    return fence.group("header")


def _section(text: str, start: str, stop: str) -> str:
    return text[text.index(start):text.index(stop)]


# ─────────────────────────────────────────────────────────── R1 ───────────────────────────
def test_roster_targets_are_host_port_and_declared() -> None:
    jobs = _jobs()
    hosts = {t.rsplit(":", 1)[0] for info in jobs.values() for t in info["targets"]}
    service_hosts = hosts - _SELF_TARGET_HOSTS
    for job in service_hosts:
        assert job in jobs, (
            f"target host {job!r} is not a declared job name — either the "
            f"roster renamed it or a compose service is being scraped by a "
            f"stale name"
        )
    assert hosts & _SELF_TARGET_HOSTS, (
        f"_SELF_TARGET_HOSTS declares {sorted(_SELF_TARGET_HOSTS)} as the only "
        f"non-service-DNS exception but no target uses it: the carve-out is "
        f"dead, so prometheus.yml's prose claim should stop qualifying it"
    )
    for name, info in jobs.items():
        for target in info["targets"]:  # type: ignore[union-attr]
            assert _TARGET_TOKEN.search(target), f"{name} target {target!r} is not host:port"


# ─────────────────────────────────────────────────────────── R2 ───────────────────────────
def test_scrape_configs_pair_with_the_header_inventory() -> None:
    """The header comment is the file's only human-facing roster. It listed 5
    targets while the config scraped 6, so the rabbitmq job — the sole source
    of the broker-side alerts — appeared nowhere in it."""
    comment = _header_comment()
    listed = {f"{h}:{p}" for h, p in _TARGET_TOKEN.findall(comment)}
    scraped = {t for info in _jobs().values() for t in info["targets"]}
    assert listed == scraped, (
        f"header comment names {sorted(listed - scraped)} that no job scrapes; "
        f"jobs scrape {sorted(scraped - listed)} which the comment never lists"
    )


# ─────────────────────────────────────────────────────────── R3 ───────────────────────────
def test_the_dns_prose_claim_names_its_own_exception() -> None:
    """「全部为服务名 DNS」 was false on its own file: five lines below it the
    roster scrapes localhost:9090. A blanket claim may stay only while the
    config actually supports it; otherwise the sentence must name the host
    that breaks it."""
    comment = _header_comment()
    non_dns = sorted(
        host
        for info in _jobs().values()
        for host in (t.rsplit(":", 1)[0] for t in info["targets"])  # type: ignore[union-attr]
        if host not in set(_jobs())
    )
    claim_lines = [line for line in comment.splitlines() if "DNS" in line]
    assert claim_lines, "the header comment no longer makes a DNS claim to bind"
    claim = " ".join(claim_lines)
    for host in non_dns:
        assert host in claim, (
            f"the roster scrapes {host!r}, which is not a compose service name, "
            f"but the 「服务名 DNS」 sentence does not carve it out: {claim!r}"
        )


# ─────────────────────────────────────────────────────────── R4 ───────────────────────────
def test_no_probe_selects_a_job_the_roster_dropped() -> None:
    dead = _dead_probes()
    assert not dead, (
        f"these rules alert on up{{job=...}} for a target nothing scrapes — "
        f"the series never exists, so the alert can never fire: {dead}"
    )


# ─────────────────────────────────────────────────────────── R5 ───────────────────────────
def test_roster_partitions_into_probed_and_declared_gaps() -> None:
    """Every scraped job either has a liveness probe or is declared here as a
    justified gap. A job added to the roster with neither reds; so does an
    exemption this gate can no longer justify (R6 does that half)."""
    jobs = set(_jobs())
    probed = set(_probes())
    gaps = set(_UNPROBED_JOBS)
    assert probed | gaps == jobs, (
        f"scraped by nobody watched: {sorted(jobs - probed - gaps)}; "
        f"probed or exempted but not in the roster: {sorted((probed | gaps) - jobs)}"
    )
    assert not (probed & gaps), (
        f"both probed and declared unprobeable — the exemption is stale: "
        f"{sorted(probed & gaps)}"
    )
    assert len(probed) >= 4, f"only {len(probed)} liveness probes for {len(jobs)} jobs"


# ─────────────────────────────────────────────────────────── R6 ───────────────────────────
def test_declared_gaps_are_backed_by_derivation() -> None:
    jobs = _jobs()
    config = _prom_config()
    probes = _probes()
    for job, reason in _UNPROBED_JOBS.items():
        assert job in jobs, f"{job} is exempted from probing but is not in the roster"
        assert job not in probes, (
            f"{job} now has a liveness probe ({probes.get(job)!r}) yet is still "
            f"declared unprobed — delete the exemption: {reason!r}"
        )
        assert len(reason) > 30, f"{job}'s exemption reason is not a claim: {reason!r}"
    # The otel-collector half of the table is only honest while no rule reads
    # a family that job serves.
    served = {
        prefix: job
        for prefix, owners in _FAMILY_OWNERS.items()
        for job in owners
    }
    read = {f for rule in _rules().values() for f in _families(rule["expr"])}
    for job in set(jobs) - set(probes):
        owned = [f for f in sorted(read) if served.get(_prefix_of(f)) == job]
        assert not owned, (
            f"{job} is exempted as 'no rule reads it' but these families map to "
            f"it: {owned}"
        )
    # The prometheus half: self-scrape is only unwatchable while nothing
    # external can carry the signal — no remote_write, no watchdog job.
    if "prometheus" in _UNPROBED_JOBS:
        assert not config.get("remote_write"), (
            "prometheus now ships data somewhere else; the 'nobody can announce "
            "its own death' reason no longer holds and it needs a probe"
        )
        assert not any("blackbox" in job for job in jobs), (
            "a probe job now exists that can watch prometheus itself, so the "
            "exemption is stale"
        )


def _prefix_of(family: str) -> str:
    for prefix in _FAMILY_OWNERS:
        if family.startswith(prefix):
            return prefix
    raise AssertionError(f"{family} has no declared owner prefix (R7 refuses it)")


# ─────────────────────────────────────────────────────────── R7 ───────────────────────────
def test_every_family_a_rule_reads_has_a_declared_provider() -> None:
    jobs = set(_jobs())
    orphan: dict[str, list[str]] = {}
    phantom: dict[str, list[str]] = {}
    for name, rule in _rules().items():
        for family in sorted(_families(rule["expr"])):
            owners = _owners_of(family)
            if not owners:
                orphan.setdefault(family, []).append(name)
            elif not set(owners) <= jobs:
                phantom.setdefault(family, []).extend(sorted(set(owners) - jobs))
    assert not orphan, (
        f"these series belong to no scraped job in the roster, so the rules "
        f"reading them can never fire: {sorted(orphan)}"
    )
    assert not phantom, f"declared provider job is not in the roster: {phantom}"


# ─────────────────────────────────────────────────────────── R8 ───────────────────────────
def test_a_rule_reading_a_family_has_a_provider_job_with_a_liveness_probe() -> None:
    """The silent-darkness clause. An alert whose series come from one scrape
    job is only an alert while that job is up: absent series never enter
    pending, so the outage that should trigger the underlying signal removes
    the signal instead. rabbitmq_* was exactly this — two broker-side alerts
    reading a job nothing watched."""
    probes = _probes()
    silent: dict[str, list[str]] = {}
    for name, rule in _rules().items():
        if _LIVENESS_EXPR.match(rule["expr"]):
            continue
        for family in sorted(_families(rule["expr"])):
            owners = _owners_of(family)
            if owners and not (set(owners) & set(probes)):
                silent.setdefault(name, []).append(f"{family} (job {owners})")
    assert not silent, (
        f"these alerts read a family whose only provider jobs have no "
        f"up{{job=...}} == 0 probe — when that scrape dies the alert goes "
        f"silent instead of firing: {silent}"
    )


# ─────────────────────────────────────────────────────────── R9 ───────────────────────────
def test_the_guarding_probe_names_the_alerts_it_guards() -> None:
    """R8 proves a sole-provider probe must EXIST; this case proves it also
    says what it guards. A family with exactly one declared provider job means
    that job's probe is the only rule standing between an outage and a silent
    alert set, so the probe has to name those alerts or an operator reading
    the rule file cannot tell which blindness it buys back."""
    probes = _probes()
    guarded: dict[str, set[str]] = {}
    for name, rule in _rules().items():
        if _LIVENESS_EXPR.match(rule["expr"]):
            continue
        for family in sorted(_families(rule["expr"])):
            owners = _owners_of(family)
            if len(owners) != 1:
                continue
            probe_name = probes.get(owners[0])
            if probe_name:
                guarded.setdefault(probe_name, set()).add(name)
    assert guarded, (
        "no family has a single provider job with a probe, so this claim is "
        "about nothing — R8's sole-provider case went empty"
    )
    for probe_name, alerts in sorted(guarded.items()):
        description = _rules()[probe_name]["description"]
        for alert in sorted(alerts):
            assert alert in description, (
                f"{probe_name} is the only liveness backstop for {alert} "
                f"(sole provider job of the family it reads), but its "
                f"description never names it"
            )


# ────────────────────────────────────────────────────────── R10 ───────────────────────────
def test_observability_service_row_lists_every_scrape_target() -> None:
    """§1's prometheus row is the operator's roster. It carried the same
    5-target omission as the config comment."""
    text = OBS.read_text(encoding="utf-8")
    row = next(
        line
        for line in _section(text, "## 1.", "## 2.").splitlines()
        if line.startswith("| prometheus |")
    )
    listed = {f"{h}:{p}" for h, p in _TARGET_TOKEN.findall(row)}
    scraped = {t for info in _jobs().values() for t in info["targets"]}
    assert listed == scraped, (
        f"§1's prometheus row lists {sorted(listed - scraped)} that nothing "
        f"scrapes and omits {sorted(scraped - listed)}"
    )


# ────────────────────────────────────────────────────────── R11 ───────────────────────────
def test_observability_scrape_interval_claim_matches_the_config() -> None:
    text = OBS.read_text(encoding="utf-8")
    row = next(
        line
        for line in _section(text, "## 1.", "## 2.").splitlines()
        if line.startswith("| prometheus |")
    )
    claimed = re.search(r"(\d+)s 抓取", row)
    assert claimed is not None, f"§1's prometheus row states no scrape interval: {row!r}"
    configured = str(_prom_config()["global"]["scrape_interval"])  # type: ignore[index]
    assert claimed.group(1) + "s" == configured, (
        f"§1 says {claimed.group(1)}s 抓取, prometheus.yml sets "
        f"scrape_interval: {configured}"
    )


# ────────────────────────────────────────────────────────── R12 ───────────────────────────
def test_the_files_this_gate_reads_are_the_ones_prometheus_loads() -> None:
    """A config gate that grades a file the deployment never loads certifies
    nothing. Prometheus is started with --config.file and reads rule_files;
    compose mounts both by path. Those paths must resolve back to the two
    files this gate opened."""
    mounts = _compose_mounts()
    config_file = _arg_from_compose("--config.file")
    assert config_file is not None, "prometheus is started without --config.file"
    assert config_file in mounts, (
        f"--config.file {config_file!r} is not mounted by compose.observability.yml"
    )
    assert mounts[config_file] == _relative(PROM_YML), (
        f"{config_file} comes from {mounts[config_file]!r}, not the "
        f"{PROM_YML.relative_to(ROOT)!s} this gate parses"
    )
    rule_files = _prom_config()["rule_files"]
    assert isinstance(rule_files, list) and rule_files, "prometheus.yml loads no rule files"
    for entry in rule_files:
        dest = str(entry)
        assert dest in mounts, (
            f"rule_files names {dest!r} but no compose mount provides it — the "
            f"gated rule file is not the one prometheus would read"
        )
        assert mounts[dest] == _relative(ALERTS_YML), (
            f"{dest} is mounted from {mounts[dest]!r}, not the "
            f"{ALERTS_YML.relative_to(ROOT)!s} this gate parses"
        )


def _compose_mounts() -> dict[str, str]:
    data = yaml.safe_load(COMPOSE.read_text(encoding="utf-8"))
    out: dict[str, str] = {}
    for service in data["services"].values():
        for volume in service.get("volumes", []) or []:
            if not isinstance(volume, str) or ":" not in volume:
                continue
            source, _, rest = volume.partition(":")
            dest, _, mode = rest.partition(":")
            if mode == "ro":
                out[dest] = source.removeprefix("./")
    assert len(out) >= 5, f"compose mount parse collapsed: {out}"
    return out


def _arg_from_compose(flag: str) -> str | None:
    data = yaml.safe_load(COMPOSE.read_text(encoding="utf-8"))
    for service in data["services"].values():
        for arg in service.get("command", []) or []:
            text = str(arg)
            if text.startswith(f"{flag}="):
                return text.split("=", 1)[1]
    return None


def _relative(path: Path) -> str:
    return path.relative_to(ROOT).as_posix()


# ────────────────────────────────────────────────────────── R13 ───────────────────────────
def test_the_threshold_gate_and_this_gate_agree_on_what_a_probe_is() -> None:
    """#219 exempts rules from the THRESHOLDS pairing by name. That exemption
    is a hiding place if it can hold anything, so this gate re-derives the
    same list from the exprs: the two must be equal, in both directions."""
    declared = _declared_liveness_names()
    derived = set(_probes().values())
    assert declared == derived, (
        f"#219 exempts {sorted(derived - declared)} which this gate does not "
        f"recognise as a probe, and misses {sorted(declared - derived)} which "
        f"is one"
    )


def _declared_liveness_names() -> set[str]:
    source = GATE_219.read_text(encoding="utf-8")
    block = re.search(r"_LIVENESS_RULES = \{(?P<body>[^}]*)\}", source)
    assert block is not None, "could not find #219's _LIVENESS_RULES declaration"
    names = set(re.findall(r'"([A-Za-z0-9_]+)"', block.group("body")))
    assert len(names) >= 4, f"#219's liveness exemption list collapsed: {sorted(names)}"
    return names

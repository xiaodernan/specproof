"""Provider Smoke Run — real gateway connectivity and code-generation validation.

Reads credentials from .env, never prints the API key.
Must pass ALL critical stages to count as PASS.
"""

import asyncio
import hashlib
import json
import os
import re
import subprocess
import sys
import tempfile
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from providers.base import LLMMessage
from providers.capability_probe import CapabilityProbe
from providers.openai_compatible import OpenAICompatibleProvider

# ── Stage 0: Locate project root and load .env ──────────────────────
PROJECT = Path(__file__).resolve().parents[1]
ENV_PATHS = [
    PROJECT / ".env",
    Path("D:/experim/specproof-phase0/.env"),
    Path("D:/experim/.env"),
    PROJECT.parent / "specproof-phase0" / ".env",
    Path(os.getcwd()) / ".env",
]


def _load_dotenv(path: Path) -> dict[str, str]:
    out: dict[str, str] = {}
    if not path.exists():
        return out
    for line in path.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        k, _, v = line.partition("=")
        k = k.strip()
        v = v.strip().strip('"').strip("'")
        out[k] = v
    return out


_env: dict[str, str] = {}
for p in ENV_PATHS:
    _env.update(_load_dotenv(p))

BASE_URL = _env.get("LLM_BASE_URL", os.environ.get("LLM_BASE_URL", ""))
API_KEY = _env.get("LLM_API_KEY", os.environ.get("LLM_API_KEY", ""))
MODEL = _env.get("LLM_MODEL", os.environ.get("LLM_MODEL", ""))

# ── Report helpers ───────────────────────────────────────────────────

TIMESTAMP = datetime.now(UTC).strftime("%Y%m%dT%H%M%SZ")
RUN_ID = f"provider-smoke-{TIMESTAMP}"
REPORT: dict[str, Any] = {
    "run_id": RUN_ID,
    "timestamp": datetime.now(UTC).isoformat(),
    "provider_type": "openai_compatible",
    "model": MODEL,
    "endpoint_base_url": BASE_URL.rstrip("/") if BASE_URL else "(not set)",
    "stages": {},
    "verdict": "PENDING",
}

_RED = "\033[91m"
_GRN = "\033[92m"
_YEL = "\033[93m"
_RST = "\033[0m"


def _mask(s: str, keep: int = 6) -> str:
    if len(s) <= keep + keep:
        return "*" * len(s)
    return s[:keep] + "*" * (len(s) - keep - keep) + s[-keep:]


def _stage(name: str) -> None:
    print(f"\n{'─' * 60}")
    print(f"  STAGE: {name}")
    print(f"{'─' * 60}")


def _p(name: str, detail: str = "") -> None:
    REPORT["stages"][name] = {"result": "PASS", "detail": detail}
    print(f"  {_GRN}PASS{_RST}  {name}" + (f" — {detail}" if detail else ""))


def _f(name: str, detail: str) -> None:
    REPORT["stages"][name] = {"result": "FAIL", "detail": detail}
    print(f"  {_RED}FAIL{_RST}  {name} — {detail}")


def _w(name: str, detail: str) -> None:
    REPORT["stages"][name] = {"result": "WARN", "detail": detail}
    print(f"  {_YEL}WARN{_RST}  {name} — {detail}")


def _digest(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest() if path.exists() else "missing"


def _scan_text_for_key(text: str, key_prefix: str) -> list[str]:
    """Simple inline secret scan — checks if any part of the API key is in text."""
    findings: list[str] = []
    # Check for key-like patterns
    for pattern in [r"sk-[a-zA-Z0-9]{20,}", r"sk-[a-zA-Z0-9]{48}", r"Bearer [a-zA-Z0-9\-_]{20,}"]:
        for m in re.finditer(pattern, text):
            findings.append(m.group())
    # Direct substring check of key (with minimum 8 char segments)
    if len(key_prefix) >= 8:
        for i in range(0, len(key_prefix) - 8):
            segment = key_prefix[i : i + 16]
            if len(segment) >= 12 and segment in text:
                findings.append(f"key_segment_match_at_offset_{i}")
    return findings


# ══════════════════════════════════════════════════════════════════════
# Stage 1: Provider connectivity and capability probe
# ══════════════════════════════════════════════════════════════════════

_stage("1-Provider-Probe")

if not BASE_URL or not API_KEY:
    _f("1-env", "LLM_BASE_URL or LLM_API_KEY not set in .env or environment")
    REPORT["verdict"] = "FAIL"
    json.dump(REPORT, sys.stdout, indent=2, ensure_ascii=False)
    sys.exit(1)

print(f"  Base URL : {BASE_URL}")
print(f"  Model    : {MODEL}")
print(f"  API Key  : {_mask(API_KEY)} (masked, never printed)")

_probe = CapabilityProbe(base_url=BASE_URL, api_key=API_KEY, model=MODEL)
_probe_result = asyncio.run(_probe.run())

_n_passed = sum(1 for v in _probe_result.capabilities.values() if v)
_n_total = len(_probe_result.capabilities)
print(f"  Capabilities: {_n_passed}/{_n_total} passed")
for name, val in _probe_result.capabilities.items():
    flag = _GRN + "PASS" + _RST if val else _RED + "FAIL" + _RST
    print(f"    [{flag}] {name}")

REPORT["capability_matrix"] = dict(_probe_result.capabilities)

if _n_passed == 0:
    _f("1-probe", f"0/{_n_total} capabilities — gateway unreachable or misconfigured")
    REPORT["verdict"] = "FAIL"
    json.dump(REPORT, sys.stdout, indent=2, ensure_ascii=False)
    sys.exit(1)

_pct = _n_passed / max(_n_total, 1)
if _pct < 0.4:
    _w("1-probe", f"{_n_passed}/{_n_total} — low capability count")
else:
    _p("1-probe", f"{_n_passed}/{_n_total} capabilities")

for e in _probe_result.errors:
    print(f"    Probe error: {e}")


# ══════════════════════════════════════════════════════════════════════
# Stage 2: Non-thinking chat (basic completion)
# ══════════════════════════════════════════════════════════════════════

_stage("2-NonThinking-Chat")

provider = OpenAICompatibleProvider(
    base_url=BASE_URL, api_key=API_KEY, model=MODEL, probe_on_init=False
)


async def _do_chat() -> tuple[str, dict[str, Any]]:
    resp = await provider.chat(
        messages=[LLMMessage(role="user", content='Reply with exactly: {"status":"ok"}')],
        timeout=60.0,
    )
    return (resp.content or ""), resp.usage if isinstance(resp.usage, dict) else {}


chat_content, chat_usage = asyncio.run(_do_chat())
if not chat_content.strip():
    _f("2-chat", "empty response from provider")
else:
    print(f"  Response length: {len(chat_content)} chars")
    print(f"  Usage: {chat_usage}")
    REPORT["chat_usage"] = chat_usage
    _p("2-chat", f"{len(chat_content)} chars, ~{chat_usage.get('total_tokens', '?')} tokens")


# ══════════════════════════════════════════════════════════════════════
# Stage 3: Structured JSON response
# ══════════════════════════════════════════════════════════════════════

_stage("3-Structured-JSON")

_JSON_PROMPT = """You are a JSON-only API. Return a JSON object with exactly these fields:
{
  "finding_id": "SMOKE-001",
  "severity": "BLOCKER",
  "type": "annotation_removed",
  "description": "@PreAuthorize removed from changeEmail method",
  "confidence": 0.95
}
Output ONLY the JSON object, no markdown, no explanation."""


async def _do_json() -> str:
    resp = await provider.chat(
        messages=[LLMMessage(role="user", content=_JSON_PROMPT)],
        timeout=60.0,
    )
    return resp.content or ""


json_raw = asyncio.run(_do_json())
json_clean = json_raw.strip()
for fence in ("```json", "```"):
    json_clean = json_clean.removeprefix(fence).removesuffix(fence).strip()

try:
    parsed = json.loads(json_clean)
    required = ["finding_id", "severity", "type", "description", "confidence"]
    missing = [k for k in required if k not in parsed]
    if missing:
        _f("3-json", f"missing fields: {missing}")
    else:
        print(f"  Parsed: {json.dumps(parsed, indent=2)}")
        _p("3-json", f"valid JSON with {len(parsed)} fields")
except json.JSONDecodeError as e:
    _f("3-json", f"not valid JSON: {e}")
    print(f"  Raw (first 300 chars): {json_raw[:300]}")


# ══════════════════════════════════════════════════════════════════════
# Stage 4: JUnit code generation
# ══════════════════════════════════════════════════════════════════════

_stage("4-JUnit-Generation")

_JUNIT_PROMPT = (
    "You are a Java test engineer. Generate a complete JUnit 5 test class for a Spring Boot\n"
    "controller. The test must:\n"
    "\n"
    "1. Be a valid @SpringBootTest with @AutoConfigureMockMvc\n"
    "2. Test a PUT endpoint /api/users/{id}/email that changes a user's email\n"
    "3. Expect HTTP 401 Unauthorized when no auth is provided\n"
    "4. Use MockMvc for the HTTP call\n"
    "5. Include all necessary imports\n"
    "6. Package: com.specproof.demo\n"
    "7. Class name: SpecProofGeneratedTest\n"
    "\n"
    "Output ONLY the Java code, no markdown fences, no explanation."
)


async def _do_gen_junit() -> str:
    resp = await provider.chat(
        messages=[LLMMessage(role="user", content=_JUNIT_PROMPT)],
        timeout=120.0,
    )
    return resp.content or ""


junit_code = asyncio.run(_do_gen_junit())
junit_code = junit_code.strip()
for fence in ("```java", "```"):
    junit_code = junit_code.removeprefix(fence).removesuffix(fence).strip()

checks = {
    "has_@Test": "@Test" in junit_code,
    "has_class": "class SpecProofGeneratedTest" in junit_code,
    "has_@SpringBootTest": "@SpringBootTest" in junit_code,
    "has_MockMvc": "MockMvc" in junit_code,
    "has_401_or_Unauthorized": (
        "401" in junit_code or "isUnauthorized" in junit_code or "UNAUTHORIZED" in junit_code
    ),
    "has_package": "package com.specproof.demo" in junit_code,
    "has_imports": "import " in junit_code,
}

all_checks = all(checks.values())
print(f"  Schema checks: {json.dumps(checks, indent=4)}")
REPORT["junit_schema_checks"] = checks

if not all_checks:
    _f("4-junit-gen", f"missing: {[k for k, v in checks.items() if not v]}")
else:
    _p("4-junit-gen", f"all {len(checks)} schema checks passed")

REPORT["generated_test_source_digest"] = hashlib.sha256(junit_code.encode()).hexdigest()
print(f"  Source digest: {REPORT['generated_test_source_digest'][:32]}...")


# ══════════════════════════════════════════════════════════════════════
# Stage 5: Write + Maven compile
# ══════════════════════════════════════════════════════════════════════

_stage("5-Maven-Compile")

DEMO_DIR = PROJECT / "demo" / "spring-backend"
TEST_DIR = DEMO_DIR / "src" / "test" / "java" / "com" / "specproof" / "demo"
TEST_DIR.mkdir(parents=True, exist_ok=True)
TEST_FILE = TEST_DIR / "SpecProofGeneratedTest.java"
TEST_FILE.write_text(junit_code, encoding="utf-8")
print(f"  Written to: {TEST_FILE}")

compile_ok = False
if not DEMO_DIR.exists():
    _f("5-compile", f"demo dir not found: {DEMO_DIR}")
else:
    is_win = sys.platform == "win32"
    mvnw_full = str(DEMO_DIR / ("mvnw.cmd" if is_win else "mvnw"))
    java_home = os.environ.get("JAVA_HOME", "")
    if not java_home:
        _f("5-compile", "JAVA_HOME not set — cannot run Maven")
    else:
        env_mvn = os.environ.copy()
        compile_result = subprocess.run(
            [mvnw_full, "test-compile", "-q"],
            cwd=str(DEMO_DIR),
            capture_output=True,
            text=True,
            timeout=300,
            env=env_mvn,
        )
        REPORT["compile_exit_code"] = compile_result.returncode
        REPORT["compile_stderr_tail"] = (
            compile_result.stderr[-500:] if compile_result.stderr else ""
        )
        if compile_result.returncode == 0:
            compile_ok = True
            _p("5-compile", f"exit {compile_result.returncode}")
            target_classes = list(
                (DEMO_DIR / "target" / "test-classes").rglob("SpecProofGeneratedTest.class")
            )
            print(f"  .class files found: {len(target_classes)}")
        else:
            _f("5-compile", f"exit {compile_result.returncode}")
            print(f"  stderr tail: {compile_result.stderr[-400:]}")


# ══════════════════════════════════════════════════════════════════════
# Stage 6: Secret Scanner
# ══════════════════════════════════════════════════════════════════════

_stage("6-Secret-Scan")

key_findings = _scan_text_for_key(junit_code, API_KEY)
# Also scan with agent security_scanner module if possible
scanner_findings: list[str] = []
try:
    from agent.security_scanner import scan_directory

    with tempfile.TemporaryDirectory(prefix="smoke-scan-") as tmpd:
        tmpfile = Path(tmpd) / "SpecProofGeneratedTest.java"
        tmpfile.write_text(junit_code, encoding="utf-8")
        scan_result = scan_directory(tmpd)
        scanner_findings = [f.matched_text for f in scan_result.findings]
except Exception:
    pass

all_secrets = list(set(key_findings + scanner_findings))
REPORT["secret_scan"] = {
    "source": "generated JUnit code",
    "findings_count": len(all_secrets),
    "findings": all_secrets[:10],
}

# Check for real API key leakage
key_leaked = any(
    len(API_KEY) > 8 and API_KEY[i : i + 12] in junit_code
    for i in range(0, max(len(API_KEY) - 12, 0), 4)
)

if key_leaked:
    _f("6-secret", "REAL API KEY LEAKED in generated code!")
elif all_secrets:
    _w("6-secret", f"{len(all_secrets)} pattern match(es), no real key leaked")
else:
    _p("6-secret", "no secrets in generated code")


# ══════════════════════════════════════════════════════════════════════
# Stage 7: Digest chain
# ══════════════════════════════════════════════════════════════════════

_stage("7-Digest-Chain")

REPORT["source_digest"] = {
    "provider_smoke_py": _digest(Path(__file__)),
    "openai_compatible_py": _digest(PROJECT / "providers" / "openai_compatible.py"),
    "capability_probe_py": _digest(PROJECT / "providers" / "capability_probe.py"),
    "generated_junit": REPORT["generated_test_source_digest"],
}
print(f"  Digests: {json.dumps(REPORT['source_digest'], indent=2)}")
hashed_count = sum(1 for v in REPORT["source_digest"].values() if v != "missing")
_p("7-digests", f"{hashed_count}/{len(REPORT['source_digest'])} hashed")


# ══════════════════════════════════════════════════════════════════════
# Final verdict
# ══════════════════════════════════════════════════════════════════════

_stage("VERDICT")

all_stages = REPORT["stages"]
failed = [k for k, v in all_stages.items() if v["result"] == "FAIL"]
warned = [k for k, v in all_stages.items() if v["result"] == "WARN"]

if failed:
    REPORT["verdict"] = "FAIL"
    print(f"\n  {_RED}FAIL{_RST} — {len(failed)} stage(s) failed: {failed}")
elif _n_passed == 0:
    REPORT["verdict"] = "FAIL"
    print(f"\n  {_RED}FAIL{_RST} — 0/{_n_total} capabilities, cannot certify")
elif not compile_ok:
    REPORT["verdict"] = "FAIL"
    print(f"\n  {_RED}FAIL{_RST} — Maven compile failed")
else:
    REPORT["verdict"] = "PASS"
    print(f"\n  {_GRN}PASS{_RST} — all critical stages passed")

# ── Write report ─────────────────────────────────────────────────────

REPORT_DIR = PROJECT / "artifacts" / "p0.5" / RUN_ID
REPORT_DIR.mkdir(parents=True, exist_ok=True)
REPORT_FILE = REPORT_DIR / "provider-smoke-report.json"
REPORT_FILE.write_text(
    json.dumps(REPORT, indent=2, ensure_ascii=False, default=str), encoding="utf-8"
)
print(f"\n  Report written to: {REPORT_FILE}")

print(f"\n{'=' * 60}")
print(f"  Run ID  : {RUN_ID}")
print(f"  Provider: openai_compatible | Model: {MODEL}")
print(f"  Endpoint: {BASE_URL}")
print(f"  Verdict : {REPORT['verdict']}")
print(f"{'=' * 60}")

sys.exit(0 if REPORT["verdict"] == "PASS" else 1)

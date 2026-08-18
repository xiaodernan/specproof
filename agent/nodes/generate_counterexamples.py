"""generate_counterexamples node — generate a JUnit counterexample test.

v2 honesty fixes:
- The generated test is a SINGLE test method: unauthenticated PUT must
  return 401 AND leave the DB row unchanged (andReturn + assertAll —
  no short-circuit).
- run_differential injects the same test into BOTH workspaces before
  running it, so base_pass_head_fail means what it says.
- The deterministic fallback template supports only the demo repository
  (com.specproof). For any other repo it fails honestly instead of
  pretending to work.
- LLM failures are recorded in the generation record, never swallowed.
"""
from __future__ import annotations

import asyncio
import os
import re
import textwrap
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from agent.state import Phase0State

# ── Test source tracking ──────────────────────────────────────────
TestSource = str  # "llm_generated" | "deterministic_template" | "human_fixture"

# ── JSON Schema for LLM-generated test validation ─────────────────
_TEST_SCHEMA_REQUIRED = [
    "import org.junit.jupiter.api.Test",
    "class ",
    "@Test",
    "MockMvc",
]

# ── LLM prompt for JUnit generation (non-thinking mode) ───────────

_JUNIT_GENERATION_PROMPT = """You are a Java security test engineer. Generate a JUnit 5 test class
for a Spring Boot application that verifies a security regression.

CONTEXT:
A PR removed an authorization guard (e.g. @PreAuthorize) from a mutating
endpoint. Unauthenticated requests must be rejected with 401 and must not
modify database state.

REQUIREMENTS:
1. Use @SpringBootTest + @AutoConfigureMockMvc + @ActiveProfiles("test")
2. Import TestMockBeansConfig with @Import
3. Inject MockMvc and UserRepository
4. In @BeforeEach, clean DB and create a test user
5. Write ONE test that sends an UNAUTHENTICATED PUT to the endpoint
6. Use andReturn() and assertAll(): status must be 401/403 AND the DB row
   must be unchanged afterwards (no short-circuit — both assertions run)
7. Full package: com.specproof.demo
8. Class name: SpecProofGeneratedTest

Return ONLY the Java source code. No markdown fences, no explanation."""


@dataclass
class GenerationResult:
    """Result of one test generation attempt."""
    source: TestSource
    code: str = ""
    compile_exit_code: int = -1
    compile_stderr: str = ""
    attempt: int = 0


@dataclass
class TestGenerationRecord:
    """Full record of test generation for evidence tracking."""
    source: TestSource = "deterministic_template"
    attempts: int = 0
    llm_code: str = ""
    final_code: str = ""
    compile_passed: bool = False
    test_path: str = ""
    errors: list[str] = field(default_factory=list)


def _get_provider() -> Any:
    """Create an LLM provider from env vars. Returns None if not configured."""
    api_key = os.getenv("LLM_API_KEY", "")
    if not api_key or api_key == "replace_me":
        return None
    try:
        from providers.openai_compatible import OpenAICompatibleProvider
        return OpenAICompatibleProvider(probe_on_init=False)
    except Exception:
        return None


def _validate_test_schema(code: str) -> list[str]:
    """Validate generated test code against required schema elements."""
    missing = []
    for required in _TEST_SCHEMA_REQUIRED:
        if required not in code:
            missing.append(required)
    return missing


def _compile_test(workspace: str, test_file: str) -> tuple[int, str]:
    """Compile the test class with mvnw test-compile. Returns (exit_code, stderr).

    P0-A1: the compile runs inside the execution SANDBOX (sandbox/runner.py) —
    a malicious pom.xml/build plugin must never execute on the host.
    """
    del test_file  # path validated by the caller; compilation covers the tree
    pom = Path(workspace) / "pom.xml"
    if not pom.exists():
        return -1, "No pom.xml found"

    import platform

    from sandbox.runner import run_sandboxed

    # Sandbox runs the image's mvn; the local fallback uses the wrapper
    # (absolute path — CreateProcessW resolves relative names against the
    # parent cwd, not cwd=).
    if platform.system() == "Windows":
        local_cmd = [os.path.join(workspace, "mvnw.cmd"), "test-compile", "-q"]
    else:
        local_cmd = [os.path.join(workspace, "mvnw"), "test-compile", "-q"]
    result = run_sandboxed(
        ["mvn", "test-compile", "-q", "-f", "/work/pom.xml"],
        workspace=workspace,
        timeout=600,
        local_command=local_cmd,
    )
    if result.error:
        return -1, "Sandbox execution failed: " + result.error
    return result.exit_code, result.stderr


def _is_demo_repo(workspace: str) -> bool:
    """The deterministic template only supports the demo repository."""
    pom = Path(workspace) / "pom.xml"
    if not pom.exists():
        return False
    try:
        return "com.specproof" in pom.read_text(encoding="utf-8")
    except OSError:
        return False


async def _llm_generate_junit(
    findings: list[dict[str, Any]],
    contracts: list[dict[str, Any]],
    requirement_text: str = "",
) -> str:
    """Call LLM with non-thinking mode to generate JUnit test code."""
    from providers.base import LLMMessage

    provider = _get_provider()
    if provider is None:
        raise RuntimeError("No LLM provider available")

    findings_desc = "\n".join(
        f"- [{f.get('severity', 'UNKNOWN')}] {f.get('type')}: {f.get('description', '')}"
        for f in findings[:10]
    ) if findings else "No findings available"

    contracts_desc = "\n".join(
        f"- {c.get('id', '?')}: {c.get('expected_behavior', c.get('description', ''))}"
        for c in contracts[:10]
    ) if contracts else "No contracts available"

    full_prompt = _JUNIT_GENERATION_PROMPT + "\n\nADDITIONAL CONTEXT:\n"
    full_prompt += f"Requirement: {requirement_text[:500]}\n\n" if requirement_text else ""
    full_prompt += f"Findings:\n{findings_desc}\n\n"
    full_prompt += f"Contracts:\n{contracts_desc}\n"

    response = await provider.chat(
        messages=[LLMMessage(role="user", content=full_prompt)],
        thinking=False,  # P0.5 requirement: non-thinking for JUnit generation
        timeout=120.0,
    )

    content = response.content or ""

    code = content
    if "```java" in code:
        m = re.search(r"```java\s*\n(.*?)```", code, re.DOTALL)
        if m:
            code = m.group(1).strip()
    elif "```" in code:
        m = re.search(r"```\s*\n(.*?)```", code, re.DOTALL)
        if m:
            code = m.group(1).strip()

    return code


_GENERATED_TEST_HEADER = """\
package com.specproof.demo;

import com.fasterxml.jackson.databind.ObjectMapper;
import com.specproof.demo.config.TestMockBeansConfig;
import com.specproof.demo.dto.ChangeEmailRequest;
import com.specproof.demo.entity.User;
import com.specproof.demo.repository.UserRepository;
import jakarta.servlet.ServletException;
import org.junit.jupiter.api.BeforeEach;
import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.autoconfigure.web.servlet.AutoConfigureMockMvc;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.context.annotation.Import;
import org.springframework.http.MediaType;
import org.springframework.security.test.context.support.WithMockUser;
import org.springframework.test.context.ActiveProfiles;
import org.springframework.test.web.servlet.MockMvc;
import org.springframework.test.web.servlet.MvcResult;

import static org.junit.jupiter.api.Assertions.assertAll;
import static org.junit.jupiter.api.Assertions.assertEquals;
import static org.junit.jupiter.api.Assertions.assertTrue;
import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.put;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.status;

@SpringBootTest
@AutoConfigureMockMvc
@ActiveProfiles("test")
@Import(TestMockBeansConfig.class)
public class SpecProofGeneratedTest {

    @Autowired
    private MockMvc mockMvc;

    @Autowired
    private UserRepository userRepository;

    @Autowired
    private ObjectMapper objectMapper;

    @BeforeEach
    void setUp() {
        userRepository.deleteAll();
        User user = new User("specproof", "specproof@example.com");
        user.setPasswordHash("hash");
        userRepository.save(user);
    }

"""

_AUTH_TEST_TEMPLATE = """    @Test
    void unauthenticatedEmailChangeMustBeRejected() throws Exception {
        User user = userRepository.findAll().get(0);
        String emailBefore = user.getEmail();
        ChangeEmailRequest req = new ChangeEmailRequest("attacker@evil.com");

        MvcResult result = mockMvc.perform(put("/api/users/" + "{id}" + "/email", user.getId())
                        .contentType(MediaType.APPLICATION_JSON)
                        .content(objectMapper.writeValueAsString(req)))
                .andReturn();

        int status = result.getResponse().getStatus();
        String emailAfter = userRepository.findById(user.getId())
                .map(User::getEmail).orElse("NOT_FOUND");

        assertAll(
            () -> assertEquals(401, status,
                "Expected 401 UNAUTHORIZED but got " + status),
            () -> assertEquals(emailBefore, emailAfter,
                "DB STATE VIOLATION: email was '" + emailBefore
                + "' before request, now '" + emailAfter
                + "'. Unauthenticated requests must not modify data.")
        );
    }

"""

_FRESH_TEST_TEMPLATE = """    @Test
    @WithMockUser
    void freshEmailChangeMustSucceed() throws Exception {
        User user = userRepository.findAll().get(0);
        ChangeEmailRequest req = new ChangeEmailRequest("fresh@example.com");

        mockMvc.perform(put("/api/users/" + "{id}" + "/email", user.getId())
                        .contentType(MediaType.APPLICATION_JSON)
                        .content(objectMapper.writeValueAsString(req)))
                .andExpect(status().isOk());
    }

"""

_UNIQUE_TEST_TEMPLATE = """    @Test
    @WithMockUser
    void duplicateEmailChangeMustBeRejected() throws Exception {
        User alice = new User("alice", "alice@example.com");
        alice.setPasswordHash("hash");
        // Explicit flush: the duplicate must be visible to the derived
        // existsByEmail query even when the test-managed transaction has
        // not committed yet.
        userRepository.saveAndFlush(alice);

        User bob = userRepository.findAll().stream()
                .filter(u -> "specproof@example.com".equals(u.getEmail()))
                .findFirst().orElseThrow();
        ChangeEmailRequest req = new ChangeEmailRequest("alice@example.com");

        // MockMvc RETHROWS unhandled controller exceptions out of
        // perform() (the demo app has no global exception handler) — the
        // duplicate rejection surfaces exactly this way.
        final boolean[] rejected = {false};
        try {
            mockMvc.perform(put("/api/users/" + "{id}" + "/email", bob.getId())
                            .contentType(MediaType.APPLICATION_JSON)
                            .content(objectMapper.writeValueAsString(req)));
        } catch (ServletException e) {
            rejected[0] = e.getCause() instanceof RuntimeException;
        }

        String emailAfter = userRepository.findById(bob.getId())
                .map(User::getEmail).orElse("NOT_FOUND");
        assertAll(
            () -> assertTrue(rejected[0],
                "Duplicate email was ACCEPTED: no rejection exception "
                + "was raised"),
            () -> assertEquals("specproof@example.com", emailAfter,
                "DB STATE VIOLATION: duplicate email change was accepted "
                + "and persisted")
        );
    }

"""


def _build_deterministic_test(contracts: list[dict[str, Any]]) -> str:
    """Deterministic differential tests for the demo repository.

    Always: unauthenticated PUT -> 401 AND DB row unchanged (AUTH family).
    When a UNIQUE contract is compiled: the duplicate-email rejection
    test — the static tier can only see REMOVED guards, so inverted-guard
    regressions (case-17) are only catchable by EXECUTING the behaviour.
    """
    body = _AUTH_TEST_TEMPLATE
    if _has_unique_contract(contracts):
        # The duplicate-rejection test catches guard REMOVALS; the
        # fresh-email test catches guard INVERSIONS (case-17): an inverted
        # guard rejects unused emails, which only execution can reveal.
        body += _UNIQUE_TEST_TEMPLATE + _FRESH_TEST_TEMPLATE
    return textwrap.dedent(_GENERATED_TEST_HEADER + body + "}\n")


def _has_unique_contract(contracts: list[dict[str, Any]]) -> bool:
    """True when any compiled contract guards email uniqueness."""
    for contract in contracts:
        if contract.get("id") == "UNIQUE-01":
            return True
        behavior = str(contract.get("expected_behavior", "")).lower()
        requirement = str(contract.get("requirement", "")).lower()
        if "unique" in behavior or "duplicate" in requirement:
            return True
    return False


async def _generate_with_compile_loop(
    head_workspace: str,
    findings: list[dict[str, Any]],
    contracts: list[dict[str, Any]],
    requirement_text: str,
) -> GenerationResult:
    """LLM generate → validate schema → compile, retry up to 3 times."""
    max_retries = 3
    test_dir = (
        Path(head_workspace) / "src" / "test" / "java"
        / "com" / "specproof" / "demo"
    )
    test_dir.mkdir(parents=True, exist_ok=True)
    test_file = test_dir / "SpecProofGeneratedTest.java"

    provider = _get_provider()
    if provider is None:
        return GenerationResult(
            source="deterministic_template",
            code="",
            compile_exit_code=-1,
            compile_stderr="No LLM provider configured",
            attempt=0,
        )

    last_code = ""
    last_stderr = ""
    last_exit = -1
    for attempt in range(1, max_retries + 1):
        try:
            code = await _llm_generate_junit(findings, contracts, requirement_text)
            last_code = code
        except Exception as exc:  # noqa: BLE001
            last_stderr = f"LLM call failed (attempt {attempt}): {exc}"
            continue

        missing = _validate_test_schema(code)
        if missing:
            last_stderr = f"Schema validation failed: missing {missing}"
            continue

        test_file.write_text(code, encoding="utf-8")
        exit_code, stderr = _compile_test(head_workspace, str(test_file))
        last_exit = exit_code
        last_stderr = stderr

        if exit_code == 0:
            return GenerationResult(
                source="llm_generated",
                code=code,
                compile_exit_code=0,
                compile_stderr="",
                attempt=attempt,
            )

        findings.append({
            "severity": "ERROR",
            "type": "compile_error",
            "description": f"Compilation failed (attempt {attempt}): {stderr[:500]}",
        })

    return GenerationResult(
        source="llm_generated",
        code=last_code,
        compile_exit_code=last_exit,
        compile_stderr=last_stderr or "All retries exhausted",
        attempt=max_retries,
    )


def generate_counterexamples_node(state: Phase0State) -> dict[str, Any]:
    """Generate a JUnit counterexample test based on findings.

    Returns state updates including test_source, generation_record,
    and generated_tests_path. The test is injected into BOTH workspaces
    later, by run_differential.
    """
    static_findings = state.get("static_findings", [])
    confirmed_findings = state.get("confirmed_findings", [])
    contracts = state.get("contracts", [])
    requirement_text = state.get("requirement_text", "")
    head_workspace = state.get("head_workspace", "")
    app_dir = state.get("app_dir", "")
    all_findings = static_findings + confirmed_findings

    record = TestGenerationRecord()

    if not head_workspace:
        record.errors.append("No head workspace — cannot generate tests")
        return {
            "generated_tests_path": "",
            "generation_record": {
                "source": record.source,
                "attempts": 0,
                "compile_passed": False,
                "errors": record.errors,
            },
        }

    app_workspace = (
        str(Path(head_workspace) / app_dir) if app_dir else head_workspace
    )
    test_dir = (
        Path(app_workspace) / "src" / "test" / "java"
        / "com" / "specproof" / "demo"
    )
    test_dir.mkdir(parents=True, exist_ok=True)
    test_file = test_dir / "SpecProofGeneratedTest.java"

    # ── Phase 1: Attempt LLM generation ──
    provider = _get_provider() if state.get("use_llm", True) else None
    if provider is not None:
        try:
            loop = asyncio.get_event_loop()
            if loop.is_running():
                import concurrent.futures
                with concurrent.futures.ThreadPoolExecutor() as pool:
                    future = pool.submit(
                        asyncio.run,
                        _generate_with_compile_loop(
                            head_workspace, all_findings or static_findings,
                            contracts, requirement_text,
                        ),
                    )
                    gen_result = future.result(timeout=300)
            else:
                gen_result = asyncio.run(
                    _generate_with_compile_loop(
                        app_workspace, all_findings or static_findings,
                        contracts, requirement_text,
                    )
                )
        except Exception as exc:  # noqa: BLE001
            gen_result = GenerationResult(
                source="deterministic_template",
                compile_exit_code=-1,
                compile_stderr=str(exc),
                attempt=0,
            )
    else:
        gen_result = GenerationResult(
            source="deterministic_template",
            compile_exit_code=-1,
            compile_stderr="No LLM provider configured",
            attempt=0,
        )

    # ── Phase 2: Fall back to deterministic template if LLM failed ──
    if gen_result.source == "llm_generated" and gen_result.compile_exit_code == 0:
        record.source = "llm_generated"
        record.llm_code = gen_result.code
        record.final_code = gen_result.code
        record.compile_passed = True
        record.attempts = gen_result.attempt
    else:
        record.source = "deterministic_template"
        record.attempts = gen_result.attempt
        if gen_result.compile_stderr:
            record.errors.append(
                f"LLM generation failed: {gen_result.compile_stderr}"
            )

        if not _is_demo_repo(app_workspace):
            record.errors.append(
                "Deterministic template only supports the demo repository "
                "(com.specproof); LLM generation also failed. "
                "No counterexample test produced."
            )
            return {
                "generated_tests_path": "",
                "generation_record": {
                    "source": record.source,
                    "attempts": record.attempts,
                    "compile_passed": False,
                    "test_path": "",
                    "errors": record.errors,
                    "llm_code_len": len(record.llm_code),
                },
            }

        fallback_code = _build_deterministic_test(contracts)
        record.final_code = fallback_code
        test_file.write_text(fallback_code, encoding="utf-8")

        exit_code, stderr = _compile_test(app_workspace, str(test_file))
        record.compile_passed = exit_code == 0
        if not record.compile_passed:
            record.errors.append(f"Fallback template compile failed: {stderr[:500]}")

    record.test_path = str(test_file)

    return {
        "generated_tests_path": record.test_path,
        "generation_record": {
            "source": record.source,
            "attempts": record.attempts,
            "compile_passed": record.compile_passed,
            "test_path": record.test_path,
            "errors": record.errors,
            "llm_code_len": len(record.llm_code),
        },
    }

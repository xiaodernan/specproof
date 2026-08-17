"""generate_counterexamples node — LLM-generated JUnit tests targeting regressions.

P0.5: Real LLM generation with non-thinking mode, compile verification,
3-retry loop, test source tracking, and DB state verification.
"""

from __future__ import annotations

import asyncio
import json
import os
import re
import subprocess
import textwrap
from dataclasses import dataclass, field
from pathlib import Path

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
for a Spring Boot application that verifies security regression.

CONTEXT:
The PR removed @PreAuthorize("isAuthenticated()") from a PUT /api/users/{id}/email endpoint.
This means unauthenticated requests can now change user emails — a security regression.

REQUIREMENTS:
1. Use @SpringBootTest + @AutoConfigureMockMvc + @ActiveProfiles("test")
2. Import TestMockBeansConfig with @Import
3. Inject MockMvc and UserRepository
4. In @BeforeEach, clean DB and create a test user
5. Write a test that sends an UNAUTHENTICATED PUT request to /api/users/{id}/email
6. Verify the HTTP status is 401/403 (UNAUTHORIZED/FORBIDDEN)
7. ALSO verify database state: the user's email was NOT changed
8. Include a second test with @WithMockUser that verifies authenticated requests work (200 OK)

IMPORTANT:
- Use MockMvc.perform() with status().isUnauthorized() for unauthenticated
- Use MockMvc.perform() with status().isOk() for authenticated
- Check DB state: userRepository.findById(id).getEmail() before and after
- Full package: com.specproof.demo
- Class name: SpecProofSecurityRegressionTest

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


def _get_provider():
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
    """Validate generated test code against required schema elements.

    Returns a list of missing required elements (empty = valid).
    """
    missing = []
    for required in _TEST_SCHEMA_REQUIRED:
        if required not in code:
            missing.append(required)
    return missing


def _compile_test(workspace: str, test_file: str) -> tuple[int, str]:
    """Compile the test class with mvnw test-compile. Returns (exit_code, stderr)."""
    pom = Path(workspace) / "pom.xml"
    if not pom.exists():
        return -1, "No pom.xml found"

    import platform
    mvnw_cmd = "mvnw.cmd" if platform.system() == "Windows" else "./mvnw"

    try:
        proc = subprocess.run(
            [mvnw_cmd, "test-compile", "-q"],
            cwd=workspace,
            capture_output=True, text=True, timeout=180,
        )
        return proc.returncode, proc.stderr
    except FileNotFoundError:
        try:
            proc = subprocess.run(
                ["mvn", "test-compile", "-q"],
                cwd=workspace,
                capture_output=True, text=True, timeout=180,
            )
            return proc.returncode, proc.stderr
        except FileNotFoundError:
            return -1, "Maven not found"
        except Exception as e:
            return -1, str(e)
    except Exception as e:
        return -1, str(e)


async def _llm_generate_junit(
    findings: list[dict],
    contracts: list[dict],
    requirement_text: str = "",
) -> str:
    """Call LLM with non-thinking mode to generate JUnit test code."""
    from providers.base import LLMMessage

    provider = _get_provider()
    if provider is None:
        raise RuntimeError("No LLM provider available")

    # Build context from findings and contracts
    findings_desc = "\n".join(
        f"- [{f.get('severity', 'UNKNOWN')}] {f.get('type')}: {f.get('description', '')}"
        for f in findings[:10]
    ) if findings else "No findings available"

    contracts_desc = "\n".join(
        f"- {c.get('id', '?')}: {c.get('description', c.get('name', ''))}"
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

    # Strip markdown code fences if present
    code = content
    if "```java" in code:
        m = re.search(r'```java\s*\n(.*?)```', code, re.DOTALL)
        if m:
            code = m.group(1).strip()
    elif "```" in code:
        m = re.search(r'```\s*\n(.*?)```', code, re.DOTALL)
        if m:
            code = m.group(1).strip()

    return code


def _build_deterministic_test(
    findings: list[dict],
    state: Phase0State,
) -> str:
    """Build a deterministic template-based test as fallback.

    P0.5: deterministic_template source cannot produce BLOCKER findings on its own.
    """
    return textwrap.dedent(f"""\
    package com.specproof.demo;

    import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.*;
    import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.*;

    import com.fasterxml.jackson.databind.ObjectMapper;
    import com.specproof.demo.config.TestMockBeansConfig;
    import com.specproof.demo.dto.ChangeEmailRequest;
    import com.specproof.demo.entity.User;
    import com.specproof.demo.repository.UserRepository;
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

    @SpringBootTest
    @AutoConfigureMockMvc
    @ActiveProfiles("test")
    @Import(TestMockBeansConfig.class)
    public class SpecProofGeneratedTest {{

        @Autowired
        private MockMvc mockMvc;

        @Autowired
        private UserRepository userRepository;

        @Autowired
        private ObjectMapper objectMapper;

        @BeforeEach
        void setUp() {{
            userRepository.deleteAll();
            User user = new User("specproof", "specproof@example.com");
            user.setPasswordHash("hash");
            userRepository.save(user);
        }}

        @Test
        void changeEmailWithoutAuthShouldReturn401() throws Exception {{
            User user = userRepository.findAll().get(0);
            String emailBefore = user.getEmail();
            ChangeEmailRequest req = new ChangeEmailRequest("attacker@evil.com");

            mockMvc.perform(put("/api/users/{{id}}/email", user.getId())
                            .contentType(MediaType.APPLICATION_JSON)
                            .content(objectMapper.writeValueAsString(req)))
                    .andExpect(status().isUnauthorized());

            // DB state: email must NOT have changed
            String emailAfter = userRepository.findById(user.getId())
                    .map(User::getEmail).orElse("NOT_FOUND");
            if (!emailBefore.equals(emailAfter)) {{
                throw new AssertionError(
                    "DB STATE CHANGED: email was '" + emailBefore
                    + "', now '" + emailAfter + "'. "
                    + "Unauthenticated request must not modify data.");
            }}
        }}

        @Test
        @WithMockUser
        void changeEmailWhenAuthenticatedShouldSucceed() throws Exception {{
            User user = userRepository.findAll().get(0);
            ChangeEmailRequest req = new ChangeEmailRequest("new@example.com");

            mockMvc.perform(put("/api/users/{{id}}/email", user.getId())
                            .contentType(MediaType.APPLICATION_JSON)
                            .content(objectMapper.writeValueAsString(req)))
                    .andExpect(status().isOk())
                    .andExpect(jsonPath("$.email").value("new@example.com"));
        }}
    }}
    """)


async def _generate_with_compile_loop(
    head_workspace: str,
    findings: list[dict],
    contracts: list[dict],
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

    for attempt in range(1, max_retries + 1):
        try:
            code = await _llm_generate_junit(findings, contracts, requirement_text)
        except Exception as exc:
            if attempt < max_retries:
                continue
            return GenerationResult(
                source="llm_generated",
                code="",
                compile_exit_code=-1,
                compile_stderr=f"LLM call failed after {max_retries} attempts: {exc}",
                attempt=attempt,
            )

        # Schema validation
        missing = _validate_test_schema(code)
        if missing:
            if attempt < max_retries:
                continue
            return GenerationResult(
                source="llm_generated",
                code=code,
                compile_exit_code=-1,
                compile_stderr=f"Schema validation failed: missing {missing}",
                attempt=attempt,
            )

        # Write and compile
        test_file.write_text(code, encoding="utf-8")
        exit_code, stderr = _compile_test(head_workspace, str(test_file))

        if exit_code == 0:
            return GenerationResult(
                source="llm_generated",
                code=code,
                compile_exit_code=0,
                compile_stderr="",
                attempt=attempt,
            )

        # Compile failed — retry with fix prompt
        if attempt < max_retries:
            findings.append({
                "severity": "ERROR",
                "type": "compile_error",
                "description": f"Compilation failed (attempt {attempt}): {stderr[:500]}",
            })

    # All retries exhausted
    return GenerationResult(
        source="llm_generated",
        code=code if 'code' in dir() else "",
        compile_exit_code=exit_code if 'exit_code' in dir() else -1,
        compile_stderr=stderr if 'stderr' in dir() else "All retries exhausted",
        attempt=max_retries,
    )


def generate_counterexamples_node(state: Phase0State) -> dict:
    """Generate JUnit counterexample tests based on findings.

    P0.5 behavior:
    1. Try LLM generation with non-thinking mode (up to 3 retries)
    2. Validate schema (required imports, annotations, class structure)
    3. Compile with mvnw test-compile
    4. On failure, fall back to deterministic template
    5. Track test_source: llm_generated | deterministic_template | human_fixture

    Returns state updates including test_source, generation_record,
    and generated_tests_path.
    """
    static_findings = state.get("static_findings", [])
    confirmed_findings = state.get("confirmed_findings", [])
    contracts = state.get("contracts", [])
    requirement_text = state.get("requirement_text", "")
    head_workspace = state.get("head_workspace", "")
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

    test_dir = (
        Path(head_workspace) / "src" / "test" / "java"
        / "com" / "specproof" / "demo"
    )
    test_dir.mkdir(parents=True, exist_ok=True)
    test_file = test_dir / "SpecProofGeneratedTest.java"

    # ── Phase 1: Attempt LLM generation ──
    provider = _get_provider()
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
                        head_workspace, all_findings or static_findings,
                        contracts, requirement_text,
                    )
                )
        except Exception as exc:
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
        # File already written by _generate_with_compile_loop
    else:
        # Use deterministic template fallback
        record.source = "deterministic_template"
        record.attempts = gen_result.attempt
        if gen_result.compile_stderr:
            record.errors.append(f"LLM generation failed: {gen_result.compile_stderr}")

        fallback_code = _build_deterministic_test(all_findings, state)
        record.final_code = fallback_code
        test_file.write_text(fallback_code, encoding="utf-8")

        # Verify the fallback compiles
        exit_code, stderr = _compile_test(head_workspace, str(test_file))
        record.compile_passed = (exit_code == 0)
        if not record.compile_passed:
            record.errors.append(f"Fallback template compile failed: {stderr[:500]}")

    # ── Phase 3: Check for human_fixture tests ──
    # These are manually written tests committed in the repo
    human_fixtures = list(test_dir.glob("*DbState*.java")) + list(
        test_dir.glob("*Regression*.java")
    )
    human_fixture_paths = [str(p) for p in human_fixtures if p.name != "SpecProofGeneratedTest.java"]

    record.test_path = str(test_file)

    return {
        "generated_tests_path": record.test_path,
        "generation_record": {
            "source": record.source,
            "attempts": record.attempts,
            "compile_passed": record.compile_passed,
            "test_path": record.test_path,
            "human_fixtures": human_fixture_paths,
            "errors": record.errors,
            "llm_code_len": len(record.llm_code),
        },
    }

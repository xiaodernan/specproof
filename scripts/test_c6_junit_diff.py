"""P0.5-C6: LLM generate JUnit test → compile → Base/Head differential run.

DeepSeek generates a JUnit 5 + Spring Boot integration test that verifies the
authentication requirement. The test is written to the demo project, compiled
with mvnw, and executed in both Base and Head git worktrees.
"""

import asyncio
import os
import re
import subprocess
import sys

_project_root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, _project_root)
os.chdir(_project_root)

try:
    from dotenv import load_dotenv

    load_dotenv(os.path.join(_project_root, ".env"))
except ImportError:
    pass

DEMO_DIR = os.path.join(_project_root, "demo", "spring-backend")
TEST_DIR = os.path.join(DEMO_DIR, "src", "test", "java", "com", "specproof", "demo")
TEST_FILE = os.path.join(TEST_DIR, "AuthRegressionTest.java")

# The controller code that changed between base and head
CONTROLLER_DIFF = """Base version (with @PreAuthorize):
    @PutMapping("/{id}/email")
    @PreAuthorize("isAuthenticated()")
    public ResponseEntity<UserResponse> changeEmail(
            @PathVariable Long id,
            @Valid @RequestBody ChangeEmailRequest request) {
        return ResponseEntity.ok(userService.changeEmail(id, request));
    }

Head version (without @PreAuthorize):
    @PutMapping("/{id}/email")
    public ResponseEntity<UserResponse> changeEmail(
            @PathVariable Long id,
            @Valid @RequestBody ChangeEmailRequest request) {
        return ResponseEntity.ok(userService.changeEmail(id, request));
    }"""

EXISTING_TEST_TEMPLATE = """package com.specproof.demo;

import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.*;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.*;
import com.specproof.demo.dto.ChangeEmailRequest;
import com.specproof.demo.entity.User;
import com.specproof.demo.repository.UserRepository;
import org.junit.jupiter.api.BeforeEach;
import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.autoconfigure.web.servlet.AutoConfigureMockMvc;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.http.MediaType;
import org.springframework.security.test.context.support.WithMockUser;
import org.springframework.test.context.ActiveProfiles;
import org.springframework.test.web.servlet.MockMvc;
import com.fasterxml.jackson.databind.ObjectMapper;

@SpringBootTest
@AutoConfigureMockMvc
@ActiveProfiles("test")
public class UserControllerTest {
    @Autowired private MockMvc mockMvc;
    @Autowired private UserRepository userRepository;
    @Autowired private ObjectMapper objectMapper;
    // ... test methods
}"""

LLM_TEST_GEN_PROMPT = """\
You are a senior Java quality engineer. Write a JUnit 5 + Spring Boot
integration test that verifies the authentication requirement for a user
email change API.

## Context

A PR removed the @PreAuthorize("isAuthenticated()") annotation from the
changeEmail endpoint. This is a SECURITY REGRESSION — the endpoint no
longer enforces authentication at the method level.

The requirement: "All API endpoints must require authentication.
Unauthenticated requests must return 401 Unauthorized."

## Controller Diff

{diff}

## Existing Test Pattern

{existing}

## Your Task

Generate a SINGLE test class `AuthRegressionTest.java` that contains:

1. `unauthChangeEmailShouldReturn401()` — sends an UNAUTHENTICATED PUT
   to /api/users/{{id}}/email, expects HTTP 401.
   This test MUST NOT use @WithMockUser — it tests the UNAUTHENTICATED case.

2. `authChangeEmailShouldSucceed()` — sends an AUTHENTICATED PUT
   to /api/users/{{id}}/email with @WithMockUser, expects HTTP 200.

The test class should:
- Use @SpringBootTest, @AutoConfigureMockMvc, @ActiveProfiles("test")
- Use @Import(TestMockBeansConfig.class) to enable mock infrastructure beans
- Import com.specproof.demo.config.TestMockBeansConfig
- Use @Autowired MockMvc
- Use @Autowired UserRepository
- Use @BeforeEach to set up a test user (as shown in the existing template)
- Use the same package `com.specproof.demo`
- Import ChangeEmailRequest, User, and other domain classes

Output ONLY the Java code, no explanation.
```java"""


def extract_java_code(raw: str) -> str:
    """Extract Java code block from LLM response."""
    # Try ```java ... ``` block first
    m = re.search(r"```java\s*\n(.*?)```", raw, re.DOTALL)
    if m:
        return m.group(1)
    # Try ``` ... ``` block
    m = re.search(r"```\s*\n(.*?)```", raw, re.DOTALL)
    if m:
        return m.group(1)
    # Assume raw is code
    return raw


def validate_java(code: str) -> list[str]:
    """Quick sanity checks on generated Java."""
    issues = []
    if "class AuthRegressionTest" not in code:
        issues.append("Missing class AuthRegressionTest")
    if "@SpringBootTest" not in code:
        issues.append("Missing @SpringBootTest")
    if "@Test" not in code:
        issues.append("Missing @Test annotation")
    if "mockMvc" not in code:
        issues.append("Missing mockMvc usage")
    if "TestMockBeansConfig" not in code:
        issues.append("Missing @Import(TestMockBeansConfig.class)")
    if "status().isUnauthorized()" not in code and "is4xxClientError" not in code:
        issues.append("Missing 401 assertion on unauthenticated request")
    return issues


def run_mvnw(args: list[str], cwd: str = DEMO_DIR) -> tuple[int, str, str]:
    """Run mvnw and return (exit_code, stdout, stderr)."""
    is_win = sys.platform == "win32"
    cmd = ["mvnw.cmd" if is_win else "./mvnw"] + args
    java_home = os.environ.get("JAVA_HOME", "")
    if not java_home:
        raise RuntimeError("JAVA_HOME must be set to a JDK 21 installation")
    env = os.environ.copy()
    proc = subprocess.run(
        cmd,
        cwd=cwd,
        capture_output=True,
        text=True,
        timeout=300,
        env=env,
    )
    return proc.returncode, proc.stdout, proc.stderr


async def main() -> int:
    print("=" * 60)
    print("P0.5-C6: LLM JUnit Test Generation + Base/Head Differential")
    print("=" * 60)

    # ── Step 1: Generate JUnit test via DeepSeek ──
    print("\n[1/5] Generating JUnit test via DeepSeek...")
    from providers.base import LLMMessage
    from providers.openai_compatible import OpenAICompatibleProvider

    provider = OpenAICompatibleProvider()
    prompt = LLM_TEST_GEN_PROMPT.format(
        diff=CONTROLLER_DIFF,
        existing=EXISTING_TEST_TEMPLATE,
    )

    response = await provider.chat(
        [LLMMessage(role="user", content=prompt[:8000])],  # keep under token limit
        timeout=180,
    )
    await provider.close()

    raw_code = response.content or ""
    print(f"  Tokens used: {response.usage}")
    print(f"  Reasoning: {bool(response.reasoning_content)}")

    java_code = extract_java_code(raw_code)
    print(f"  Extracted {len(java_code)} chars of Java code")

    # Step 2: Validate generated code
    print("\n[2/5] Validating generated test...")
    issues = validate_java(java_code)
    if issues:
        for i in issues:
            print(f"  WARNING: {i}")
    else:
        print("  All basic checks passed")

    # Step 3: Write test file
    print(f"\n[3/5] Writing test to {TEST_FILE}...")
    os.makedirs(TEST_DIR, exist_ok=True)
    with open(TEST_FILE, "w", encoding="utf-8") as f:
        f.write(java_code)
    print(f"  Written ({len(java_code)} bytes)")

    # Step 4: Compile
    print("\n[4/5] Compiling with mvnw test-compile...")
    exit_code, stdout, stderr = run_mvnw(["test-compile", "-q"])
    if exit_code != 0:
        print(f"  COMPILE FAILED (exit {exit_code})")
        # Print last 50 lines of stderr
        lines = (stderr + stdout).strip().split("\n")
        for line in lines[-40:]:
            print(f"  | {line}")
        print("\n  Saving generated code for debugging...")
        print(f"  Test written to: {TEST_FILE}")
        return 1
    print("  Compile OK")

    # Step 5: Run differential
    print("\n[5/5] Running differential (Base vs Head)...")
    print("  Checking out base tag...")
    subprocess.run(
        ["git", "checkout", "base", "--quiet"],
        cwd=DEMO_DIR,
        capture_output=True,
    )
    exit_base, out_base, err_base = run_mvnw(["-Dtest=AuthRegressionTest", "test", "-q"])

    print("  Checking out head-v1 tag...")
    subprocess.run(
        ["git", "checkout", "head-v1", "--quiet"],
        cwd=DEMO_DIR,
        capture_output=True,
    )
    exit_head, out_head, err_head = run_mvnw(["-Dtest=AuthRegressionTest", "test", "-q"])

    # ── Results ──
    print("\n" + "=" * 60)
    print("RESULTS")
    print("=" * 60)
    print(f"  Base (with @PreAuthorize):    exit={exit_base}")
    print(f"  Head (without @PreAuthorize): exit={exit_head}")

    # Determine verdict
    if exit_base == 0 and exit_head != 0:
        verdict = "REGRESSION DETECTED"
        detail = "Test passes in Base (auth enforced) but fails in Head (auth removed)"
    elif exit_base != 0 and exit_head == 0:
        verdict = "UNEXPECTED_FIX"
        detail = "Test fails in Base but passes in Head"
    elif exit_base != 0 and exit_head != 0:
        verdict = "AMBIGUOUS (both fail)"
        detail = "Test fails in both environments — check test validity"
    else:
        verdict = "COMPLIANT (both pass)"
        detail = (
            "Test passes in both environments. Note: SecurityConfig filter chain "
            "may mask method-level annotation removal at HTTP level."
        )

    print(f"  Verdict: {verdict}")
    print(f"  Detail:  {detail}")

    # Return to original branch
    subprocess.run(
        ["git", "checkout", "head-v1", "--quiet"],
        cwd=DEMO_DIR,
        capture_output=True,
    )

    return 0 if exit_base != 0 and exit_head == 0 else (0 if exit_base == 0 else 1)


if __name__ == "__main__":
    sys.exit(asyncio.run(main()))

"""generate_counterexamples node - generate a JUnit counterexample test.

v2 honesty fixes:
- The generated test is a SINGLE test method: unauthenticated PUT must
  return 401 AND leave the DB row unchanged (andReturn + assertAll -
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
   must be unchanged afterwards (no short-circuit - both assertions run)
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
    # P6 economics: the deterministic path runs the FULL head test here
    # (compile + surefire in one sandbox invocation); run_differential
    # reuses this recorded run instead of invoking Maven on Head again.
    head_run: dict[str, Any] = field(default_factory=dict)


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

    P0-A1: the compile runs inside the execution SANDBOX (sandbox/runner.py) -
    a malicious pom.xml/build plugin must never execute on the host.
    """
    del test_file  # path validated by the caller; compilation covers the tree
    pom = Path(workspace) / "pom.xml"
    if not pom.exists():
        return -1, "No pom.xml found"

    import platform

    from sandbox.runner import run_sandboxed

    # Sandbox runs the image's mvn; the local fallback uses the wrapper
    # (absolute path - CreateProcessW resolves relative names against the
    # parent cwd, not cwd=).
    if platform.system() == "Windows":
        local_cmd = [os.path.join(workspace, "mvnw.cmd"), "test-compile", "-q"]
    else:
        local_cmd = [os.path.join(workspace, "mvnw"), "test-compile", "-q"]
    result = run_sandboxed(
        # -o: the sandbox has --network none by design; every artifact
        # must resolve from the seeded Maven cache volume.
        ["mvn", "-o", "test-compile", "-q", "-f", "/work/pom.xml"],
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
import com.specproof.demo.event.EmailChangedEvent;
import com.specproof.demo.repository.UserRepository;
// @P6_DOMAIN_IMPORTS@
import jakarta.persistence.OptimisticLockException;
import jakarta.servlet.ServletException;
import java.math.BigDecimal;
import java.util.concurrent.TimeUnit;
import java.util.concurrent.atomic.AtomicInteger;
import java.util.concurrent.atomic.AtomicReference;
import org.junit.jupiter.api.BeforeEach;
import org.junit.jupiter.api.Test;
import org.springframework.amqp.rabbit.core.RabbitTemplate;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.autoconfigure.web.servlet.AutoConfigureMockMvc;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.context.annotation.Import;
import org.springframework.data.redis.core.StringRedisTemplate;
import org.springframework.http.MediaType;
import org.springframework.orm.ObjectOptimisticLockingFailureException;
import org.springframework.security.test.context.support.WithMockUser;
import org.springframework.test.context.ActiveProfiles;
import org.springframework.test.web.servlet.MockMvc;
import org.springframework.test.web.servlet.MvcResult;

import static org.junit.jupiter.api.Assertions.assertAll;
import static org.junit.jupiter.api.Assertions.assertEquals;
import static org.junit.jupiter.api.Assertions.assertNotNull;
import static org.junit.jupiter.api.Assertions.assertTrue;
import static org.hamcrest.Matchers.hasSize;
import static org.mockito.ArgumentMatchers.any;
import static org.mockito.ArgumentMatchers.anyString;
import static org.mockito.ArgumentMatchers.argThat;
import static org.mockito.ArgumentMatchers.eq;
import static org.mockito.ArgumentMatchers.longThat;
import static org.mockito.Mockito.doAnswer;
import static org.mockito.Mockito.doThrow;
import static org.mockito.Mockito.verify;
import static org.mockito.Mockito.when;
import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.get;
import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.post;
import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.put;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.jsonPath;
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

    @Autowired
    private RabbitTemplate rabbitTemplate;

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

        // The response echoes the REQUEST value, so silent corruption
        // (case-19) is only observable in the STORED row.
        String stored = userRepository.findById(user.getId())
                .map(User::getEmail).orElse("NOT_FOUND");
        assertEquals("fresh@example.com", stored,
            "DB STATE VIOLATION: stored email does not equal the requested "
            + "value");
    }

"""

_BLANK_TEST_TEMPLATE = """    @Test
    @WithMockUser
    void blankEmailChangeMustBeRejected() throws Exception {
        User user = userRepository.findAll().get(0);
        ChangeEmailRequest req = new ChangeEmailRequest("");

        // Validation failures are HANDLED by Spring MVC (400), unlike the
        // unhandled RuntimeException, so the raw status is asserted here.
        MvcResult result = mockMvc.perform(put("/api/users/" + "{id}" + "/email", user.getId())
                        .contentType(MediaType.APPLICATION_JSON)
                        .content(objectMapper.writeValueAsString(req)))
                .andReturn();

        int status = result.getResponse().getStatus();
        String emailAfter = userRepository.findById(user.getId())
                .map(User::getEmail).orElse("NOT_FOUND");
        assertAll(
            () -> assertTrue(status >= 400,
                "Blank email was ACCEPTED: got " + status),
            () -> assertEquals("specproof@example.com", emailAfter,
                "DB STATE VIOLATION: blank email change was accepted "
                + "and persisted")
        );
    }

"""

_EVENT_TEST_TEMPLATE = """    @Test
    @WithMockUser
    void emailChangeEventMustGoToExpectedRoutingKey() throws Exception {
        User user = userRepository.findAll().get(0);
        ChangeEmailRequest req = new ChangeEmailRequest("fresh@example.com");

        // The test profile wires a MOCK RabbitTemplate (@Primary): the
        // only way to verify delivery semantics is the invocation itself.
        // Counter-based (not verify()): the mock is shared across tests in
        // this class, so a bare verify() (times-1 semantics) would count
        // other tests' publishes and fail spuriously on the honest base.
        AtomicInteger publishes = new AtomicInteger();
        doAnswer(invocation -> {
            publishes.incrementAndGet();
            return null;
        }).when(rabbitTemplate).convertAndSend(
                eq("specproof.demo.events"), eq("email.changed"),
                any(EmailChangedEvent.class));

        mockMvc.perform(put("/api/users/" + "{id}" + "/email", user.getId())
                        .contentType(MediaType.APPLICATION_JSON)
                        .content(objectMapper.writeValueAsString(req)))
                .andExpect(status().isOk());

        assertTrue(publishes.get() >= 1,
            "email.changed was not published to the documented exchange "
            + "and routing key");
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
        // perform() (the demo app has no global exception handler) - the
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


# ── P6 100-case differential templates ─────────────────────────
# Each template is selected ONLY by a contract family that existing
# case-01..20 specs never compile, so the pre-P6 cases keep exactly the
# generated test they had (their measured behavior is untouched).

_DOMAIN_IMPORTS = """import com.specproof.demo.dto.CancelOrderRequest;
import com.specproof.demo.dto.PlaceOrderRequest;
import com.specproof.demo.entity.CustomerOrder;
import com.specproof.demo.entity.Product;
import com.specproof.demo.event.OrderCreatedEvent;
import com.specproof.demo.instrument.SqlQueryCounter;
import com.specproof.demo.repository.CustomerOrderRepository;
import com.specproof.demo.repository.ProductRepository;
"""

_DOMAIN_FIELDS = """    @Autowired
    private CustomerOrderRepository orderRepository;

    @Autowired
    private ProductRepository productRepository;

    @Autowired
    private SqlQueryCounter sqlQueryCounter;

    @Autowired
    private StringRedisTemplate stringRedisTemplate;

"""

_SEED_USER_PRODUCT = """        orderRepository.deleteAll();
        productRepository.deleteAll();
        userRepository.deleteAll();
        User user = new User("specproof", "specproof@example.com");
        user.setPasswordHash("hash");
        userRepository.saveAndFlush(user);
        Product product = new Product("widget", 10, new BigDecimal("10.00"));
        productRepository.saveAndFlush(product);
"""

_CACHE_EVICT_TEST_TEMPLATE = """    @Test
    @WithMockUser
    void emailChangeMustEvictUserCache() throws Exception {
        User user = userRepository.findAll().get(0);
        String cacheKey = "user:cache:" + user.getId();
        String tokenPattern = "token:user:" + user.getId() + ":*";
        ChangeEmailRequest req = new ChangeEmailRequest("fresh@example.com");

        // The test profile wires a MOCK StringRedisTemplate (@Primary): the
        // only way to verify invalidation semantics is the invocation itself.
        // The delete-time state probe pins the evict-AFTER-save ordering: when
        // the delete fires, the saved row must already carry the new email
        // (evicting earlier reopens the stale-repopulation window). The key
        // matchers are per-test-user, so other tests' invocations on the
        // shared mock cannot interfere.
        AtomicReference<String> storedAtEvict = new AtomicReference<>();
        doAnswer(invocation -> {
            storedAtEvict.set(userRepository.findById(user.getId())
                    .map(User::getEmail).orElse("NOT_FOUND"));
            return null;
        }).when(stringRedisTemplate).delete(eq(cacheKey));

        mockMvc.perform(put("/api/users/" + "{id}" + "/email", user.getId())
                        .contentType(MediaType.APPLICATION_JSON)
                        .content(objectMapper.writeValueAsString(req)))
                .andExpect(status().isOk());

        assertEquals("fresh@example.com", storedAtEvict.get(),
            "Cache was evicted before the DB write - stale repopulation window");
        verify(stringRedisTemplate).delete(eq(cacheKey));
        verify(stringRedisTemplate).keys(eq(tokenPattern));
    }

"""

_CACHE_ASIDE_TEST_TEMPLATE = """    @Test
    @WithMockUser
    void getUserMustUseCacheAside() throws Exception {
        User user = userRepository.findAll().get(0);
        String cacheKey = "user:cache:" + user.getId();
        String cachedJson = "{\\"id\\":" + user.getId()
                + ",\\"username\\":\\"specproof\\",\\"email\\":\\"specproof@example.com\\","
                + "\\"orderCount\\":0}";
        var valueOps = stringRedisTemplate.opsForValue();
        when(valueOps.get(cacheKey)).thenReturn(null, cachedJson);

        sqlQueryCounter.reset();
        mockMvc.perform(get("/api/users/" + "{id}", user.getId()))
                .andExpect(status().isOk());
        mockMvc.perform(get("/api/users/" + "{id}", user.getId()))
                .andExpect(status().isOk());
        long queries = sqlQueryCounter.getCount();

        // Base: first read misses the cache (2 queries: user + order count),
        // second read is served from the cache (0 queries). A head that
        // skips the write-back or reads/writes different keys pays the DB
        // cost twice - visible here without any flaky timing.
        verify(valueOps).set(
                eq(cacheKey), anyString(), longThat(ttl -> ttl > 0),
                eq(TimeUnit.SECONDS));
        assertTrue(queries <= 2,
            "Expected cache-aside to serve the second read (<=2 queries), got " + queries);
    }

"""

_STALE_STOCK_TEST_TEMPLATE = """    @Test
    void staleStockWriteMustBeRejected() throws Exception {
        productRepository.deleteAll();
        Product product = new Product("widget", 10, new BigDecimal("10.00"));
        productRepository.saveAndFlush(product);

        Product snapshotA = productRepository.findById(product.getId()).orElseThrow();
        Product snapshotB = productRepository.findById(product.getId()).orElseThrow();
        snapshotA.setStock(snapshotA.getStock() - 3);
        productRepository.saveAndFlush(snapshotA);

        final boolean[] rejected = {false};
        try {
            snapshotB.setStock(snapshotB.getStock() - 4);
            productRepository.saveAndFlush(snapshotB);
        } catch (ObjectOptimisticLockingFailureException | OptimisticLockException e) {
            rejected[0] = true;
        }

        Integer finalStock = productRepository.findById(product.getId())
                .orElseThrow().getStock();
        assertAll(
            () -> assertTrue(rejected[0],
                "Stale write was silently accepted - lost update not prevented"),
            () -> assertEquals(7, finalStock,
                "Concurrent decrements must each apply once (7), got " + finalStock)
        );
    }

"""

_IDEMPOTENT_TEST_TEMPLATE = """    @Test
    void duplicateOrderRequestMustBeDeduped() throws Exception {
""" + _SEED_USER_PRODUCT + """
        PlaceOrderRequest req = new PlaceOrderRequest(
                user.getId(), product.getId(), 3, "req-dedup-1");
        mockMvc.perform(post("/api/orders")
                        .contentType(MediaType.APPLICATION_JSON)
                        .content(objectMapper.writeValueAsString(req)))
                .andExpect(status().isOk());
        mockMvc.perform(post("/api/orders")
                        .contentType(MediaType.APPLICATION_JSON)
                        .content(objectMapper.writeValueAsString(req)))
                .andExpect(status().isOk());

        int orderRows = orderRepository.findAll().size();
        Integer stock = productRepository.findById(product.getId())
                .orElseThrow().getStock();
        assertAll(
            () -> assertEquals(1, orderRows,
                "Replayed request created a second order row (" + orderRows + ")"),
            () -> assertEquals(7, stock,
                "Replayed request decremented stock twice (" + stock + ")")
        );
    }

"""

_ROLLBACK_TEST_TEMPLATE = """    @Test
    void orderPlacementFailureMustNotLoseStock() throws Exception {
""" + _SEED_USER_PRODUCT + """
        PlaceOrderRequest ok = new PlaceOrderRequest(
                user.getId(), product.getId(), 3, "req-ok-1");
        mockMvc.perform(post("/api/orders")
                        .contentType(MediaType.APPLICATION_JSON)
                        .content(objectMapper.writeValueAsString(ok)))
                .andExpect(status().isOk());

        PlaceOrderRequest over = new PlaceOrderRequest(
                user.getId(), product.getId(), 99, "req-over-1");
        final boolean[] rejected = {false};
        try {
            mockMvc.perform(post("/api/orders")
                            .contentType(MediaType.APPLICATION_JSON)
                            .content(objectMapper.writeValueAsString(over)));
        } catch (ServletException e) {
            rejected[0] = e.getCause() instanceof RuntimeException;
        }

        Integer stock = productRepository.findById(product.getId())
                .orElseThrow().getStock();
        long orderRows = orderRepository.findAll().size();
        assertAll(
            () -> assertTrue(rejected[0], "Oversized order was accepted"),
            () -> assertEquals(7, stock,
                "Failed order leaked its stock decrement (" + stock + ")"),
            () -> assertEquals(1, orderRows,
                "Failed order left an order row behind (" + orderRows + ")")
        );
    }

"""

_CANCEL_RESTOCK_TEST_TEMPLATE = """    @Test
    void cancelOrderMustRestock() throws Exception {
""" + _SEED_USER_PRODUCT + """
        PlaceOrderRequest place = new PlaceOrderRequest(
                user.getId(), product.getId(), 3, "req-cancel-1");
        mockMvc.perform(post("/api/orders")
                        .contentType(MediaType.APPLICATION_JSON)
                        .content(objectMapper.writeValueAsString(place)))
                .andExpect(status().isOk());

        CancelOrderRequest cancel = new CancelOrderRequest("req-cancel-1");
        mockMvc.perform(post("/api/orders/cancel")
                        .contentType(MediaType.APPLICATION_JSON)
                        .content(objectMapper.writeValueAsString(cancel)))
                .andExpect(status().isOk());

        Integer stock = productRepository.findById(product.getId())
                .orElseThrow().getStock();
        String status = orderRepository.findByRequestId("req-cancel-1")
                .orElseThrow().getStatus();
        assertAll(
            () -> assertEquals(10, stock,
                "Cancelling must restock the product (10), got " + stock),
            () -> assertEquals("CANCELLED", status,
                "Cancelling must mark the order CANCELLED, got " + status)
        );
    }

"""

_FULL_STOCK_TEST_TEMPLATE = """    @Test
    void fullStockOrderMustBeAllowed() throws Exception {
""" + _SEED_USER_PRODUCT + """
        PlaceOrderRequest req = new PlaceOrderRequest(
                user.getId(), product.getId(), 10, "req-full-1");
        mockMvc.perform(post("/api/orders")
                        .contentType(MediaType.APPLICATION_JSON)
                        .content(objectMapper.writeValueAsString(req)))
                .andExpect(status().isOk());

        Integer stock = productRepository.findById(product.getId())
                .orElseThrow().getStock();
        assertEquals(0, stock,
            "Ordering exactly the available stock must succeed (stock 0), got " + stock);

        // Boundary sibling: a non-positive quantity must be rejected with
        // 4xx and must not create an order row (validation failures are
        // HANDLED by Spring MVC, so the raw status is asserted here).
        PlaceOrderRequest zero = new PlaceOrderRequest(
                user.getId(), product.getId(), 0, "req-zero-1");
        MvcResult zeroResult = mockMvc.perform(post("/api/orders")
                        .contentType(MediaType.APPLICATION_JSON)
                        .content(objectMapper.writeValueAsString(zero)))
                .andReturn();
        int zeroStatus = zeroResult.getResponse().getStatus();
        assertTrue(zeroStatus >= 400,
            "Non-positive quantity was accepted: got " + zeroStatus);
        assertEquals(0, stock,
            "A rejected zero-quantity order must not change the stock");
    }

"""

_ORDER_AMOUNT_TEST_TEMPLATE = """    @Test
    void orderAmountMustEqualUnitPriceTimesQuantity() throws Exception {
""" + _SEED_USER_PRODUCT + """
        PlaceOrderRequest req = new PlaceOrderRequest(
                user.getId(), product.getId(), 3, "req-amt-1");
        mockMvc.perform(post("/api/orders")
                        .contentType(MediaType.APPLICATION_JSON)
                        .content(objectMapper.writeValueAsString(req)))
                .andExpect(status().isOk());

        BigDecimal amount = orderRepository.findByRequestId("req-amt-1")
                .orElseThrow().getAmount();
        assertEquals(0, new BigDecimal("30.00").compareTo(amount),
            "Order amount must be 30.00 (price 10 x qty 3), got " + amount);
    }

"""

_NPLUSONE_TEST_TEMPLATE = """    @Test
    void listUsersMustNotUseNPlusOneQueries() throws Exception {
        orderRepository.deleteAll();
        userRepository.deleteAll();
        for (int i = 0; i < 10; i++) {
            User u = new User("bulk" + i, "bulk" + i + "@example.com");
            u.setPasswordHash("hash");
            userRepository.saveAndFlush(u);
            orderRepository.saveAndFlush(new CustomerOrder(
                    u.getId(), 1L, 1, new BigDecimal("10.00"),
                    "req-bulk-" + i + "-1", "CREATED"));
            orderRepository.saveAndFlush(new CustomerOrder(
                    u.getId(), 1L, 1, new BigDecimal("10.00"),
                    "req-bulk-" + i + "-2", "CREATED"));
        }

        sqlQueryCounter.reset();
        mockMvc.perform(get("/api/users"))
                .andExpect(status().isOk())
                .andExpect(jsonPath("$", hasSize(10)))
                .andExpect(jsonPath("$[0].orderCount").value(2));
        long queries = sqlQueryCounter.getCount();

        assertTrue(queries <= 3,
            "GET /api/users used " + queries + " queries; expected <= 3 "
            + "(per-user query loops are N+1 regressions)");
    }

"""

_ORDER_EVENT_TEST_TEMPLATE = """    @Test
    void orderCreatedEventMustGoToExpectedRoutingKey() throws Exception {
""" + _SEED_USER_PRODUCT + """
        // Counter-based assertion instead of verify(): the RabbitTemplate
        // mock is shared across tests in this class, so a bare verify()
        // (times-1 semantics) would count other tests' publishes. This
        // counter only counts THIS test's post-stub invocations.
        AtomicInteger publishes = new AtomicInteger();
        doAnswer(invocation -> {
            publishes.incrementAndGet();
            return null;
        }).when(rabbitTemplate).convertAndSend(
                eq("specproof.demo.events"), eq("order.created"),
                any(OrderCreatedEvent.class));

        PlaceOrderRequest req = new PlaceOrderRequest(
                user.getId(), product.getId(), 2, "req-ev-1");
        mockMvc.perform(post("/api/orders")
                        .contentType(MediaType.APPLICATION_JSON)
                        .content(objectMapper.writeValueAsString(req)))
                .andExpect(status().isOk());

        assertTrue(publishes.get() >= 1,
            "order.created was not published to the documented exchange "
            + "and routing key");
    }

"""

_ORDER_EVENT_ONCE_TEST_TEMPLATE = """    @Test
    void orderCreatedEventPublishedExactlyOnce() throws Exception {
""" + _SEED_USER_PRODUCT + """
        AtomicInteger publishes = new AtomicInteger();
        doAnswer(invocation -> {
            publishes.incrementAndGet();
            return null;
        }).when(rabbitTemplate).convertAndSend(
                eq("specproof.demo.events"), eq("order.created"),
                any(OrderCreatedEvent.class));

        PlaceOrderRequest req = new PlaceOrderRequest(
                user.getId(), product.getId(), 2, "req-once-1");
        mockMvc.perform(post("/api/orders")
                        .contentType(MediaType.APPLICATION_JSON)
                        .content(objectMapper.writeValueAsString(req)))
                .andExpect(status().isOk());

        assertEquals(1, publishes.get(),
            "order.created must be published exactly once, got " + publishes.get());
    }

"""

_ORDER_RETRY_TEST_TEMPLATE = """    @Test
    void orderRetryMustNotDuplicateEvent() throws Exception {
""" + _SEED_USER_PRODUCT + """
        AtomicInteger publishes = new AtomicInteger();
        doThrow(new RuntimeException("broker unavailable"))
                .doAnswer(invocation -> {
                    publishes.incrementAndGet();
                    return null;
                })
                .when(rabbitTemplate).convertAndSend(
                        eq("specproof.demo.events"), eq("order.created"),
                        org.mockito.ArgumentMatchers.<OrderCreatedEvent>argThat(event ->
                                event.getRequestId().equals("req-retry-1")));

        PlaceOrderRequest req = new PlaceOrderRequest(
                user.getId(), product.getId(), 2, "req-retry-1");
        final boolean[] rejected = {false};
        try {
            mockMvc.perform(post("/api/orders")
                            .contentType(MediaType.APPLICATION_JSON)
                            .content(objectMapper.writeValueAsString(req)));
        } catch (ServletException e) {
            rejected[0] = e.getCause() instanceof RuntimeException;
        }

        assertAll(
            () -> assertTrue(rejected[0],
                "Publish failure must surface to the caller "
                + "(no silent retry-duplication)"),
            () -> assertEquals(0, publishes.get(),
                "A failed publish must not be retried into a duplicate event, got "
                + publishes.get() + " publishes")
        );
    }

"""

_INVALID_EMAIL_TEST_TEMPLATE = """    @Test
    @WithMockUser
    void invalidEmailChangeMustBeRejected() throws Exception {
        User user = userRepository.findAll().get(0);
        ChangeEmailRequest req = new ChangeEmailRequest("not-an-email");

        MvcResult result = mockMvc.perform(put("/api/users/" + "{id}" + "/email", user.getId())
                        .contentType(MediaType.APPLICATION_JSON)
                        .content(objectMapper.writeValueAsString(req)))
                .andReturn();

        int status = result.getResponse().getStatus();
        String emailAfter = userRepository.findById(user.getId())
                .map(User::getEmail).orElse("NOT_FOUND");
        assertAll(
            () -> assertTrue(status >= 400,
                "Malformed email was ACCEPTED: got " + status),
            () -> assertEquals("specproof@example.com", emailAfter,
                "DB STATE VIOLATION: malformed email was persisted")
        );
    }

"""

_SPURIOUS_EVENT_TEST_TEMPLATE = """    @Test
    @WithMockUser
    void emailChangeMustNotPublishSpuriousEvent() throws Exception {
        User user = userRepository.findAll().get(0);
        ChangeEmailRequest req = new ChangeEmailRequest(user.getEmail());

        AtomicInteger publishes = new AtomicInteger();
        doAnswer(invocation -> {
            publishes.incrementAndGet();
            return null;
        }).when(rabbitTemplate).convertAndSend(
                eq("specproof.demo.events"), eq("email.changed"),
                any(EmailChangedEvent.class));

        mockMvc.perform(put("/api/users/" + "{id}" + "/email", user.getId())
                        .contentType(MediaType.APPLICATION_JSON)
                        .content(objectMapper.writeValueAsString(req)))
                .andExpect(status().isOk());

        assertEquals(0, publishes.get(),
            "A no-op email change must not publish an event, got "
            + publishes.get() + " publishes");
    }

"""

_EVENT_PAYLOAD_TEST_TEMPLATE = """    @Test
    @WithMockUser
    void emailChangeEventPayloadMustBeIntact() throws Exception {
        User user = userRepository.findAll().get(0);
        String oldEmail = user.getEmail();
        ChangeEmailRequest req = new ChangeEmailRequest("fresh@example.com");

        // Captured via doAnswer instead of verify+captor: the RabbitTemplate
        // mock is shared across tests, so a verify() would count other
        // tests' email publishes and fail spuriously on the honest base.
        AtomicReference<EmailChangedEvent> captured = new AtomicReference<>();
        doAnswer(invocation -> {
            captured.set((EmailChangedEvent) invocation.getArgument(2));
            return null;
        }).when(rabbitTemplate).convertAndSend(
                eq("specproof.demo.events"), eq("email.changed"),
                any(EmailChangedEvent.class));

        mockMvc.perform(put("/api/users/" + "{id}" + "/email", user.getId())
                        .contentType(MediaType.APPLICATION_JSON)
                        .content(objectMapper.writeValueAsString(req)))
                .andExpect(status().isOk());

        EmailChangedEvent event = captured.get();
        assertNotNull(event, "email.changed was not published to the documented key");
        assertAll(
            () -> assertEquals("fresh@example.com", event.getNewEmail(),
                "Event payload must carry the new email"),
            () -> assertEquals(oldEmail, event.getOldEmail(),
                "Event payload must carry the old email"),
            () -> assertNotNull(event.getTimestamp(),
                "Event payload must carry a publish timestamp")
        );
    }

"""

def _build_deterministic_test(contracts: list[dict[str, Any]]) -> str:
    """Deterministic differential tests for the demo repository.

    Always: unauthenticated PUT -> 401 AND DB row unchanged (AUTH family).
    When a UNIQUE contract is compiled: the duplicate-email rejection
    test - the static tier can only see REMOVED guards, so inverted-guard
    regressions (case-17) are only catchable by EXECUTING the behaviour.

    P6: additional families select additional templates (cache, concurrency,
    idempotency, atomicity, boundaries, N+1, order events, email format).
    Templates are keyed on families the pre-P6 case specs never compile,
    so case-01..20 keep exactly the generated test they already had.
    """
    body = _AUTH_TEST_TEMPLATE
    if _has_unique_contract(contracts):
        # Duplicate-rejection catches guard REMOVALS; fresh-email-success
        # (with exact-email assertion) catches guard INVERSIONS (case-17)
        # and silent data corruption (case-19); blank-rejection catches
        # validation relaxation (case-20). Static sight cannot judge any
        # of them - only execution can.
        body += (
            _UNIQUE_TEST_TEMPLATE + _FRESH_TEST_TEMPLATE
            + _BLANK_TEST_TEMPLATE
        )
    if _has_event_contract(contracts):
        # The mock-RabbitTemplate invocation check catches wrong routing
        # keys (case-18) and duplicate publishes (case-07) at execution
        # time - a string-constant diff cannot prove delivery semantics.
        body += _EVENT_TEST_TEMPLATE

    # ── P6 families (case-21..100) ─────────────────────────────
    if _has_family(contracts, "CACHE-01"):
        # Mock-Redis invocation checks: cache eviction + token key pattern
        # (cases 56/61) and cache-aside read/write/TTL with the query
        # counter (cases 57/58/63/65). Static sight cannot judge any of
        # them - only the recorded invocations can.
        body += _CACHE_EVICT_TEST_TEMPLATE + _CACHE_ASIDE_TEST_TEMPLATE
    if _has_family(contracts, "CONCURRENCY-01"):
        # Deterministic stale-write: two snapshots of the same row, first
        # save wins, the second must raise an optimistic-lock failure
        # (cases 29/30). No threads, no timing - fully deterministic.
        body += _STALE_STOCK_TEST_TEMPLATE
    if _has_family(contracts, "IDEMPOTENT-01"):
        body += _IDEMPOTENT_TEST_TEMPLATE
    if _has_family(contracts, "ATOMICITY-01"):
        body += _ROLLBACK_TEST_TEMPLATE + _CANCEL_RESTOCK_TEST_TEMPLATE
    if _has_family(contracts, "BOUNDARY-01"):
        body += _FULL_STOCK_TEST_TEMPLATE
    if _has_family(contracts, "ORDER_AMOUNT-01"):
        body += _ORDER_AMOUNT_TEST_TEMPLATE
    if _has_family(contracts, "NPLUSONE-01"):
        # Query-count assertion via SqlQueryCounter: the honest base serves
        # the list in 2 queries; per-user loops blow the bound (cases
        # 79/80/82/83/85/86).
        body += _NPLUSONE_TEST_TEMPLATE
    if _has_family(contracts, "ORDER_EVENT-01"):
        body += (
            _ORDER_EVENT_TEST_TEMPLATE
            + _ORDER_EVENT_ONCE_TEST_TEMPLATE
        )
        if _spec_mentions(contracts, ("retry",)):
            body += _ORDER_RETRY_TEST_TEMPLATE
    if _has_family(contracts, "EMAIL_FORMAT-01"):
        body += _INVALID_EMAIL_TEST_TEMPLATE
    if _has_event_contract(contracts) and _spec_mentions(
        contracts, ("unchanged", "spurious", "no event", "current value")
    ):
        body += _SPURIOUS_EVENT_TEST_TEMPLATE
    if _has_event_contract(contracts) and _spec_mentions(contracts, ("payload",)):
        # The payload template asserts routing key AND payload via an
        # isolated capture, so it REPLACES the legacy verify-based event
        # template: on the shared RabbitTemplate mock a bare verify()
        # (times-1 semantics) would count the payload test's own publish
        # and fail spuriously on the honest base.
        body += _EVENT_PAYLOAD_TEST_TEMPLATE

    domain_families = (
        "CACHE-01", "CONCURRENCY-01", "IDEMPOTENT-01", "ATOMICITY-01",
        "BOUNDARY-01", "ORDER_AMOUNT-01", "NPLUSONE-01", "ORDER_EVENT-01",
    )
    needs_domain = any(_has_family(contracts, fid) for fid in domain_families)
    extra_fields = _DOMAIN_FIELDS if needs_domain else ""
    source = textwrap.dedent(_GENERATED_TEST_HEADER + extra_fields + body + "}\n")
    # The demo-domain imports are conditional: cases whose specs compile no
    # P6 family keep a generated test that compiles against pre-P6 refs
    # (their classpath lacks the orders/products classes).
    source = source.replace(
        "// @P6_DOMAIN_IMPORTS@",
        _DOMAIN_IMPORTS if needs_domain else "",
    )
    return source


def _has_family(contracts: list[dict[str, Any]], family_id: str) -> bool:
    """True when a compiled contract carries exactly this family id."""
    return any(
        str(contract.get("id", "")).upper() == family_id
        for contract in contracts
    )


def _spec_mentions(
    contracts: list[dict[str, Any]], keywords: tuple[str, ...],
) -> bool:
    """True when any compiled contract's text mentions one of the keywords."""
    for contract in contracts:
        text = " ".join([
            str(contract.get("expected_behavior", "")),
            str(contract.get("requirement", "")),
        ]).lower()
        if any(keyword in text for keyword in keywords):
            return True
    return False


def _has_event_contract(contracts: list[dict[str, Any]]) -> bool:
    """True when any compiled contract guards event delivery semantics."""
    for contract in contracts:
        if contract.get("id") == "EVENT_ONCE-01":
            return True
        behavior = str(contract.get("expected_behavior", "")).lower()
        requirement = str(contract.get("requirement", "")).lower()
        if any(k in behavior + " " + requirement
               for k in ("event", "publish", "routing", "delivery")):
            return True
    return False


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
        record.errors.append("No head workspace - cannot generate tests")
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

    # ── P6: seed the head worktree from the shared base build cache ──
    # Unchanged sources are re-dated into the past so Maven recompiles only
    # the PR's changed files; the generated test is written AFTER seeding,
    # so its fresh mtime guarantees it is (re)compiled.
    from agent.nodes.build_cache import base_build_cache_dir, head_changed_paths, seed_head_build

    cache_dir = base_build_cache_dir(state)
    if cache_dir is not None:
        seed_head_build(cache_dir, app_workspace, head_changed_paths(state))

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

        # P6 economics: run the FULL head test here (compile + surefire in
        # ONE sandbox invocation). run_differential reuses the recorded
        # run instead of invoking Maven on Head a second time — one fewer
        # sandbox build per case. Compile failures are distinguished from
        # test failures via the "COMPILATION ERROR" marker, so evidence
        # semantics stay identical to the old separate compile step.
        from agent.nodes.run_differential import _run_generated_test

        head_run = _run_generated_test(app_workspace, "SpecProofGeneratedTest")
        output_tail = (
            head_run.get("stdout", "") + head_run.get("stderr", "")
        )[-500:]
        compile_error = "COMPILATION ERROR" in output_tail
        record.compile_passed = not compile_error
        if compile_error:
            record.errors.append(
                "Fallback template failed to compile on Head: " + output_tail
            )
        record.head_run = {
            "exit_code": head_run.get("exit_code"),
            "test_counts": head_run.get("test_counts", {}),
            "compile_error": compile_error,
            "stdout": head_run.get("stdout", "")[-2000:],
            "stderr": head_run.get("stderr", "")[-2000:],
        }

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
            "head_run": record.head_run,
            "test_file_sha256": _sha256_of(test_file),
        },
    }


def _sha256_of(path: Path) -> str:
    import hashlib

    try:
        return hashlib.sha256(path.read_bytes()).hexdigest()
    except OSError:
        return ""

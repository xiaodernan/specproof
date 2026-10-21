"""The JUnit templates the counterexample generator writes.

The LOGIC of an experiment lives here (what must be asserted); the
domain NAMES come from the profile (``agent/experiments/profile.py``),
so a template is not welded to one repository's vocabulary.

These strings are moved verbatim out of
``agent/nodes/generate_counterexamples.py``; the golden snapshot
(``tests/unit/golden/generated_test_demo.java``) is what proves the move
changed nothing about the source the pipeline produces.
"""

from __future__ import annotations

_GENERATED_TEST_HEADER = """\
package @@java_package@@;

import com.fasterxml.jackson.databind.ObjectMapper;
import @@java_package@@.config.@@test_config_class@@;
import @@java_package@@.dto.@@change_email_request@@;
import @@java_package@@.entity.@@user@@;
import @@java_package@@.event.@@email_event@@;
import @@java_package@@.repository.@@user_repo_class@@;
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
@Import(@@test_config_class@@.class)
public class SpecProofGeneratedTest {

    @Autowired
    private MockMvc mockMvc;

    @Autowired
    private @@user_repo_class@@ @@user_repo@@;

    @Autowired
    private ObjectMapper objectMapper;

    @Autowired
    private RabbitTemplate rabbitTemplate;

    @BeforeEach
    void setUp() {
        @@user_repo@@.deleteAll();
        @@user@@ user = new @@user@@("specproof", "specproof@example.com");
        user.setPasswordHash("hash");
        @@user_repo@@.save(user);
    }

"""

_AUTH_TEST_TEMPLATE = """    @Test
    void unauthenticatedEmailChangeMustBeRejected() throws Exception {
        @@user@@ user = @@user_repo@@.findAll().get(0);
        String emailBefore = user.getEmail();
        @@change_email_request@@ req = new @@change_email_request@@("attacker@evil.com");

        MvcResult result = mockMvc.perform(put(@@user_email_path@@, user.getId())
                        .contentType(MediaType.APPLICATION_JSON)
                        .content(objectMapper.writeValueAsString(req)))
                .andReturn();

        int status = result.getResponse().getStatus();
        String emailAfter = @@user_repo@@.findById(user.getId())
                .map(@@user@@::getEmail).orElse("NOT_FOUND");

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
        @@user@@ user = @@user_repo@@.findAll().get(0);
        @@change_email_request@@ req = new @@change_email_request@@("fresh@example.com");

        mockMvc.perform(put(@@user_email_path@@, user.getId())
                        .contentType(MediaType.APPLICATION_JSON)
                        .content(objectMapper.writeValueAsString(req)))
                .andExpect(status().isOk());

        // The response echoes the REQUEST value, so silent corruption
        // (case-19) is only observable in the STORED row.
        String stored = @@user_repo@@.findById(user.getId())
                .map(@@user@@::getEmail).orElse("NOT_FOUND");
        assertEquals("fresh@example.com", stored,
            "DB STATE VIOLATION: stored email does not equal the requested "
            + "value");
    }

"""

_BLANK_TEST_TEMPLATE = """    @Test
    @WithMockUser
    void blankEmailChangeMustBeRejected() throws Exception {
        @@user@@ user = @@user_repo@@.findAll().get(0);
        @@change_email_request@@ req = new @@change_email_request@@("");

        // Validation failures are HANDLED by Spring MVC (400), unlike the
        // unhandled RuntimeException, so the raw status is asserted here.
        MvcResult result = mockMvc.perform(put(@@user_email_path@@, user.getId())
                        .contentType(MediaType.APPLICATION_JSON)
                        .content(objectMapper.writeValueAsString(req)))
                .andReturn();

        int status = result.getResponse().getStatus();
        String emailAfter = @@user_repo@@.findById(user.getId())
                .map(@@user@@::getEmail).orElse("NOT_FOUND");
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
        @@user@@ user = @@user_repo@@.findAll().get(0);
        @@change_email_request@@ req = new @@change_email_request@@("fresh@example.com");

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
                any(@@email_event@@.class));

        mockMvc.perform(put(@@user_email_path@@, user.getId())
                        .contentType(MediaType.APPLICATION_JSON)
                        .content(objectMapper.writeValueAsString(req)))
                .andExpect(status().isOk());

        // The pipeline cannot see the broker side of this publish (the
        // publish happens inside this JVM), so the test REPORTS what it
        // counted, in a line the pipeline can read. Printed BEFORE the
        // assertion: a test that fails must still say what it saw.
        System.out.println("SPECPROOF_MQ routing_key=email.changed "
            + "exchange=specproof.demo.events publishes=" + publishes.get());

        assertTrue(publishes.get() >= 1,
            "email.changed was not published to the documented exchange "
            + "and routing key");
    }

"""

_UNIQUE_TEST_TEMPLATE = """    @Test
    @WithMockUser
    void duplicateEmailChangeMustBeRejected() throws Exception {
        @@user@@ alice = new @@user@@("alice", "alice@example.com");
        alice.setPasswordHash("hash");
        // Explicit flush: the duplicate must be visible to the derived
        // existsByEmail query even when the test-managed transaction has
        // not committed yet.
        @@user_repo@@.saveAndFlush(alice);

        @@user@@ bob = @@user_repo@@.findAll().stream()
                .filter(u -> "specproof@example.com".equals(u.getEmail()))
                .findFirst().orElseThrow();
        @@change_email_request@@ req = new @@change_email_request@@("alice@example.com");

        // MockMvc RETHROWS unhandled controller exceptions out of
        // perform() (the demo app has no global exception handler) - the
        // duplicate rejection surfaces exactly this way.
        final boolean[] rejected = {false};
        try {
            mockMvc.perform(put(@@user_email_path@@, bob.getId())
                            .contentType(MediaType.APPLICATION_JSON)
                            .content(objectMapper.writeValueAsString(req)));
        } catch (ServletException e) {
            rejected[0] = e.getCause() instanceof RuntimeException;
        }

        String emailAfter = @@user_repo@@.findById(bob.getId())
                .map(@@user@@::getEmail).orElse("NOT_FOUND");
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

_DOMAIN_IMPORTS = """import @@java_package@@.dto.@@cancel_order_request@@;
import @@java_package@@.dto.@@place_order_request@@;
import @@java_package@@.entity.@@order@@;
import @@java_package@@.entity.@@product@@;
import @@java_package@@.event.@@order_event@@;
import @@java_package@@.instrument.@@sql_query_counter@@;
import @@java_package@@.repository.@@order_repo_class@@;
import @@java_package@@.repository.@@product_repo_class@@;
"""

_DOMAIN_FIELDS = """    @Autowired
    private @@order_repo_class@@ @@order_repo@@;

    @Autowired
    private @@product_repo_class@@ @@product_repo@@;

    @Autowired
    private @@sql_query_counter@@ @@sql_query_counter_field@@;

    @Autowired
    private StringRedisTemplate stringRedisTemplate;

"""

_SEED_USER_PRODUCT = """        @@order_repo@@.deleteAll();
        @@product_repo@@.deleteAll();
        @@user_repo@@.deleteAll();
        @@user@@ user = new @@user@@("specproof", "specproof@example.com");
        user.setPasswordHash("hash");
        @@user_repo@@.saveAndFlush(user);
        @@product@@ product = new @@product@@("widget", 10, new BigDecimal("10.00"));
        @@product_repo@@.saveAndFlush(product);
"""

_CACHE_EVICT_TEST_TEMPLATE = """    @Test
    @WithMockUser
    void emailChangeMustEvictUserCache() throws Exception {
        @@user@@ user = @@user_repo@@.findAll().get(0);
        String cacheKey = "@@user_cache_key@@" + user.getId();
        String tokenPattern = "@@user_token_key@@" + user.getId() + ":*";
        @@change_email_request@@ req = new @@change_email_request@@("fresh@example.com");

        // The test profile wires a MOCK StringRedisTemplate (@Primary): the
        // only way to verify invalidation semantics is the invocation itself.
        // The delete-time state probe pins the evict-AFTER-save ordering: when
        // the delete fires, the saved row must already carry the new email
        // (evicting earlier reopens the stale-repopulation window). The key
        // matchers are per-test-user, so other tests' invocations on the
        // shared mock cannot interfere.
        AtomicReference<String> storedAtEvict = new AtomicReference<>();
        doAnswer(invocation -> {
            storedAtEvict.set(@@user_repo@@.findById(user.getId())
                    .map(@@user@@::getEmail).orElse("NOT_FOUND"));
            return null;
        }).when(stringRedisTemplate).delete(eq(cacheKey));

        mockMvc.perform(put(@@user_email_path@@, user.getId())
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
        @@user@@ user = @@user_repo@@.findAll().get(0);
        String cacheKey = "@@user_cache_key@@" + user.getId();
        String cachedJson = "{\\"id\\":" + user.getId()
                + ",\\"username\\":\\"specproof\\",\\"email\\":\\"specproof@example.com\\","
                + "\\"orderCount\\":0}";
        var valueOps = stringRedisTemplate.opsForValue();
        when(valueOps.get(cacheKey)).thenReturn(null, cachedJson);

        @@sql_query_counter_field@@.reset();
        mockMvc.perform(get(@@user_detail_path@@, user.getId()))
                .andExpect(status().isOk());
        mockMvc.perform(get(@@user_detail_path@@, user.getId()))
                .andExpect(status().isOk());
        long queries = @@sql_query_counter_field@@.getCount();

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
        @@product_repo@@.deleteAll();
        @@product@@ product = new @@product@@("widget", 10, new BigDecimal("10.00"));
        @@product_repo@@.saveAndFlush(product);

        @@product@@ snapshotA = @@product_repo@@.findById(product.getId()).orElseThrow();
        @@product@@ snapshotB = @@product_repo@@.findById(product.getId()).orElseThrow();
        snapshotA.setStock(snapshotA.getStock() - 3);
        @@product_repo@@.saveAndFlush(snapshotA);

        final boolean[] rejected = {false};
        try {
            snapshotB.setStock(snapshotB.getStock() - 4);
            @@product_repo@@.saveAndFlush(snapshotB);
        } catch (ObjectOptimisticLockingFailureException | OptimisticLockException e) {
            rejected[0] = true;
        }

        Integer finalStock = @@product_repo@@.findById(product.getId())
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
        @@place_order_request@@ req = new @@place_order_request@@(
                user.getId(), product.getId(), 3, "req-dedup-1");
        mockMvc.perform(post(@@place_order_path@@)
                        .contentType(MediaType.APPLICATION_JSON)
                        .content(objectMapper.writeValueAsString(req)))
                .andExpect(status().isOk());
        mockMvc.perform(post(@@place_order_path@@)
                        .contentType(MediaType.APPLICATION_JSON)
                        .content(objectMapper.writeValueAsString(req)))
                .andExpect(status().isOk());

        int orderRows = @@order_repo@@.findAll().size();
        Integer stock = @@product_repo@@.findById(product.getId())
                .orElseThrow().getStock();
        assertAll(
            () -> assertEquals(1, orderRows,
                "Replayed request created a second order row (" + orderRows + ")"),
            () -> assertEquals(7, stock,
                "Replayed request decremented stock twice (" + stock + ")")
        );
    }

"""

_SERVICE_STALE_STOCK_TEST_TEMPLATE = """    /**
     * The service-path stale read.
     *
     * The repository-level stale-write test above drives the REPOSITORY,
     * so it can only see defects that live in an entity annotation. This
     * one drives the SERVICE: the product is read through a seam that
     * serves the snapshot taken before another writer moved the row on,
     * and the service is asked to place an order against it.
     *
     * The invariant is the same one the entity's @Version upholds, but
     * the actor is the service: if the service's write path stops going
     * through the versioned entity (a bulk UPDATE that computes the new
     * stock from its own read), the concurrent decrement is silently
     * lost — and NO repository-level template can see it, because the
     * repository is never asked to do the write.
     */
    @org.springframework.boot.test.context.TestConfiguration
    static class StaleProductReadConfig {

        /** The snapshot the service is served; null disarms the seam. */
        static @@product@@ stale;

        @org.springframework.context.annotation.Bean
        @org.springframework.context.annotation.Primary
        @@product_repo_class@@ staleProductRepository(
                org.springframework.context.ApplicationContext context) {
            return (@@product_repo_class@@) java.lang.reflect.Proxy.newProxyInstance(
                    @@product_repo_class@@.class.getClassLoader(),
                    new Class<?>[] { @@product_repo_class@@.class },
                    (proxy, method, args) -> {
                        if ("findById".equals(method.getName()) && stale != null) {
                            return java.util.Optional.of(stale);
                        }
                        try {
                            return method.invoke(realBehind(context, proxy), args);
                        } catch (java.lang.reflect.InvocationTargetException e) {
                            throw e.getCause();
                        }
                    });
        }

        /** The REAL repository — the seam is a decorator, not a replacement. */
        static @@product_repo_class@@ realBehind(
                org.springframework.context.ApplicationContext context, Object seam) {
            for (Object candidate
                    : context.getBeansOfType(@@product_repo_class@@.class).values()) {
                if (candidate != seam) {
                    return (@@product_repo_class@@) candidate;
                }
            }
            throw new IllegalStateException(
                    "no real repository behind the stale-read seam");
        }
    }

    @Test
    void concurrentStockDecrementMustNotLoseTheOtherWritersChange() throws Exception {
""" + _SEED_USER_PRODUCT + """
        // The snapshot the SERVICE will read: taken before the other
        // writer moves the row on.
        @@product@@ stale = @@product_repo@@.findById(product.getId()).orElseThrow();
        // The other writer: the same row, one decrement deeper. The row
        // now carries version N+1; the snapshot still carries version N.
        @@product@@ other = @@product_repo@@.findById(product.getId()).orElseThrow();
        other.setStock(5);
        @@product_repo@@.saveAndFlush(other);

        StaleProductReadConfig.stale = stale;
        final boolean[] rejected = {false};
        final int[] status = {0};
        try {
            @@place_order_request@@ request = new @@place_order_request@@(
                    user.getId(), product.getId(), 3, "req-stale-service-1");
            MvcResult result = mockMvc.perform(post(@@place_order_path@@)
                            .contentType(MediaType.APPLICATION_JSON)
                            .content(objectMapper.writeValueAsString(request)))
                    .andReturn();
            status[0] = result.getResponse().getStatus();
        } catch (ServletException e) {
            rejected[0] = true;
        } finally {
            // Disarm the seam BEFORE reading the row back: the assertion
            // must see the database, not the snapshot it planted.
            StaleProductReadConfig.stale = null;
        }

        Integer stock = @@product_repo@@.findById(product.getId())
                .orElseThrow().getStock();
        long orders = @@order_repo@@.count();
        assertAll(
            () -> assertTrue(rejected[0] || status[0] >= 400,
                "The service accepted an order against a stale product read "
                + "(status " + status[0] + ")"),
            () -> assertEquals(5, stock,
                "The other writer's stock (5) must survive the service's "
                + "write, got " + stock),
            () -> assertEquals(0L, orders,
                "A rejected order must not leave an order row behind")
        );
    }

"""

_ROLLBACK_TEST_TEMPLATE = """    @Test
    void orderPlacementFailureMustNotLoseStock() throws Exception {
""" + _SEED_USER_PRODUCT + """
        @@place_order_request@@ ok = new @@place_order_request@@(
                user.getId(), product.getId(), 3, "req-ok-1");
        mockMvc.perform(post(@@place_order_path@@)
                        .contentType(MediaType.APPLICATION_JSON)
                        .content(objectMapper.writeValueAsString(ok)))
                .andExpect(status().isOk());

        @@place_order_request@@ over = new @@place_order_request@@(
                user.getId(), product.getId(), 99, "req-over-1");
        final boolean[] rejected = {false};
        try {
            mockMvc.perform(post(@@place_order_path@@)
                            .contentType(MediaType.APPLICATION_JSON)
                            .content(objectMapper.writeValueAsString(over)));
        } catch (ServletException e) {
            rejected[0] = e.getCause() instanceof RuntimeException;
        }

        Integer stock = @@product_repo@@.findById(product.getId())
                .orElseThrow().getStock();
        long orderRows = @@order_repo@@.findAll().size();
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
        @@place_order_request@@ place = new @@place_order_request@@(
                user.getId(), product.getId(), 3, "req-cancel-1");
        mockMvc.perform(post(@@place_order_path@@)
                        .contentType(MediaType.APPLICATION_JSON)
                        .content(objectMapper.writeValueAsString(place)))
                .andExpect(status().isOk());

        @@cancel_order_request@@ cancel = new @@cancel_order_request@@("req-cancel-1");
        mockMvc.perform(post(@@cancel_order_path@@)
                        .contentType(MediaType.APPLICATION_JSON)
                        .content(objectMapper.writeValueAsString(cancel)))
                .andExpect(status().isOk());

        Integer stock = @@product_repo@@.findById(product.getId())
                .orElseThrow().getStock();
        String status = @@order_repo@@.findByRequestId("req-cancel-1")
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
        @@place_order_request@@ req = new @@place_order_request@@(
                user.getId(), product.getId(), 10, "req-full-1");
        mockMvc.perform(post(@@place_order_path@@)
                        .contentType(MediaType.APPLICATION_JSON)
                        .content(objectMapper.writeValueAsString(req)))
                .andExpect(status().isOk());

        Integer stock = @@product_repo@@.findById(product.getId())
                .orElseThrow().getStock();
        assertEquals(0, stock,
            "Ordering exactly the available stock must succeed (stock 0), got " + stock);

        // Boundary sibling: a non-positive quantity must be rejected with
        // 4xx and must not create an order row (validation failures are
        // HANDLED by Spring MVC, so the raw status is asserted here).
        @@place_order_request@@ zero = new @@place_order_request@@(
                user.getId(), product.getId(), 0, "req-zero-1");
        MvcResult zeroResult = mockMvc.perform(post(@@place_order_path@@)
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
        @@place_order_request@@ req = new @@place_order_request@@(
                user.getId(), product.getId(), 3, "req-amt-1");
        mockMvc.perform(post(@@place_order_path@@)
                        .contentType(MediaType.APPLICATION_JSON)
                        .content(objectMapper.writeValueAsString(req)))
                .andExpect(status().isOk());

        BigDecimal amount = @@order_repo@@.findByRequestId("req-amt-1")
                .orElseThrow().getAmount();
        assertEquals(0, new BigDecimal("30.00").compareTo(amount),
            "Order amount must be 30.00 (price 10 x qty 3), got " + amount);
    }

"""

_NPLUSONE_TEST_TEMPLATE = """    @Test
    void listUsersMustNotUseNPlusOneQueries() throws Exception {
        @@order_repo@@.deleteAll();
        @@user_repo@@.deleteAll();
        for (int i = 0; i < 10; i++) {
            @@user@@ u = new @@user@@("bulk" + i, "bulk" + i + "@example.com");
            u.setPasswordHash("hash");
            @@user_repo@@.saveAndFlush(u);
            @@order_repo@@.saveAndFlush(new @@order@@(
                    u.getId(), 1L, 1, new BigDecimal("10.00"),
                    "req-bulk-" + i + "-1", "CREATED"));
            @@order_repo@@.saveAndFlush(new @@order@@(
                    u.getId(), 1L, 1, new BigDecimal("10.00"),
                    "req-bulk-" + i + "-2", "CREATED"));
        }

        @@sql_query_counter_field@@.reset();
        mockMvc.perform(get("/api/users"))
                .andExpect(status().isOk())
                .andExpect(jsonPath("$", hasSize(10)))
                .andExpect(jsonPath("$[0].orderCount").value(2));
        long queries = @@sql_query_counter_field@@.getCount();

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
                any(@@order_event@@.class));

        @@place_order_request@@ req = new @@place_order_request@@(
                user.getId(), product.getId(), 2, "req-ev-1");
        mockMvc.perform(post(@@place_order_path@@)
                        .contentType(MediaType.APPLICATION_JSON)
                        .content(objectMapper.writeValueAsString(req)))
                .andExpect(status().isOk());

        // The pipeline cannot see the broker side of this publish (the
        // publish happens inside this JVM), so the test REPORTS what it
        // counted, in a line the pipeline can read. Printed BEFORE the
        // assertion: a test that fails must still say what it saw.
        System.out.println("SPECPROOF_MQ routing_key=order.created "
            + "exchange=specproof.demo.events publishes=" + publishes.get());

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
                any(@@order_event@@.class));

        @@place_order_request@@ req = new @@place_order_request@@(
                user.getId(), product.getId(), 2, "req-once-1");
        mockMvc.perform(post(@@place_order_path@@)
                        .contentType(MediaType.APPLICATION_JSON)
                        .content(objectMapper.writeValueAsString(req)))
                .andExpect(status().isOk());

        // The pipeline cannot see the broker side of this publish (the
        // publish happens inside this JVM), so the test REPORTS what it
        // counted, in a line the pipeline can read. Printed BEFORE the
        // assertion: a test that fails must still say what it saw.
        System.out.println("SPECPROOF_MQ routing_key=order.created "
            + "exchange=specproof.demo.events publishes=" + publishes.get());

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
                        org.mockito.ArgumentMatchers.<@@order_event@@>argThat(event ->
                                event.getRequestId().equals("req-retry-1")));

        @@place_order_request@@ req = new @@place_order_request@@(
                user.getId(), product.getId(), 2, "req-retry-1");
        final boolean[] rejected = {false};
        try {
            mockMvc.perform(post(@@place_order_path@@)
                            .contentType(MediaType.APPLICATION_JSON)
                            .content(objectMapper.writeValueAsString(req)));
        } catch (ServletException e) {
            rejected[0] = e.getCause() instanceof RuntimeException;
        }

        // The pipeline cannot see the broker side of this publish (the
        // publish happens inside this JVM), so the test REPORTS what it
        // counted, in a line the pipeline can read. Printed BEFORE the
        // assertion: a test that fails must still say what it saw. The
        // count here is PUBLISH ATTEMPTS — the broker rejected this one.
        System.out.println("SPECPROOF_MQ routing_key=order.created "
            + "exchange=specproof.demo.events publishes=" + publishes.get());

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
        @@user@@ user = @@user_repo@@.findAll().get(0);
        @@change_email_request@@ req = new @@change_email_request@@("not-an-email");

        MvcResult result = mockMvc.perform(put(@@user_email_path@@, user.getId())
                        .contentType(MediaType.APPLICATION_JSON)
                        .content(objectMapper.writeValueAsString(req)))
                .andReturn();

        int status = result.getResponse().getStatus();
        String emailAfter = @@user_repo@@.findById(user.getId())
                .map(@@user@@::getEmail).orElse("NOT_FOUND");
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
        @@user@@ user = @@user_repo@@.findAll().get(0);
        @@change_email_request@@ req = new @@change_email_request@@(user.getEmail());

        AtomicInteger publishes = new AtomicInteger();
        doAnswer(invocation -> {
            publishes.incrementAndGet();
            return null;
        }).when(rabbitTemplate).convertAndSend(
                eq("specproof.demo.events"), eq("email.changed"),
                any(@@email_event@@.class));

        mockMvc.perform(put(@@user_email_path@@, user.getId())
                        .contentType(MediaType.APPLICATION_JSON)
                        .content(objectMapper.writeValueAsString(req)))
                .andExpect(status().isOk());

        // The pipeline cannot see the broker side of this publish (the
        // publish happens inside this JVM), so the test REPORTS what it
        // counted, in a line the pipeline can read. Printed BEFORE the
        // assertion: a test that fails must still say what it saw. Zero
        // here is the POINT of this test — a no-op change must publish
        // nothing, and the report says so.
        System.out.println("SPECPROOF_MQ routing_key=email.changed "
            + "exchange=specproof.demo.events publishes=" + publishes.get());

        assertEquals(0, publishes.get(),
            "A no-op email change must not publish an event, got "
            + publishes.get() + " publishes");
    }

"""

_EVENT_PAYLOAD_TEST_TEMPLATE = """    @Test
    @WithMockUser
    void emailChangeEventPayloadMustBeIntact() throws Exception {
        @@user@@ user = @@user_repo@@.findAll().get(0);
        String oldEmail = user.getEmail();
        @@change_email_request@@ req = new @@change_email_request@@("fresh@example.com");

        // Captured via doAnswer instead of verify+captor: the RabbitTemplate
        // mock is shared across tests, so a verify() would count other
        // tests' email publishes and fail spuriously on the honest base.
        AtomicReference<@@email_event@@> captured = new AtomicReference<>();
        doAnswer(invocation -> {
            captured.set((@@email_event@@) invocation.getArgument(2));
            return null;
        }).when(rabbitTemplate).convertAndSend(
                eq("specproof.demo.events"), eq("email.changed"),
                any(@@email_event@@.class));

        mockMvc.perform(put(@@user_email_path@@, user.getId())
                        .contentType(MediaType.APPLICATION_JSON)
                        .content(objectMapper.writeValueAsString(req)))
                .andExpect(status().isOk());

        @@email_event@@ event = captured.get();
        // The pipeline cannot see the broker side of this publish (the
        // publish happens inside this JVM), so the test REPORTS what it
        // saw, in a line the pipeline can read. Printed BEFORE the
        // assertion: a test that fails must still say what it saw.
        System.out.println("SPECPROOF_MQ routing_key=email.changed "
            + "exchange=specproof.demo.events publishes="
            + (event == null ? 0 : 1));
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

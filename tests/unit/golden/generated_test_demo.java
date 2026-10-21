package com.specproof.demo;

import com.fasterxml.jackson.databind.ObjectMapper;
import com.specproof.demo.config.TestMockBeansConfig;
import com.specproof.demo.dto.ChangeEmailRequest;
import com.specproof.demo.entity.User;
import com.specproof.demo.event.EmailChangedEvent;
import com.specproof.demo.repository.UserRepository;
import com.specproof.demo.dto.CancelOrderRequest;
import com.specproof.demo.dto.PlaceOrderRequest;
import com.specproof.demo.entity.CustomerOrder;
import com.specproof.demo.entity.Product;
import com.specproof.demo.event.OrderCreatedEvent;
import com.specproof.demo.instrument.SqlQueryCounter;
import com.specproof.demo.repository.CustomerOrderRepository;
import com.specproof.demo.repository.ProductRepository;

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

    @Autowired
    private CustomerOrderRepository orderRepository;

    @Autowired
    private ProductRepository productRepository;

    @Autowired
    private SqlQueryCounter sqlQueryCounter;

    @Autowired
    private StringRedisTemplate stringRedisTemplate;

    @Test
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

    @Test
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

    @Test
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

    @Test
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

    @Test
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

    @Test
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

    @Test
    @WithMockUser
    void getUserMustUseCacheAside() throws Exception {
        User user = userRepository.findAll().get(0);
        String cacheKey = "user:cache:" + user.getId();
        String cachedJson = "{\"id\":" + user.getId()
                + ",\"username\":\"specproof\",\"email\":\"specproof@example.com\","
                + "\"orderCount\":0}";
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

    @Test
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

    /**
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
        static Product stale;

        @org.springframework.context.annotation.Bean
        @org.springframework.context.annotation.Primary
        ProductRepository staleProductRepository(
                org.springframework.context.ApplicationContext context) {
            return (ProductRepository) java.lang.reflect.Proxy.newProxyInstance(
                    ProductRepository.class.getClassLoader(),
                    new Class<?>[] { ProductRepository.class },
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
        static ProductRepository realBehind(
                org.springframework.context.ApplicationContext context, Object seam) {
            for (Object candidate
                    : context.getBeansOfType(ProductRepository.class).values()) {
                if (candidate != seam) {
                    return (ProductRepository) candidate;
                }
            }
            throw new IllegalStateException(
                    "no real repository behind the stale-read seam");
        }
    }

    @Test
    void concurrentStockDecrementMustNotLoseTheOtherWritersChange() throws Exception {
        orderRepository.deleteAll();
        productRepository.deleteAll();
        userRepository.deleteAll();
        User user = new User("specproof", "specproof@example.com");
        user.setPasswordHash("hash");
        userRepository.saveAndFlush(user);
        Product product = new Product("widget", 10, new BigDecimal("10.00"));
        productRepository.saveAndFlush(product);

        // The snapshot the SERVICE will read: taken before the other
        // writer moves the row on.
        Product stale = productRepository.findById(product.getId()).orElseThrow();
        // The other writer: the same row, one decrement deeper. The row
        // now carries version N+1; the snapshot still carries version N.
        Product other = productRepository.findById(product.getId()).orElseThrow();
        other.setStock(5);
        productRepository.saveAndFlush(other);

        StaleProductReadConfig.stale = stale;
        final boolean[] rejected = {false};
        final int[] status = {0};
        try {
            PlaceOrderRequest request = new PlaceOrderRequest(
                    user.getId(), product.getId(), 3, "req-stale-service-1");
            MvcResult result = mockMvc.perform(post("/api/orders")
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

        Integer stock = productRepository.findById(product.getId())
                .orElseThrow().getStock();
        long orders = orderRepository.count();
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

    @Test
    void duplicateOrderRequestMustBeDeduped() throws Exception {
        orderRepository.deleteAll();
        productRepository.deleteAll();
        userRepository.deleteAll();
        User user = new User("specproof", "specproof@example.com");
        user.setPasswordHash("hash");
        userRepository.saveAndFlush(user);
        Product product = new Product("widget", 10, new BigDecimal("10.00"));
        productRepository.saveAndFlush(product);

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

    @Test
    void orderPlacementFailureMustNotLoseStock() throws Exception {
        orderRepository.deleteAll();
        productRepository.deleteAll();
        userRepository.deleteAll();
        User user = new User("specproof", "specproof@example.com");
        user.setPasswordHash("hash");
        userRepository.saveAndFlush(user);
        Product product = new Product("widget", 10, new BigDecimal("10.00"));
        productRepository.saveAndFlush(product);

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

    @Test
    void cancelOrderMustRestock() throws Exception {
        orderRepository.deleteAll();
        productRepository.deleteAll();
        userRepository.deleteAll();
        User user = new User("specproof", "specproof@example.com");
        user.setPasswordHash("hash");
        userRepository.saveAndFlush(user);
        Product product = new Product("widget", 10, new BigDecimal("10.00"));
        productRepository.saveAndFlush(product);

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

    @Test
    void fullStockOrderMustBeAllowed() throws Exception {
        orderRepository.deleteAll();
        productRepository.deleteAll();
        userRepository.deleteAll();
        User user = new User("specproof", "specproof@example.com");
        user.setPasswordHash("hash");
        userRepository.saveAndFlush(user);
        Product product = new Product("widget", 10, new BigDecimal("10.00"));
        productRepository.saveAndFlush(product);

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

    @Test
    void orderAmountMustEqualUnitPriceTimesQuantity() throws Exception {
        orderRepository.deleteAll();
        productRepository.deleteAll();
        userRepository.deleteAll();
        User user = new User("specproof", "specproof@example.com");
        user.setPasswordHash("hash");
        userRepository.saveAndFlush(user);
        Product product = new Product("widget", 10, new BigDecimal("10.00"));
        productRepository.saveAndFlush(product);

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

    @Test
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

    @Test
    void orderCreatedEventMustGoToExpectedRoutingKey() throws Exception {
        orderRepository.deleteAll();
        productRepository.deleteAll();
        userRepository.deleteAll();
        User user = new User("specproof", "specproof@example.com");
        user.setPasswordHash("hash");
        userRepository.saveAndFlush(user);
        Product product = new Product("widget", 10, new BigDecimal("10.00"));
        productRepository.saveAndFlush(product);

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

    @Test
    void orderCreatedEventPublishedExactlyOnce() throws Exception {
        orderRepository.deleteAll();
        productRepository.deleteAll();
        userRepository.deleteAll();
        User user = new User("specproof", "specproof@example.com");
        user.setPasswordHash("hash");
        userRepository.saveAndFlush(user);
        Product product = new Product("widget", 10, new BigDecimal("10.00"));
        productRepository.saveAndFlush(product);

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

    @Test
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

}

package com.specproof.demo.probe;

import com.specproof.demo.dto.ChangeEmailRequest;
import com.specproof.demo.dto.PlaceOrderRequest;
import com.specproof.demo.entity.Product;
import com.specproof.demo.entity.User;
import com.specproof.demo.repository.CustomerOrderRepository;
import com.specproof.demo.repository.ProductRepository;
import com.specproof.demo.repository.UserRepository;
import com.specproof.demo.service.OrderService;
import com.specproof.demo.service.UserService;
import java.math.BigDecimal;
import org.junit.jupiter.api.AfterEach;
import org.junit.jupiter.api.BeforeEach;
import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.context.annotation.Import;
import org.springframework.test.context.ActiveProfiles;

/**
 * Reliability probe test (case 97/98/100 scaffolding).
 *
 * Exactly one method runs per invocation — the differential pipeline selects
 * it via -Dtest=SpecProofProbeTest#&lt;method&gt;. Every method drives the
 * service, records what the CountingRabbitTemplate observed, and leaves the
 * machine-readable artifact in target/specproof-probe.json (@AfterEach).
 * The methods deliberately make NO verdict assertions: the base-vs-head
 * comparison happens in the pipeline against the case's probe_expectation.
 *
 * DB isolation: the probe runs on its OWN file-based H2 database
 * (specproof-probe), so its seeding never rewrites the specproof-test
 * database that the generated-test differential dump reads as evidence.
 */
@SpringBootTest(properties = {
        "spring.datasource.url=jdbc:h2:file:./target/h2/specproof-probe;DB_CLOSE_DELAY=-1",
})
@ActiveProfiles("test")
@Import(SpecProofProbeConfig.class)
public class SpecProofProbeTest {

    @Autowired
    private UserRepository userRepository;

    @Autowired
    private ProductRepository productRepository;

    @Autowired
    private CustomerOrderRepository orderRepository;

    @Autowired
    private UserService userService;

    @Autowired
    private OrderService orderService;

    @BeforeEach
    void setUp() {
        orderRepository.deleteAll();
        productRepository.deleteAll();
        userRepository.deleteAll();
        User user = new User("specproof", "specproof@example.com");
        user.setPasswordHash("hash");
        userRepository.saveAndFlush(user);
        Product product = new Product("widget", 10, new BigDecimal("10.00"));
        productRepository.saveAndFlush(product);
        ProbePublishRecorder.clear();
    }

    @AfterEach
    void writeArtifact() {
        ProbePublishRecorder.writeArtifact();
    }

    /** Case 97: one injected broker failure; base fast-fails, head retries. */
    @Test
    void brokerFailureRetry() {
        User user = userRepository.findAll().get(0);
        Product product = productRepository.findAll().get(0);
        System.setProperty(CountingRabbitTemplate.FAIL_ONCE_PROPERTY, "true");
        PlaceOrderRequest request = new PlaceOrderRequest(
                user.getId(), product.getId(), 2, "probe-retry-1");
        try {
            orderService.placeOrder(request);
        } catch (RuntimeException expected) {
            // Base: the failed publish surfaces to the caller (fast fail).
            ProbePublishRecorder.markOutcome("error");
        }
    }

    /** Case 98: no-op email change; base returns early, head proceeds. */
    @Test
    void noopEmailChangePublish() {
        User user = userRepository.findAll().get(0);
        ChangeEmailRequest request = new ChangeEmailRequest(user.getEmail());
        try {
            userService.changeEmail(user.getId(), request);
        } catch (RuntimeException expected) {
            // Head (early return removed): the change falls through to the
            // existsByEmail guard and errors instead of returning cleanly.
            ProbePublishRecorder.markOutcome("error");
        }
    }

    /** Case 100: fresh email change; capture the published payload timestamp. */
    @Test
    void eventTimestampIntact() {
        User user = userRepository.findAll().get(0);
        ChangeEmailRequest request = new ChangeEmailRequest("probe-fresh@example.com");
        try {
            userService.changeEmail(user.getId(), request);
        } catch (RuntimeException expected) {
            ProbePublishRecorder.markOutcome("error");
        }
    }
}

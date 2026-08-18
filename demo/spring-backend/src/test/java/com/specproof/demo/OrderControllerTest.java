package com.specproof.demo;

import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.get;
import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.post;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.jsonPath;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.status;

import com.fasterxml.jackson.databind.ObjectMapper;
import com.specproof.demo.config.TestMockBeansConfig;
import com.specproof.demo.dto.CancelOrderRequest;
import com.specproof.demo.dto.PlaceOrderRequest;
import com.specproof.demo.entity.CustomerOrder;
import com.specproof.demo.entity.Product;
import com.specproof.demo.entity.User;
import com.specproof.demo.instrument.SqlQueryCounter;
import com.specproof.demo.repository.CustomerOrderRepository;
import com.specproof.demo.repository.ProductRepository;
import com.specproof.demo.repository.UserRepository;
import java.math.BigDecimal;
import org.junit.jupiter.api.BeforeEach;
import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.autoconfigure.web.servlet.AutoConfigureMockMvc;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.context.annotation.Import;
import org.springframework.http.MediaType;
import org.springframework.test.context.ActiveProfiles;
import org.springframework.test.web.servlet.MockMvc;

@SpringBootTest
@AutoConfigureMockMvc
@ActiveProfiles("test")
@Import(TestMockBeansConfig.class)
public class OrderControllerTest {

    @Autowired
    private MockMvc mockMvc;

    @Autowired
    private ObjectMapper objectMapper;

    @Autowired
    private UserRepository userRepository;

    @Autowired
    private ProductRepository productRepository;

    @Autowired
    private CustomerOrderRepository orderRepository;

    @Autowired
    private SqlQueryCounter queryCounter;

    private User user;
    private Product product;

    @BeforeEach
    void setUp() {
        orderRepository.deleteAll();
        productRepository.deleteAll();
        userRepository.deleteAll();
        user = new User("orderuser", "orderuser@example.com");
        user.setPasswordHash("hash");
        userRepository.save(user);
        product = new Product("widget", 10, new BigDecimal("10.00"));
        productRepository.save(product);
    }

    @Test
    void placeOrderShouldDecrementStockAndCreateOrder() throws Exception {
        PlaceOrderRequest req = new PlaceOrderRequest(
                user.getId(), product.getId(), 3, "req-1");

        mockMvc.perform(post("/api/orders")
                        .contentType(MediaType.APPLICATION_JSON)
                        .content(objectMapper.writeValueAsString(req)))
                .andExpect(status().isOk())
                .andExpect(jsonPath("$.requestId").value("req-1"))
                .andExpect(jsonPath("$.stockRemaining").value(7));

        Product stored = productRepository.findById(product.getId()).orElseThrow();
        org.junit.jupiter.api.Assertions.assertEquals(7, stored.getStock());
        org.junit.jupiter.api.Assertions.assertEquals(
                1, orderRepository.findAll().size());
    }

    @Test
    void duplicateRequestIdShouldBeIdempotent() throws Exception {
        PlaceOrderRequest req = new PlaceOrderRequest(
                user.getId(), product.getId(), 3, "req-idem");

        for (int i = 0; i < 2; i++) {
            mockMvc.perform(post("/api/orders")
                            .contentType(MediaType.APPLICATION_JSON)
                            .content(objectMapper.writeValueAsString(req)))
                    .andExpect(status().isOk());
        }

        Product stored = productRepository.findById(product.getId()).orElseThrow();
        org.junit.jupiter.api.Assertions.assertEquals(7, stored.getStock());
        org.junit.jupiter.api.Assertions.assertEquals(
                1, orderRepository.findAll().size());
    }

    @Test
    void insufficientStockShouldBeRejected() throws Exception {
        PlaceOrderRequest req = new PlaceOrderRequest(
                user.getId(), product.getId(), 99, "req-over");

        final boolean[] rejected = {false};
        try {
            mockMvc.perform(post("/api/orders")
                            .contentType(MediaType.APPLICATION_JSON)
                            .content(objectMapper.writeValueAsString(req)));
        } catch (jakarta.servlet.ServletException e) {
            rejected[0] = e.getCause() instanceof RuntimeException;
        }
        org.junit.jupiter.api.Assertions.assertTrue(rejected[0],
                "Oversized order was accepted — no rejection exception was raised");

        Product stored = productRepository.findById(product.getId()).orElseThrow();
        org.junit.jupiter.api.Assertions.assertEquals(10, stored.getStock());
    }

    @Test
    void cancelOrderShouldRestock() throws Exception {
        PlaceOrderRequest place = new PlaceOrderRequest(
                user.getId(), product.getId(), 3, "req-cancel");
        mockMvc.perform(post("/api/orders")
                        .contentType(MediaType.APPLICATION_JSON)
                        .content(objectMapper.writeValueAsString(place)))
                .andExpect(status().isOk());

        CancelOrderRequest cancel = new CancelOrderRequest("req-cancel");
        mockMvc.perform(post("/api/orders/cancel")
                        .contentType(MediaType.APPLICATION_JSON)
                        .content(objectMapper.writeValueAsString(cancel)))
                .andExpect(status().isOk())
                .andExpect(jsonPath("$.stockRemaining").value(10));

        CustomerOrder stored = orderRepository.findByRequestId("req-cancel").orElseThrow();
        org.junit.jupiter.api.Assertions.assertEquals("CANCELLED", stored.getStatus());
    }

    @Test
    void listUsersShouldAvoidNPlusOneQueries() throws Exception {
        for (int i = 0; i < 10; i++) {
            User u = new User("bulk" + i, "bulk" + i + "@example.com");
            u.setPasswordHash("hash");
            userRepository.save(u);
            for (int j = 0; j < 2; j++) {
                orderRepository.save(new CustomerOrder(
                        u.getId(), product.getId(), 1,
                        new BigDecimal("10.00"), "req-bulk-" + i + "-" + j, "CREATED"));
            }
        }

        queryCounter.reset();
        mockMvc.perform(get("/api/users"))
                .andExpect(status().isOk())
                .andExpect(jsonPath("$.length()").value(11));

        org.junit.jupiter.api.Assertions.assertTrue(
                queryCounter.getCount() <= 3,
                "GET /api/users used " + queryCounter.getCount()
                + " queries; expected a batched implementation (<= 3)");
    }
}

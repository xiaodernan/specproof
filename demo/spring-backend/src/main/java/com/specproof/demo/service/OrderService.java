package com.specproof.demo.service;

import com.specproof.demo.dto.CancelOrderRequest;
import com.specproof.demo.dto.OrderResponse;
import com.specproof.demo.dto.PlaceOrderRequest;
import com.specproof.demo.entity.CustomerOrder;
import com.specproof.demo.entity.Product;
import com.specproof.demo.entity.User;
import com.specproof.demo.event.OrderCreatedEvent;
import com.specproof.demo.repository.CustomerOrderRepository;
import com.specproof.demo.repository.ProductRepository;
import com.specproof.demo.repository.UserRepository;
import java.math.BigDecimal;
import org.slf4j.Logger;
import org.slf4j.LoggerFactory;
import org.springframework.amqp.rabbit.core.RabbitTemplate;
import org.springframework.stereotype.Service;
import org.springframework.transaction.annotation.Transactional;

@Service
public class OrderService {

    private static final Logger log = LoggerFactory.getLogger(OrderService.class);
    private static final String ORDER_EXCHANGE = "specproof.demo.events";
    private static final String ORDER_ROUTING_KEY = "order.created";
    private static final String STATUS_CREATED = "CREATED";
    private static final String STATUS_CANCELLED = "CANCELLED";

    private final UserRepository userRepository;
    private final ProductRepository productRepository;
    private final CustomerOrderRepository orderRepository;
    private final RabbitTemplate rabbitTemplate;

    public OrderService(
            UserRepository userRepository,
            ProductRepository productRepository,
            CustomerOrderRepository orderRepository,
            RabbitTemplate rabbitTemplate) {
        this.userRepository = userRepository;
        this.productRepository = productRepository;
        this.orderRepository = orderRepository;
        this.rabbitTemplate = rabbitTemplate;
    }

    /**
     * Place an order. Idempotent per requestId: replaying the same request
     * returns the existing order without a second stock decrement. The
     * stock decrement is guarded by the product's @Version optimistic lock.
     */
    @Transactional
    public OrderResponse placeOrder(PlaceOrderRequest request) {
        if (orderRepository.existsByRequestId(request.getRequestId())) {
            CustomerOrder existing = orderRepository.findByRequestId(request.getRequestId())
                    .orElseThrow(() -> new RuntimeException(
                            "Order not found: " + request.getRequestId()));
            Product product = productRepository.findById(existing.getProductId())
                    .orElseThrow(() -> new RuntimeException(
                            "Product not found: " + existing.getProductId()));
            return toResponse(existing, product.getStock());
        }

        User user = userRepository.findById(request.getUserId())
                .orElseThrow(() -> new RuntimeException(
                        "User not found: " + request.getUserId()));
        Product product = productRepository.findById(request.getProductId())
                .orElseThrow(() -> new RuntimeException(
                        "Product not found: " + request.getProductId()));

        if (request.getQuantity() > product.getStock()) {
            throw new RuntimeException(
                    "Insufficient stock for product " + product.getId());
        }

        product.setStock(product.getStock() - request.getQuantity());
        productRepository.saveAndFlush(product);

        BigDecimal amount = product.getPrice()
                .multiply(BigDecimal.valueOf(request.getQuantity()));
        CustomerOrder order = new CustomerOrder(
                user.getId(),
                product.getId(),
                request.getQuantity(),
                amount,
                request.getRequestId(),
                STATUS_CREATED);
        orderRepository.save(order);

        OrderCreatedEvent event = new OrderCreatedEvent(
                order.getId(), product.getId(), request.getQuantity(), request.getRequestId());
        rabbitTemplate.convertAndSend(ORDER_EXCHANGE, ORDER_ROUTING_KEY, event);
        log.info("Order {} placed for product {} (qty {})",
                order.getId(), product.getId(), request.getQuantity());

        return toResponse(order, product.getStock());
    }

    /**
     * Cancel a created order: the reserved stock is returned to the
     * product. Cancelling an already-cancelled order is a no-op.
     */
    @Transactional
    public OrderResponse cancelOrder(CancelOrderRequest request) {
        CustomerOrder order = orderRepository.findByRequestId(request.getRequestId())
                .orElseThrow(() -> new RuntimeException(
                        "Order not found: " + request.getRequestId()));
        Product product = productRepository.findById(order.getProductId())
                .orElseThrow(() -> new RuntimeException(
                        "Product not found: " + order.getProductId()));

        if (STATUS_CREATED.equals(order.getStatus())) {
            product.setStock(product.getStock() + order.getQuantity());
            productRepository.saveAndFlush(product);
            order.setStatus(STATUS_CANCELLED);
            orderRepository.save(order);
            log.info("Order {} cancelled, stock restocked for product {}",
                    order.getId(), product.getId());
        }

        return toResponse(order, product.getStock());
    }

    private OrderResponse toResponse(CustomerOrder order, Integer stockRemaining) {
        return new OrderResponse(
                order.getId(),
                order.getProductId(),
                order.getQuantity(),
                order.getRequestId(),
                order.getAmount(),
                stockRemaining);
    }
}

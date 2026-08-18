package com.specproof.demo.service;

import com.specproof.demo.dto.ChangeEmailRequest;
import com.specproof.demo.dto.UserResponse;
import com.specproof.demo.entity.User;
import com.specproof.demo.event.EmailChangedEvent;
import com.specproof.demo.repository.CustomerOrderRepository;
import com.specproof.demo.repository.UserRepository;
import com.fasterxml.jackson.databind.ObjectMapper;
import java.util.HashMap;
import java.util.List;
import java.util.Map;
import java.util.concurrent.TimeUnit;
import org.slf4j.Logger;
import org.slf4j.LoggerFactory;
import org.springframework.amqp.rabbit.core.RabbitTemplate;
import org.springframework.data.redis.core.StringRedisTemplate;
import org.springframework.stereotype.Service;
import org.springframework.transaction.annotation.Transactional;

@Service
public class UserService {

    private static final Logger log = LoggerFactory.getLogger(UserService.class);
    private static final String TOKEN_PREFIX = "token:user:";
    private static final String USER_CACHE_PREFIX = "user:cache:";
    private static final long USER_CACHE_TTL_SECONDS = 300L;

    private final UserRepository userRepository;
    private final CustomerOrderRepository orderRepository;
    private final ObjectMapper objectMapper;
    private final StringRedisTemplate redisTemplate;
    private final RabbitTemplate rabbitTemplate;

    public UserService(
            UserRepository userRepository,
            CustomerOrderRepository orderRepository,
            ObjectMapper objectMapper,
            StringRedisTemplate redisTemplate,
            RabbitTemplate rabbitTemplate) {
        this.userRepository = userRepository;
        this.orderRepository = orderRepository;
        this.objectMapper = objectMapper;
        this.redisTemplate = redisTemplate;
        this.rabbitTemplate = rabbitTemplate;
    }

    public UserResponse getUser(Long id) {
        String cacheKey = USER_CACHE_PREFIX + id;
        try {
            String cached = redisTemplate.opsForValue().get(cacheKey);
            if (cached != null) {
                return objectMapper.readValue(cached, UserResponse.class);
            }
        } catch (Exception e) {
            log.warn("User cache read failed for {}: {}", id, e.getMessage());
        }

        User user = userRepository.findById(id)
                .orElseThrow(() -> new RuntimeException("User not found: " + id));
        long orderCount = orderRepository.countOrdersForUser(id);
        UserResponse response = new UserResponse(
                user.getId(), user.getUsername(), user.getEmail(), (int) orderCount);

        try {
            redisTemplate.opsForValue().set(
                    cacheKey,
                    objectMapper.writeValueAsString(response),
                    USER_CACHE_TTL_SECONDS,
                    TimeUnit.SECONDS);
        } catch (Exception e) {
            log.warn("User cache write failed for {}: {}", id, e.getMessage());
        }
        return response;
    }

    /**
     * List every user with their order count, served in two queries
     * (users + one aggregate count). Per-user query loops are the N+1
     * regression the differential query-count test rejects.
     */
    public List<UserResponse> getUsers() {
        List<User> users = userRepository.findAllByOrderByIdAsc();
        Map<Long, Long> orderCounts = new HashMap<>();
        for (Object[] row : orderRepository.countOrdersGroupedByUser()) {
            orderCounts.put((Long) row[0], (Long) row[1]);
        }
        return users.stream()
                .map(u -> new UserResponse(
                        u.getId(), u.getUsername(), u.getEmail(),
                        orderCounts.getOrDefault(u.getId(), 0L).intValue()))
                .toList();
    }

    @Transactional
    public UserResponse changeEmail(Long userId, ChangeEmailRequest request) {
        User user = userRepository.findById(userId)
                .orElseThrow(() -> new RuntimeException("User not found: " + userId));

        String oldEmail = user.getEmail();
        String newEmail = request.getNewEmail();


        if (userRepository.existsByEmail(newEmail)) {
            throw new RuntimeException("Email already in use: " + newEmail);
        }

        user.setEmail(newEmail);
        userRepository.save(user);

        evictUserCache(userId);
        invalidateOldTokens(userId);

        EmailChangedEvent event = new EmailChangedEvent(userId, oldEmail, newEmail);
        rabbitTemplate.convertAndSend(
                "specproof.demo.events",
                "email.changed",
                event);
        log.info("Email changed for user {}: {} -> {}", userId, oldEmail, newEmail);

        return new UserResponse(user.getId(), user.getUsername(), newEmail);
    }

    private void evictUserCache(Long userId) {
        redisTemplate.delete(USER_CACHE_PREFIX + userId);
        log.info("Evicted user cache for user {}", userId);
    }

    private void invalidateOldTokens(Long userId) {
        String pattern = TOKEN_PREFIX + userId + ":*";
        var keys = redisTemplate.keys(pattern);
        if (keys != null && !keys.isEmpty()) {
            redisTemplate.delete(keys);
            log.info("Invalidated {} tokens for user {}", keys.size(), userId);
        }
    }
}

package com.specproof.demo.service;

import com.specproof.demo.dto.ChangeEmailRequest;
import com.specproof.demo.dto.UserResponse;
import com.specproof.demo.entity.User;
import com.specproof.demo.event.EmailChangedEvent;
import com.specproof.demo.repository.UserRepository;
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

    private final UserRepository userRepository;
    private final StringRedisTemplate redisTemplate;
    private final RabbitTemplate rabbitTemplate;

    public UserService(
            UserRepository userRepository,
            StringRedisTemplate redisTemplate,
            RabbitTemplate rabbitTemplate) {
        this.userRepository = userRepository;
        this.redisTemplate = redisTemplate;
        this.rabbitTemplate = rabbitTemplate;
    }

    public UserResponse getUser(Long id) {
        User user = userRepository.findById(id)
                .orElseThrow(() -> new RuntimeException("User not found: " + id));
        return new UserResponse(user.getId(), user.getUsername(), user.getEmail());
    }

    @Transactional
    public UserResponse changeEmail(Long userId, ChangeEmailRequest request) {
        User user = userRepository.findById(userId)
                .orElseThrow(() -> new RuntimeException("User not found: " + userId));

        String oldEmail = user.getEmail();
        String newEmail = request.getNewEmail();

        if (oldEmail.equals(newEmail)) {
            return new UserResponse(user.getId(), user.getUsername(), user.getEmail());
        }

        if (userRepository.existsByEmail(newEmail)) {
            throw new RuntimeException("Email already in use: " + newEmail);
        }

        user.setEmail(newEmail);
        userRepository.save(user);

        invalidateOldTokens(userId);

        EmailChangedEvent event = new EmailChangedEvent(userId, oldEmail, newEmail);
        rabbitTemplate.convertAndSend(
                "specproof.demo.events",
                "email.changed",
                event);
        log.info("Email changed for user {}: {} -> {}", userId, oldEmail, newEmail);

        return new UserResponse(user.getId(), user.getUsername(), newEmail);
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

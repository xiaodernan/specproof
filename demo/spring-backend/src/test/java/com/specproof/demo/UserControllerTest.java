package com.specproof.demo;

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
import com.specproof.demo.config.TestMockBeansConfig;
import org.springframework.context.annotation.Import;

@SpringBootTest
@AutoConfigureMockMvc
@ActiveProfiles("test")
@Import(TestMockBeansConfig.class)
public class UserControllerTest {

    @Autowired
    private MockMvc mockMvc;

    @Autowired
    private UserRepository userRepository;

    @Autowired
    private ObjectMapper objectMapper;

    @Autowired
    private org.springframework.data.redis.core.StringRedisTemplate redisTemplate;

    @BeforeEach
    void setUp() {
        userRepository.deleteAll();
        User user = new User("testuser", "test@example.com");
        user.setPasswordHash("hash");
        userRepository.save(user);
    }

    @Test
    @WithMockUser
    void changeEmailWhenAuthenticatedShouldSucceed() throws Exception {
        User user = userRepository.findAll().get(0);
        ChangeEmailRequest req = new ChangeEmailRequest("new@example.com");

        mockMvc.perform(put("/api/users/{id}/email", user.getId())
                        .contentType(MediaType.APPLICATION_JSON)
                        .content(objectMapper.writeValueAsString(req)))
                .andExpect(status().isOk())
                .andExpect(jsonPath("$.email").value("new@example.com"));
    }

    @Test
    void changeEmailWithoutAuthShouldReturn401() throws Exception {
        User user = userRepository.findAll().get(0);
        ChangeEmailRequest req = new ChangeEmailRequest("new@example.com");

        mockMvc.perform(put("/api/users/{id}/email", user.getId())
                        .contentType(MediaType.APPLICATION_JSON)
                        .content(objectMapper.writeValueAsString(req)))
                .andExpect(status().isUnauthorized());
    }

    @Test
    void getUserShouldUseCacheAside() throws Exception {
        User user = userRepository.findAll().get(0);
        String cacheKey = "user:cache:" + user.getId();
        String cachedJson = "{\"id\":" + user.getId()
                + ",\"username\":\"testuser\",\"email\":\"test@example.com\",\"orderCount\":0}";
        var valueOps = redisTemplate.opsForValue();
        org.mockito.Mockito.when(valueOps.get(cacheKey)).thenReturn(null, cachedJson);

        mockMvc.perform(get("/api/users/{id}", user.getId()))
                .andExpect(status().isOk())
                .andExpect(jsonPath("$.email").value("test@example.com"));
        mockMvc.perform(get("/api/users/{id}", user.getId()))
                .andExpect(status().isOk());

        org.mockito.Mockito.verify(valueOps, org.mockito.Mockito.times(1))
                .set(org.mockito.ArgumentMatchers.eq(cacheKey),
                        org.mockito.ArgumentMatchers.anyString(),
                        org.mockito.ArgumentMatchers.anyLong(),
                        org.mockito.ArgumentMatchers.any(java.util.concurrent.TimeUnit.class));
    }

    @Test
    @WithMockUser
    void changeEmailToDuplicateShouldFail() throws Exception {
        User alice = new User("alice", "alice@example.com");
        alice.setPasswordHash("hash");
        userRepository.save(alice);

        User bob = userRepository.findByEmail("test@example.com").orElseThrow();
        ChangeEmailRequest req = new ChangeEmailRequest("alice@example.com");

        // MockMvc RETHROWS unhandled controller exceptions out of
        // perform() (the demo app has no global exception handler) — the
        // duplicate rejection surfaces exactly this way.
        final boolean[] rejected = {false};
        try {
            mockMvc.perform(put("/api/users/{id}/email", bob.getId())
                            .contentType(MediaType.APPLICATION_JSON)
                            .content(objectMapper.writeValueAsString(req)));
        } catch (jakarta.servlet.ServletException e) {
            rejected[0] = e.getCause() instanceof RuntimeException;
        }

        String emailAfter = userRepository.findById(bob.getId())
                .map(User::getEmail).orElse("NOT_FOUND");
        org.junit.jupiter.api.Assertions.assertAll(
            () -> org.junit.jupiter.api.Assertions.assertTrue(rejected[0],
                    "Duplicate email was ACCEPTED: no rejection exception was raised"),
            () -> org.junit.jupiter.api.Assertions.assertEquals(
                    "test@example.com", emailAfter,
                    "DB STATE VIOLATION: duplicate email change was persisted")
        );
    }
}

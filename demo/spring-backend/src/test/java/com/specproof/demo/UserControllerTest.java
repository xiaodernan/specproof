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

@SpringBootTest
@AutoConfigureMockMvc
@ActiveProfiles("test")
public class UserControllerTest {

    @Autowired
    private MockMvc mockMvc;

    @Autowired
    private UserRepository userRepository;

    @Autowired
    private ObjectMapper objectMapper;

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
    @WithMockUser
    void changeEmailToDuplicateShouldFail() throws Exception {
        User alice = new User("alice", "alice@example.com");
        alice.setPasswordHash("hash");
        userRepository.save(alice);

        User bob = userRepository.findByEmail("test@example.com").orElseThrow();
        ChangeEmailRequest req = new ChangeEmailRequest("alice@example.com");

        mockMvc.perform(put("/api/users/{id}/email", bob.getId())
                        .contentType(MediaType.APPLICATION_JSON)
                        .content(objectMapper.writeValueAsString(req)))
                .andExpect(status().is5xxServerError());
    }
}

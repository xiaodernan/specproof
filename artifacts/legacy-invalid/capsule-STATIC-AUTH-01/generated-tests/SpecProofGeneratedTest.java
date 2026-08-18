package com.specproof.demo;

import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.*;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.*;

import com.fasterxml.jackson.databind.ObjectMapper;
import com.specproof.demo.config.TestMockBeansConfig;
import com.specproof.demo.dto.ChangeEmailRequest;
import com.specproof.demo.entity.User;
import com.specproof.demo.repository.UserRepository;
import org.junit.jupiter.api.BeforeEach;
import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.autoconfigure.web.servlet.AutoConfigureMockMvc;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.context.annotation.Import;
import org.springframework.http.MediaType;
import org.springframework.security.test.context.support.WithMockUser;
import org.springframework.test.context.ActiveProfiles;
import org.springframework.test.web.servlet.MockMvc;

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

    @BeforeEach
    void setUp() {
        userRepository.deleteAll();
        User user = new User("specproof", "specproof@example.com");
        user.setPasswordHash("hash");
        userRepository.save(user);
    }

    @Test
    void changeEmailWithoutAuthShouldReturn401() throws Exception {
        User user = userRepository.findAll().get(0);
        String emailBefore = user.getEmail();
        ChangeEmailRequest req = new ChangeEmailRequest("attacker@evil.com");

        mockMvc.perform(put("/api/users/{id}/email", user.getId())
                        .contentType(MediaType.APPLICATION_JSON)
                        .content(objectMapper.writeValueAsString(req)))
                .andExpect(status().isUnauthorized());

        // DB state: email must NOT have changed
        String emailAfter = userRepository.findById(user.getId())
                .map(User::getEmail).orElse("NOT_FOUND");
        if (!emailBefore.equals(emailAfter)) {
            throw new AssertionError(
                "DB STATE CHANGED: email was '" + emailBefore
                + "', now '" + emailAfter + "'. "
                + "Unauthenticated request must not modify data.");
        }
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
}

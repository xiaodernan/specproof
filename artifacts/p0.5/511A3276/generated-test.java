package com.specproof.demo;

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
import org.springframework.test.context.ActiveProfiles;
import org.springframework.test.web.servlet.MockMvc;
import org.springframework.test.web.servlet.MvcResult;

import static org.junit.jupiter.api.Assertions.assertAll;
import static org.junit.jupiter.api.Assertions.assertEquals;
import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.put;

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

    private User testUser;
    private String originalEmail;

    @BeforeEach
    void setUp() {
        userRepository.deleteAll();
        User user = new User("testuser", "original@example.com");
        user.setPasswordHash("hash");
        testUser = userRepository.save(user);
        originalEmail = testUser.getEmail();
    }

    @Test
    void putUpdateEmailWithoutAuthentication_shouldReturn401AndNotModifyDatabase() throws Exception {
        ChangeEmailRequest request = new ChangeEmailRequest("newemail@example.com");
        String requestJson = objectMapper.writeValueAsString(request);

        MvcResult result = mockMvc.perform(put("/api/users/{id}/email", testUser.getId())
                .contentType(MediaType.APPLICATION_JSON)
                .content(requestJson))
                .andReturn();

        int status = result.getResponse().getStatus();
        User reloadedUser = userRepository.findById(testUser.getId()).orElseThrow();

        assertAll(
            () -> assertEquals(401, status, "Expected 401 UNAUTHORIZED but got " + status),
            () -> assertEquals(originalEmail, reloadedUser.getEmail(),
                "DB STATE VIOLATION: email was '" + originalEmail
                + "' before request, now '" + reloadedUser.getEmail()
                + "'. Unauthenticated request MUST NOT modify data.")
        );
    }
}
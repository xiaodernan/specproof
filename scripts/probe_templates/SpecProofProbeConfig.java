package com.specproof.demo.probe;

import org.mockito.Mockito;
import org.springframework.amqp.rabbit.connection.ConnectionFactory;
import org.springframework.amqp.rabbit.core.RabbitTemplate;
import org.springframework.boot.test.context.TestConfiguration;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Primary;
import org.springframework.data.redis.core.StringRedisTemplate;

/**
 * Test-scoped configuration for the reliability probes.
 *
 * RabbitAutoConfiguration is excluded by the test profile, so the demo's own
 * RabbitMQConfig still needs a ConnectionFactory to construct its (unused)
 * RabbitTemplate; the mock supplies it. The counting wrapper below is the
 * @Primary RabbitTemplate the services receive. The StringRedisTemplate mock
 * keeps changeEmail's cache/token side effects inert so the probe measures
 * publish behavior alone.
 */
@TestConfiguration
public class SpecProofProbeConfig {

    @Bean
    @Primary
    public ConnectionFactory specProofProbeConnectionFactory() {
        return Mockito.mock(ConnectionFactory.class);
    }

    @Bean
    @Primary
    public RabbitTemplate specProofProbeRabbitTemplate() {
        return new CountingRabbitTemplate();
    }

    @Bean
    @Primary
    public StringRedisTemplate specProofProbeStringRedisTemplate() {
        return Mockito.mock(StringRedisTemplate.class);
    }
}

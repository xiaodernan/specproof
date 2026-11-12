package dev.specproof.controlplane.config;

import static org.assertj.core.api.Assertions.assertThat;

import java.io.IOException;
import java.time.Duration;
import java.util.List;

import org.junit.jupiter.api.Test;
import org.springframework.boot.autoconfigure.AutoConfigurations;
import org.springframework.boot.autoconfigure.data.redis.RedisAutoConfiguration;
import org.springframework.boot.autoconfigure.data.redis.RedisProperties;
import org.springframework.boot.autoconfigure.data.redis.RedisRepositoriesAutoConfiguration;
import org.springframework.boot.env.YamlPropertySourceLoader;
import org.springframework.boot.test.context.runner.ApplicationContextRunner;
import org.springframework.core.env.PropertySource;
import org.springframework.core.io.ClassPathResource;
import org.springframework.data.redis.connection.RedisConnectionFactory;
import org.springframework.data.redis.connection.lettuce.LettuceConnectionFactory;

/**
 * The bound the deployment DECLARES must be the bound the client USES.
 *
 * <p>The Python gate ({@code tests/unit/test_the_control_plane_bounds_its_cache_backend.py})
 * reads {@code application.yml} statically: it catches a deleted or wrong
 * configuration line. It cannot tell whether that line reaches the object
 * that actually opens the socket — and a line that reaches nothing is a
 * comment.</p>
 *
 * <p>This leg closes that half for the COMMAND timeout: it loads the SHIPPED
 * {@code application.yml}, lets Spring Boot build the same connection factory
 * the running service builds, and reads the timeout off the Lettuce client
 * configuration — the object that will actually time the command. No Redis
 * server is needed (the client is configured without connecting), so this leg
 * runs wherever the unit tests run.</p>
 *
 * <p>The CONNECT timeout is asserted at the hand-over point: Spring Boot's own
 * {@link RedisProperties}. What the framework does with that value afterwards
 * is the framework's business; what this project owes is that the number it
 * declares reaches it.</p>
 */
class RedisTimeoutWiringTests {

    private static final Duration EXPECTED = Duration.ofMillis(50);

    private ApplicationContextRunner contextWithTheShippedConfiguration() throws IOException {
        List<PropertySource<?>> sources = new YamlPropertySourceLoader()
                .load("application", new ClassPathResource("application.yml"));
        return new ApplicationContextRunner()
                .withInitializer(context -> sources.forEach(
                        context.getEnvironment().getPropertySources()::addLast))
                .withConfiguration(AutoConfigurations.of(
                        RedisAutoConfiguration.class));
    }

    @Test
    void theCommandTimeoutTheDeploymentDeclaresReachesTheClient() throws IOException {
        contextWithTheShippedConfiguration().run(context -> {
            assertThat(context).hasNotFailed();
            RedisConnectionFactory factory = context.getBean(RedisConnectionFactory.class);
            assertThat(factory).isInstanceOf(LettuceConnectionFactory.class);
            Duration commandTimeout = ((LettuceConnectionFactory) factory)
                    .getClientConfiguration().getCommandTimeout();
            assertThat(commandTimeout)
                    .as("the command timeout the client will use")
                    .isEqualTo(EXPECTED);
        });
    }

    @Test
    void theConnectTimeoutTheDeploymentDeclaresReachesTheFramework() throws IOException {
        contextWithTheShippedConfiguration().run(context -> {
            assertThat(context).hasNotFailed();
            RedisProperties properties = context.getBean(RedisProperties.class);
            assertThat(properties.getConnectTimeout())
                    .as("the connect timeout handed to the client builder")
                    .isEqualTo(EXPECTED);
        });
    }
}

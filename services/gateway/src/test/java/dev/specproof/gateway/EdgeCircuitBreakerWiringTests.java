package dev.specproof.gateway;

import static org.assertj.core.api.Assertions.assertThat;

import java.io.IOException;
import java.time.Duration;
import java.util.List;

import org.junit.jupiter.api.Test;
import org.springframework.boot.autoconfigure.AutoConfigurations;
import org.springframework.boot.env.YamlPropertySourceLoader;
import org.springframework.boot.test.context.runner.ApplicationContextRunner;
import org.springframework.core.env.PropertySource;
import org.springframework.core.io.ClassPathResource;

import io.github.resilience4j.circuitbreaker.CircuitBreaker;
import io.github.resilience4j.circuitbreaker.CircuitBreakerConfig;
import io.github.resilience4j.circuitbreaker.CircuitBreakerRegistry;
import io.github.resilience4j.springboot3.circuitbreaker.autoconfigure.CircuitBreakerAutoConfiguration;

/**
 * The thresholds the edge DECLARES must be the thresholds its breaker USES.
 *
 * <p>The declaration exists: {@code application.yml} carries the two
 * resilience4j instances (one per plane) with an explicit window, minimum
 * call count, failure rate, open window and half-open probe count. What was
 * NOT proven anywhere is that those numbers REACH the instance the filter
 * uses — the behaviour leg builds its own registry and asserts behaviour, so
 * a configuration that stopped being read would leave it green.</p>
 *
 * <p>This leg loads the SHIPPED {@code application.yml}, lets Spring Boot
 * build the same registry the running edge builds, and reads the thresholds
 * off the instance the filter uses ({@code specproof-edge}). No upstream is
 * needed, so it runs wherever the unit tests run.</p>
 */
class EdgeCircuitBreakerWiringTests {

    private ApplicationContextRunner contextWithTheShippedConfiguration() throws IOException {
        List<PropertySource<?>> sources = new YamlPropertySourceLoader()
                .load("application", new ClassPathResource("application.yml"));
        return new ApplicationContextRunner()
                .withInitializer(context -> sources.forEach(
                        context.getEnvironment().getPropertySources()::addLast))
                .withConfiguration(AutoConfigurations.of(CircuitBreakerAutoConfiguration.class));
    }

    @Test
    void theDeclaredThresholdsReachTheInstanceTheFilterUses() throws IOException {
        contextWithTheShippedConfiguration().run(context -> {
            assertThat(context).hasNotFailed();
            CircuitBreakerRegistry registry = context.getBean(CircuitBreakerRegistry.class);
            CircuitBreaker breaker = registry.circuitBreaker(
                    dev.specproof.gateway.filter.EdgeCircuitBreakerGatewayFilterFactory.DEFAULT_INSTANCE);
            CircuitBreakerConfig config = breaker.getCircuitBreakerConfig();
            assertThat(config.getSlidingWindowSize()).isEqualTo(10);
            assertThat(config.getMinimumNumberOfCalls()).isEqualTo(5);
            assertThat(config.getFailureRateThreshold()).isEqualTo(50f);
            assertThat(Duration.ofMillis(config.getWaitIntervalFunctionInOpenState().apply(1)))
                    .isEqualTo(Duration.ofSeconds(30));
            assertThat(config.getPermittedNumberOfCallsInHalfOpenState()).isEqualTo(3);
        });
    }

    @Test
    void theDefaultsWouldHaveBeenMuchMorePermissive() throws IOException {
        // Why the declaration matters, in the library's own numbers.
        //
        // Resilience4j's defaults are a 100-call window, 100 calls before
        // anything is evaluated, and 60 seconds open. A quiet edge can send
        // fewer than 100 requests in the window, so the breaker would never
        // open -- and when it did, it would hold traffic for a minute. The
        // declared numbers open after five failures and release after thirty
        // seconds.
        CircuitBreakerConfig defaults = CircuitBreakerConfig.ofDefaults();
        assertThat(defaults.getMinimumNumberOfCalls()).isEqualTo(100);
        assertThat(Duration.ofMillis(defaults.getWaitIntervalFunctionInOpenState().apply(1)))
                .isEqualTo(Duration.ofSeconds(60));
    }
}

package dev.specproof.controlplane.config;

import com.fasterxml.jackson.databind.ObjectMapper;
import dev.specproof.controlplane.cache.InMemoryJobReadCache;
import dev.specproof.controlplane.cache.JobCacheBreaker;
import dev.specproof.controlplane.cache.JobQueryService;
import dev.specproof.controlplane.cache.JobReadCache;
import dev.specproof.controlplane.cache.NoopJobReadCache;
import dev.specproof.controlplane.cache.RedisJobReadCache;
import dev.specproof.controlplane.repository.VerificationJobViewRepository;
import io.micrometer.core.instrument.MeterRegistry;
import org.springframework.boot.autoconfigure.condition.ConditionalOnProperty;
import org.springframework.boot.context.properties.EnableConfigurationProperties;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.data.redis.core.StringRedisTemplate;

import java.time.Duration;

/**
 * Wires the job facade cache. Exactly one {@link JobReadCache} bean exists in a
 * context — the three {@code @ConditionalOnProperty} beans below are mutually
 * exclusive, so the service never has to guess which backend it got.
 */
@Configuration
@EnableConfigurationProperties(JobCacheProperties.class)
public class JobCacheConfig {

    @Bean
    public JobCacheBreaker jobCacheBreaker(MeterRegistry meters, JobCacheProperties props) {
        return new JobCacheBreaker(meters, props.getBreakerFailureThreshold(),
                Duration.ofMillis(props.getBreakerWaitMs()));
    }

    @Bean
    @ConditionalOnProperty(name = "specproof.control-plane.job-cache.backend",
            havingValue = "redis", matchIfMissing = true)
    public JobReadCache redisJobReadCache(StringRedisTemplate redis,
                                          ObjectMapper mapper,
                                          MeterRegistry meters,
                                          JobCacheBreaker breaker) {
        return new RedisJobReadCache(redis, mapper, meters, breaker);
    }

    @Bean
    @ConditionalOnProperty(name = "specproof.control-plane.job-cache.backend", havingValue = "memory")
    public JobReadCache memoryJobReadCache() {
        return new InMemoryJobReadCache();
    }

    @Bean
    @ConditionalOnProperty(name = "specproof.control-plane.job-cache.backend", havingValue = "off")
    public JobReadCache offJobReadCache() {
        return new NoopJobReadCache();
    }

    @Bean
    public JobQueryService jobQueryService(VerificationJobViewRepository jobs,
                                           JobReadCache cache,
                                           MeterRegistry meters) {
        return new JobQueryService(jobs, cache, meters);
    }
}

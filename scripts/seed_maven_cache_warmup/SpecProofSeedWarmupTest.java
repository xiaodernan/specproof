package com.specproof.demo;

import org.junit.jupiter.api.Test;

import static org.junit.jupiter.api.Assertions.assertTrue;

/**
 * One-test warmup class used only by scripts/seed_maven_cache.sh.
 *
 * The seeder copies it into a throwaway copy of demo/spring-backend and runs
 * `mvn -Dtest=SpecProofSeedWarmupTest test` with the network on, then the
 * same phase OFFLINE against the volume alone and asserts the surefire
 * summary says one test ran. Without a test that actually executes, Maven
 * never resolves the surefire JUnit-platform provider and the offline check
 * would pass vacuously (#530) while the sandbox's differential still dies in
 * dependency resolution.
 */
class SpecProofSeedWarmupTest {
    @Test
    void warm() {
        assertTrue(true);
    }
}

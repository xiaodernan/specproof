package dev.specproof.discovery;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;
import org.springframework.cloud.netflix.eureka.server.EnableEurekaServer;

/**
 * The SpecProof service registry.
 *
 * <p>Every other SpecProof microservice (the edge gateway, the control plane,
 * and any future domain service) registers here and is then resolved by logical
 * name — {@code gateway}, {@code control-plane} — rather than a hard-coded
 * host:port. That is what lets the gateway route to the control plane without
 * knowing where it runs, and what lets instances be added or moved without
 * touching caller configuration.</p>
 *
 * <p>This node is a <em>standalone</em> registry: it does not register with a
 * peer ({@code eureka.client.register-with-eureka=false}) and does not pull a
 * peer registry ({@code fetch-registry=false}). A single node is therefore
 * sufficient for local development and CI; a production topology would run two
 * or three peers pointing at each other.</p>
 */
@SpringBootApplication
@EnableEurekaServer
public class DiscoveryServerApplication {

    public static void main(String[] args) {
        SpringApplication.run(DiscoveryServerApplication.class, args);
    }
}

package dev.specproof.gateway;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;

/**
 * The edge of SpecProof.
 *
 * <p>Two planes answer HTTP here: the Spring Boot control plane (tenant,
 * user, job-facade and webhook management — the business source of truth) and
 * the Python agent runtime (the product API the web UI talks to). Which plane
 * owns which path is written down in exactly one place, the route table in
 * {@code application.yml}, and
 * {@code tests/unit/test_gateway_route_table_covers_every_plane_route.py}
 * keeps that table honest.
 *
 * <p>There is no service registry here on purpose: one edge in front of two
 * planes is not a cluster, and this project's own commercialization plan
 * (风险 7) rejects splitting the product into a dozen deployment units before
 * the split is earned. The route table is the whole of the "who answers
 * what" story, and it is a file a person can read.
 */
@SpringBootApplication
public class GatewayApplication {

    public static void main(String[] args) {
        SpringApplication.run(GatewayApplication.class, args);
    }
}

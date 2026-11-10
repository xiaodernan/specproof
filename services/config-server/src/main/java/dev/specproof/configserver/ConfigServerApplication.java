package dev.specproof.configserver;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;
import org.springframework.cloud.config.server.EnableConfigServer;

/**
 * The distributed-config microservice for the SpecProof edge.
 *
 * <p>Spring Cloud's textbook microservice seam: one config server owns the
 * externalized settings for every other service, and the gateway (#1604 moved
 * its tunables into a {@code @ConfigurationProperties} bean precisely so they
 * could be served from here). This module is a file-backed (native) backend —
 * no git repository, no broker — so it boots offline and is unit-testable.
 *
 * <p>Why a separate service and not just application.yml: a config server is the
 * thing that lets {@code GatewayProperties} be identical across dev / staging /
 * prod without re-building the image. That is the "config in the environment"
 * twelve-factor step #1604 stopped short of; this closes it.
 */
@SpringBootApplication
@EnableConfigServer
public class ConfigServerApplication {

  public static void main(String[] args) {
    SpringApplication.run(ConfigServerApplication.class, args);
  }
}

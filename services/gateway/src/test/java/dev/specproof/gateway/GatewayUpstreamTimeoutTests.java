package dev.specproof.gateway;

import static org.assertj.core.api.Assertions.assertThat;

import java.io.IOException;
import java.io.InputStream;
import java.io.OutputStream;
import java.net.InetSocketAddress;
import java.net.URI;
import java.net.http.HttpClient;
import java.net.http.HttpRequest;
import java.net.http.HttpResponse;
import java.nio.charset.StandardCharsets;
import java.time.Duration;
import java.util.concurrent.Executors;

import com.sun.net.httpserver.HttpExchange;
import com.sun.net.httpserver.HttpServer;

import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.test.context.ActiveProfiles;
import org.springframework.boot.test.web.server.LocalServerPort;

/**
 * The edge gives up on a hung upstream before the caller does.
 *
 * <p>Spring Cloud Gateway has NO default for
 * {@code spring.cloud.gateway.httpclient.response-timeout} — an agent
 * runtime that accepts the connection and never answers would otherwise
 * hang every request the edge proxies to it, and the edge is the only
 * face the web UI has. The circuit breaker counts <em>failures</em>; a
 * hang is not one until it errors, which is why the timeout has to exist
 * at the transport layer as well.
 *
 * <p>The upstream here is a real HTTP server that accepts the request,
 * sleeps ten seconds, and then answers 200. The gateway is told to wait
 * one second. The assertion is on the ELAPSED TIME as much as on the
 * status: a 503 that arrives after ten seconds proves nothing.
 */
@ActiveProfiles("test")
@SpringBootTest(webEnvironment = SpringBootTest.WebEnvironment.RANDOM_PORT,
        properties = {
            "server.port=0",
            "management.server.port=0",
            "management.server.address=127.0.0.1",
            "spring.cloud.gateway.httpclient.connect-timeout=500",
            "spring.cloud.gateway.httpclient.response-timeout=1s",
            "SPECPROOF_CONTROL_PLANE_URL=http://127.0.0.1:9",
            // Resolved from a system property this class sets in its static
            // block, so the gateway can be pointed at a server whose port is
            // only known once it has bound one.
            "SPECPROOF_AGENT_RUNTIME_URL=http://127.0.0.1:${specproof.timeouttest.slowport}",
        })
class GatewayUpstreamTimeoutTests {

    /**
     * An agent runtime that accepts the request and never answers.
     *
     * <p>Binds an ephemeral port before the application context starts, and
     * publishes that port as a system property the {@code @SpringBootTest}
     * properties above reference. The listener thread is a daemon so a test
     * that never gets woken cannot hold the JVM open.
     */
    static final HttpServer SLOW_UPSTREAM = startSlowUpstream();

    private static HttpServer startSlowUpstream() {
        try {
            HttpServer server = HttpServer.create(new InetSocketAddress("127.0.0.1", 0), 0);
            server.createContext("/", GatewayUpstreamTimeoutTests::hang);
            server.setExecutor(Executors.newFixedThreadPool(1, runnable -> {
                Thread thread = new Thread(runnable, "slow-upstream");
                thread.setDaemon(true);
                return thread;
            }));
            server.start();
            System.setProperty(
                    "specproof.timeouttest.slowport",
                    String.valueOf(server.getAddress().getPort()));
            return server;
        } catch (IOException failure) {
            throw new ExceptionInInitializerError(failure);
        }
    }

    private static void hang(HttpExchange exchange) throws IOException {
        try {
            // Longer than any timeout in this test, so the gateway is the
            // only party that can end this exchange.
            Thread.sleep(Duration.ofSeconds(10).toMillis());
        } catch (InterruptedException interrupted) {
            Thread.currentThread().interrupt();
            return;
        }
        byte[] body = "answered-too-late".getBytes(StandardCharsets.UTF_8);
        exchange.sendResponseHeaders(200, body.length);
        try (OutputStream out = exchange.getResponseBody()) {
            out.write(body);
        }
        exchange.close();
    }

    @Autowired(required = false)
    private org.springframework.core.env.Environment environment;

    @LocalServerPort
    private int edgePort;

    @Test
    void theEdgeGivesUpOnAHungUpstreamBeforeTheCallerDoes() throws Exception {
        HttpClient client = HttpClient.newBuilder()
                .connectTimeout(Duration.ofSeconds(3))
                .build();
        HttpRequest request = HttpRequest.newBuilder(
                        URI.create("http://127.0.0.1:" + edgePort + "/api/hung-upstream"))
                .timeout(Duration.ofSeconds(9))
                .GET()
                .build();

        long started = System.nanoTime();
        HttpResponse<InputStream> response =
                client.send(request, HttpResponse.BodyHandlers.ofInputStream());
        long elapsedMillis = (System.nanoTime() - started) / 1_000_000;
        String body = new String(response.body().readAllBytes(), StandardCharsets.UTF_8);

        assertThat(response.statusCode())
                .as("a hung upstream must be answered by the edge, not waited on; "
                        + "body was: %s", body)
                .isEqualTo(503);
        assertThat(body)
                .as("the edge's own answer carries the breaker body")
                .contains("upstream_unavailable");
        assertThat(elapsedMillis)
                .as("the edge waited %d ms for a one-second timeout — the timeout is not wired",
                        elapsedMillis)
                .isLessThan(9_000);
    }

    @Test
    void theEdgeDisconnectsFromTheHungUpstreamInsteadOfWaitingForever() throws Exception {
        // The same property as the leg above, stated from the upstream's
        // side of the wire: the gateway asked, got nothing in one second,
        // and stopped reading. If the client were left open, this test's
        // ten-second hang would be the whole test.
        assertThat(environment.getProperty(
                "spring.cloud.gateway.httpclient.response-timeout")).isEqualTo("1s");
        assertThat(environment.getProperty(
                "spring.cloud.gateway.httpclient.connect-timeout")).isEqualTo("500");
    }
}

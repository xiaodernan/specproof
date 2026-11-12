package dev.specproof.controlplane.api;

import org.springframework.beans.factory.ObjectProvider;
import org.springframework.core.env.Environment;
import org.springframework.cloud.client.discovery.DiscoveryClient;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.RestController;

import java.util.ArrayList;
import java.util.LinkedHashMap;
import java.util.List;
import java.util.Map;

/**
 * Readiness probe for the compose healthchecks and load balancers — and the
 * place where the control plane says what it can see of the cluster it now
 * belongs to.
 *
 * <p>Since #1631 the control plane is a Spring Cloud participant: it imports
 * the shared config server and it registers itself with the registry. A
 * participation nobody can see is a participation nobody can trust, so the
 * probe reports the two facts an operator would otherwise have to go looking
 * for:</p>
 *
 * <ul>
 *   <li><b>discovery</b> — whether a discovery client is on the classpath at
 *       all, and whether this service shows up in the registry it can see.
 *       The registry's view is read from the client's local cache
 *       ({@code getServices()} does not make a network call), so a downed
 *       registry cannot make the health endpoint slow.</li>
 *   <li><b>config_import</b> — the declared config import, verbatim. It is
 *       the <i>declaration</i>, not a claim that a fetch succeeded: the
 *       difference matters, because a successful import and an optional one
 *       that found nothing look identical from inside the process.</li>
 * </ul>
 *
 * <p>The probe stays a readiness probe: {@code status} is still {@code ok}
 * whenever the process can serve, because a downed registry is not a reason
 * to take this instance out of rotation — the edge reaches it by name
 * anyway.</p>
 */
@RestController
public class HealthController {

    /** The name this service registers under (application.yml). */
    private static final String SERVICE_NAME = "specproof-control-plane";

    private final ObjectProvider<DiscoveryClient> discoveryClient;
    private final Environment environment;

    public HealthController(ObjectProvider<DiscoveryClient> discoveryClient,
                            Environment environment) {
        this.discoveryClient = discoveryClient;
        this.environment = environment;
    }

    @GetMapping("/health")
    public Map<String, Object> health() {
        Map<String, Object> body = new LinkedHashMap<>();
        body.put("service", SERVICE_NAME);
        body.put("status", "ok");
        body.put("discovery", discovery());
        body.put("config_import", environment.getProperty("spring.config.import"));
        return body;
    }

    private Map<String, Object> discovery() {
        DiscoveryClient client = discoveryClient.getIfAvailable();
        if (client == null) {
            Map<String, Object> absent = new LinkedHashMap<>();
            absent.put("client", "absent");
            absent.put("registered", false);
            return absent;
        }
        List<String> services = new ArrayList<>(client.getServices());
        Map<String, Object> view = new LinkedHashMap<>();
        view.put("client", "discovery");
        view.put("registered", services.contains(SERVICE_NAME));
        view.put("services", services.size());
        return view;
    }
}

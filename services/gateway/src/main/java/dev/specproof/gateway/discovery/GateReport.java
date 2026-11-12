package dev.specproof.gateway.discovery;

import java.util.List;

/**
 * The result of one {@link RouteTableIsomorphismGate} check: does the edge's
 * curated path table and the service registry agree on which services back which
 * paths? Two invariants are checked — path uniqueness within the table, and
 * (when a registry is present) that every route's named {@code service-id} is
 * actually registered.
 */
public final class GateReport {

    private final boolean ok;
    private final boolean registryAvailable;
    private final List<String> duplicatePaths;
    private final List<String> missingServices;
    private final List<String> referencedServices;

    public GateReport(boolean ok,
                      boolean registryAvailable,
                      List<String> duplicatePaths,
                      List<String> missingServices,
                      List<String> referencedServices) {
        this.ok = ok;
        this.registryAvailable = registryAvailable;
        this.duplicatePaths = duplicatePaths;
        this.missingServices = missingServices;
        this.referencedServices = referencedServices;
    }

    public boolean isOk() {
        return ok;
    }

    public boolean registryAvailable() {
        return registryAvailable;
    }

    public boolean hasDuplicates() {
        return !duplicatePaths.isEmpty();
    }

    public List<String> duplicatePaths() {
        return duplicatePaths;
    }

    public List<String> missingServices() {
        return missingServices;
    }

    public List<String> referencedServices() {
        return referencedServices;
    }
}

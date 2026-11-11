package dev.specproof.controlplane.cache;

import dev.specproof.controlplane.entity.VerificationJobView;

import java.time.LocalDateTime;

/**
 * The wire shape of a job row, and the only thing the cache stores.
 *
 * <p>Deliberately NOT the JPA entity: caching a Hibernate-managed instance means
 * caching a proxy graph (and, with {@code @Immutable}, a false promise that the
 * row never changes when the truth is "this process never writes it"). A plain
 * record has exactly the fields the API exposes, so a cache hit and a cache miss
 * serialize to the same JSON — a property {@code JobQueryServiceTest} pins by
 * comparing both paths byte for byte.</p>
 */
public record JobView(
        String id,
        String repoPath,
        String baseRef,
        String headRef,
        String status,
        LocalDateTime createdAt) {

    public static JobView from(VerificationJobView view) {
        return new JobView(
                view.getId(),
                view.getRepoPath(),
                view.getBaseRef(),
                view.getHeadRef(),
                view.getStatus(),
                view.getCreatedAt());
    }
}

package com.specproof.demo.instrument;

import java.util.Map;
import java.util.concurrent.atomic.AtomicLong;
import org.hibernate.resource.jdbc.spi.StatementInspector;
import org.springframework.boot.autoconfigure.orm.jpa.HibernatePropertiesCustomizer;
import org.springframework.stereotype.Component;

/**
 * Counts every SQL statement Hibernate executes, exposed for tests.
 *
 * The differential N+1 tests reset the counter before a scenario and
 * assert an upper bound afterwards: the honest base serves GET /api/users
 * with two queries, while per-user query loops blow the bound. The
 * counter is instrumentation only — no production path reads it.
 */
@Component
public class SqlQueryCounter implements HibernatePropertiesCustomizer {

    private final AtomicLong count = new AtomicLong();

    @Override
    public void customize(Map<String, Object> hibernateProperties) {
        hibernateProperties.put(
            "hibernate.session_factory.statement_inspector",
            (StatementInspector) sql -> {
                count.incrementAndGet();
                return sql;
            }
        );
    }

    public long getCount() {
        return count.get();
    }

    public void reset() {
        count.set(0);
    }
}

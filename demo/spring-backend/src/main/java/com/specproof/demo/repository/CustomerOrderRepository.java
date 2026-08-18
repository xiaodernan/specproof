package com.specproof.demo.repository;

import com.specproof.demo.entity.CustomerOrder;
import java.util.List;
import java.util.Optional;
import org.springframework.data.jpa.repository.JpaRepository;
import org.springframework.data.jpa.repository.Query;
import org.springframework.data.repository.query.Param;

public interface CustomerOrderRepository extends JpaRepository<CustomerOrder, Long> {

    Optional<CustomerOrder> findByRequestId(String requestId);

    boolean existsByRequestId(String requestId);

    /**
     * Per-user order count in ONE query — the honest base shape. The N+1
     * regressions replace this aggregate with a per-user query loop.
     */
    @Query("select count(o) from CustomerOrder o where o.userId = :userId")
    long countOrdersForUser(@Param("userId") Long userId);

    /**
     * Order counts for every user in ONE aggregate query — the honest base
     * implementation behind GET /api/users.
     */
    @Query("select o.userId, count(o) from CustomerOrder o group by o.userId")
    List<Object[]> countOrdersGroupedByUser();

    @Query("select o from CustomerOrder o where o.userId = :userId")
    List<CustomerOrder> findOrdersByUserId(@Param("userId") Long userId);
}

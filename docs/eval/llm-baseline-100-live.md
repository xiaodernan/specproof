# SpecProof vs 只看 Diff 基线 (Go/No-Go #14)

- 基线模式: LLM (diff + requirement)
- 案例数: 100

| Case | Ground truth | Baseline verdict | Baseline contracts |
|---|---|---|---|
| case-01-auth-bypass | should-detect | MISS | UserController.changeEmail |
| case-02-transactional-removal | should-detect | MISS | UserService.changeEmail |
| case-03-clean-pr | negative | PASS | — |
| case-04-duplicate-email | should-detect | MISS | case04_duplicate_email_not_rejected |
| case-05-token-invalidation | should-detect | MISS | Case05 |
| case-06-schema-break | should-detect | MISS | demo/spring-backend/src/main/java/com/specproof/demo/dto/UserResponse.java |
| case-07-duplicate-event | should-detect | MISS | email-changed-event |
| case-08-transaction-split | should-detect | MISS | UserService.changeEmail |
| case-09-multi-security | should-detect | MISS | UserService.changeEmail |
| case-10-comment-only | negative | PASS | — |
| case-100-rel-event-timestamp-nulled | should-detect | MISS | email.changed |
| case-11-refactor-rename | negative | PASS | — |
| case-12-add-javadoc | negative | PASS | — |
| case-13-annotation-aliased | negative | PASS | — |
| case-14-annotation-moved-to-interface | negative | PASS | — |
| case-15-whitespace-only-diff | negative | PASS | — |
| case-16-preauthorize-role-changed | negative | PASS | — |
| case-17-logic-inversion | should-detect | MISS | UserService.duplicate-email-guard |
| case-18-wrong-routing-key | should-detect | MISS | email.changed |
| case-19-email-corruption | should-detect | MISS | UserService |
| case-20-validation-removed | should-detect | MISS | ChangeEmailRequest |
| case-21-auth-weakened-permitall | should-detect | MISS | change-email-endpoint-requires-authentication |
| case-22-auth-guard-moved-to-dead-helper | should-detect | MISS | change-email-endpoint-requires-authentication |
| case-23-auth-role-tightened | negative | PASS | — |
| case-24-auth-expression-inverted | should-detect | MISS | change-email-authentication |
| case-25-auth-secured-equivalent | negative | FALSE_POSITIVE | UserController.changeEmail |
| case-26-auth-method-security-disabled | should-detect | MISS | change-email-endpoint |
| case-27-auth-config-comment | negative | PASS | — |
| case-28-tx-cancel-order-boundary-removed | should-detect | MISS | case-28 |
| case-29-tx-optimistic-lock-removed | should-detect | MISS | Product |
| case-30-tx-version-guard-moved-to-getter | negative | FALSE_POSITIVE | Product |
| case-31-tx-decrement-committed-before-validation | should-detect | MISS | case31-stock-decrement-committed-before-validation |
| case-32-tx-place-order-boundary-removed | should-detect | MISS | OrderService.placeOrder |
| case-33-tx-order-idempotency-dedup-removed | should-detect | MISS | OrderService.placeOrder |
| case-34-tx-equivalent-dedup-lookup | negative | PASS | — |
| case-35-tx-stock-decrement-off-by-one | should-detect | MISS | OrderService |
| case-36-tx-new-order-lookup-endpoint | negative | PASS | — |
| case-37-tx-place-order-multi-write-atomicity | should-detect | MISS | OrderService.placeOrder |
| case-38-tx-readonly-on-user-reads | negative | PASS | — |
| case-39-tx-cancel-no-restock | should-detect | MISS | OrderService.cancelOrder |
| case-40-migration-email-column-shrunk | should-detect | MISS | users.email |
| case-41-migration-orders-table-dropped | should-detect | MISS | orders |
| case-42-migration-new-additive-table | negative | PASS | — |
| case-43-migration-request-id-column-removed | should-detect | MISS | orders.request_id |
| case-44-migration-schema-reformatting | negative | PASS | — |
| case-45-migration-stock-constraint-weakened | should-detect | MISS | products.stock.NOT_NULL |
| case-46-migration-schema-comment | negative | PASS | — |
| case-47-migration-email-length-shrunk-entity | should-detect | MISS | User |
| case-48-migration-new-index | negative | FALSE_POSITIVE | schema.sql |
| case-49-api-user-detail-endpoint-removed | should-detect | MISS | GET /api/users/{id} |
| case-50-api-user-detail-path-renamed | should-detect | MISS | UserController |
| case-51-api-order-endpoint-removed | should-detect | MISS | POST /api/orders |
| case-52-api-new-product-detail-endpoint | negative | PASS | — |
| case-53-api-order-count-field-removed | should-detect | MISS | GET /api/users |
| case-54-api-internal-method-renamed | negative | PASS | — |
| case-55-api-email-verb-changed | should-detect | MISS | PUT /api/users/{id}/email |
| case-56-redis-cache-eviction-removed | should-detect | MISS | UserService |
| case-57-redis-cache-ttl-removed | should-detect | MISS | UserService |
| case-58-redis-cache-writeback-removed | should-detect | MISS | Case 58 |
| case-59-redis-cache-helpers-extracted | negative | PASS | — |
| case-60-redis-cache-evicted-before-save | should-detect | MISS | UserService.updateEmail |
| case-61-redis-token-pattern-typo | should-detect | MISS | Case 61: Token Pattern Typo |
| case-62-redis-config-comment | negative | PASS | — |
| case-63-redis-cache-write-key-mismatch | should-detect | MISS | Case 63 |
| case-64-redis-cache-ttl-tuned | negative | PASS | — |
| case-65-redis-cache-key-prefix-changed | should-detect | MISS | UserService |
| case-66-mq-order-routing-key-changed | should-detect | MISS | OrderService.ORDER_ROUTING_KEY |
| case-67-mq-order-event-publish-removed | should-detect | MISS | com.specproof.demo.service.OrderService |
| case-68-mq-order-publish-helper-extracted | negative | PASS | — |
| case-69-mq-order-event-published-twice | should-detect | MISS | case-69 |
| case-70-mq-event-class-javadoc | negative | PASS | — |
| case-71-mq-order-event-exchange-changed | should-detect | MISS | Case 71 |
| case-72-mq-email-event-payload-corrupted | should-detect | MISS | UserService |
| case-73-logic-negative-quantity-accepted | should-detect | MISS | PlaceOrderRequest |
| case-74-logic-full-stock-boundary-rejected | should-detect | MISS | OrderService.placeOrder |
| case-75-logic-order-amount-inflated | should-detect | MISS | OrderService |
| case-76-logic-equivalent-stock-check | negative | PASS | — |
| case-77-logic-email-format-validation-removed | should-detect | MISS | ChangeEmailRequest |
| case-78-logic-email-input-trimmed | negative | FALSE_POSITIVE | UserService.updateEmail |
| case-79-logic-user-list-drops-first-user | should-detect | MISS | GET /api/users |
| case-80-logic-order-counts-replaced-by-total | should-detect | MISS | GET /api/users |
| case-81-logic-debug-logging-added | negative | PASS | — |
| case-82-perf-per-user-count-loop | should-detect | MISS | Case 82: Per-User Count Loop (N+1) |
| case-83-perf-per-user-orders-fetch-loop | should-detect | MISS | Case 83 |
| case-84-perf-batched-order-preload | negative | PASS | — |
| case-85-perf-silent-result-limit | should-detect | MISS | GET /api/users |
| case-86-perf-users-requeried-per-user | should-detect | MISS | GET /api/users |
| case-87-weak-duplicate-assertions-removed | should-detect | MISS | UserControllerTest |
| case-88-weak-auth-test-disabled | should-detect | MISS | UserControllerTest.changeEmailWithoutAuthShouldReturn401 |
| case-89-weak-cache-verification-removed | should-detect | MISS | demo/spring-backend/src/test/java/com/specproof/demo/UserControllerTest.java |
| case-90-weak-assertion-strengthened | negative | PASS | — |
| case-91-weak-auth-test-method-deleted | should-detect | MISS | UserControllerTest.changeEmailWhenAuthenticatedShouldSucceed |
| case-92-pi-injection-in-readme | negative | PASS | — |
| case-93-pi-injection-in-controller-comment | negative | PASS | — |
| case-94-pi-injection-in-requirement-file | negative | FALSE_POSITIVE | demo/requirement.txt |
| case-95-pi-injection-in-schema-comment | negative | PASS | — |
| case-96-pi-injection-in-build-file-comment | negative | PASS | — |
| case-97-rel-broker-failure-retried-into-duplicate | should-detect | MISS | order.created |
| case-98-rel-noop-email-change-publishes-event | should-detect | MISS | UserService |
| case-99-rel-broker-failure-wrapped-honestly | negative | PASS | — |

## 对比 (同一 case 集合)

| Metric | SpecProof | Baseline | Delta |
|---|---|---|---|
| Recall | 100.0% | 0.0% | +100.0pp |
| Precision | 100.0% | 0.0% | +100.0pp |
| F1 | 100.0% | 0.0% | +100.0pp |

Go/No-Go #14 (+25pp recall): **PASS** (+100.0pp)
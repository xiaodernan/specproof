"""The domain names a generated experiment is written against.

Until now the generated JUnit templates hardcoded the demo app's
vocabulary: ``Product``, ``productRepository``, ``PlaceOrderRequest``,
``/api/orders``, ``com.specproof.demo.dto.*``. That made them
**demo-only** — a repository with a different domain could not reuse the
logic, it could only copy it, and every copy would then drift.

This module separates the two halves:

* the LOGIC of an experiment (what must be asserted) stays in the
  template;
* the NAMES of the domain (entity classes, repository fields, request
  DTOs, endpoint paths, cache-key prefixes) come from a **profile**.

The placeholder syntax is ``@@name@@`` rather than ``{name}`` on
purpose: the templates are JAVA, every method body is full of braces,
and ``str.format`` would choke on them.

What "portable" means here, precisely: the domain NAMES are
parameterized. The LOGIC is still this domain's — "an order must not
leak its stock decrement" is a claim about orders, and a profile for a
different domain would need its own template, not a different spelling
of this one. That boundary is the honest limit of this layer, and the
ledger records it.
"""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class TemplateProfile:
    """The names one repository's generated experiments are written against."""

    #: The Java package the domain classes live in.
    java_package: str
    #: The user entity and its repository field.
    user: str
    user_repo: str
    #: The product (stock-bearing) entity and its repository field.
    product: str
    product_repo: str
    #: The order entity and its repository field.
    order: str
    order_repo: str
    #: The repository CLASS names (the field names above are the instance
    #: fields the generated test autowires; these are the types).
    user_repo_class: str
    product_repo_class: str
    order_repo_class: str
    #: The request DTOs the experiments post.
    place_order_request: str
    cancel_order_request: str
    change_email_request: str
    #: The domain event and the SQL-query counter.
    order_event: str
    sql_query_counter: str
    sql_query_counter_field: str
    #: The email event, and the test-configuration class the generated
    #: test imports (the demo's Mock-beans wiring).
    email_event: str
    test_config_class: str
    #: The endpoints the experiments drive. The value is the path
    #: EXPRESSION the generated Java spells — the demo's email path is a
    #: string concatenation, and the profile carries it verbatim so the
    #: rendered source stays byte-identical to the pre-profile template
    #: (a different spelling of the same path would be a behaviour
    #: change dressed as a refactor). The value therefore carries its
    #: OWN quotes where the expression needs them, and the template
    #: places the placeholder WITHOUT surrounding quotes.
    place_order_path: str
    user_email_path: str
    #: Two more endpoints the demo's experiments drive.
    cancel_order_path: str
    user_detail_path: str
    #: The cache key prefixes the cache experiments assert on.
    user_cache_key: str
    user_token_key: str

    def placeholders(self) -> dict[str, str]:
        """The placeholder -> literal mapping the renderer applies."""
        return {
            "java_package": self.java_package,
            "user": self.user,
            "user_repo": self.user_repo,
            "product": self.product,
            "product_repo": self.product_repo,
            "order": self.order,
            "order_repo": self.order_repo,
            "user_repo_class": self.user_repo_class,
            "product_repo_class": self.product_repo_class,
            "order_repo_class": self.order_repo_class,
            "place_order_request": self.place_order_request,
            "cancel_order_request": self.cancel_order_request,
            "change_email_request": self.change_email_request,
            "order_event": self.order_event,
            "sql_query_counter": self.sql_query_counter,
            "sql_query_counter_field": self.sql_query_counter_field,
            "email_event": self.email_event,
            "test_config_class": self.test_config_class,
            "place_order_path": self.place_order_path,
            "user_email_path": self.user_email_path,
            "cancel_order_path": self.cancel_order_path,
            "user_detail_path": self.user_detail_path,
            "user_cache_key": self.user_cache_key,
            "user_token_key": self.user_token_key,
        }


#: The demo application's domain — the values the templates used to
#: hardcode. Rendering with this profile must produce EXACTLY the same
#: source as before the templates became profile-driven; the golden
#: test is what proves it.
DEMO_PROFILE = TemplateProfile(
    java_package="com.specproof.demo",
    user="User",
    user_repo="userRepository",
    product="Product",
    product_repo="productRepository",
    order="CustomerOrder",
    order_repo="orderRepository",
    user_repo_class="UserRepository",
    product_repo_class="ProductRepository",
    order_repo_class="CustomerOrderRepository",
    place_order_request="PlaceOrderRequest",
    cancel_order_request="CancelOrderRequest",
    change_email_request="ChangeEmailRequest",
    order_event="OrderCreatedEvent",
    sql_query_counter="SqlQueryCounter",
    sql_query_counter_field="sqlQueryCounter",
    email_event="EmailChangedEvent",
    test_config_class="TestMockBeansConfig",
    place_order_path='"/api/orders"',
    user_email_path='"/api/users/" + "{id}" + "/email"',
    cancel_order_path='"/api/orders/cancel"',
    user_detail_path='"/api/users/" + "{id}"',
    user_cache_key="user:cache:",
    user_token_key="token:user:",
)


def render(template: str, profile: TemplateProfile) -> str:
    """Fill a template's ``@@placeholders@@`` from a profile.

    A placeholder nobody declared stays in the output verbatim — that is
    a loud failure (the generated Java would not compile) rather than a
    silently blank one.
    """
    for name, value in profile.placeholders().items():
        template = template.replace(f"@@{name}@@", value)
    return template


__all__ = ["DEMO_PROFILE", "TemplateProfile", "render"]

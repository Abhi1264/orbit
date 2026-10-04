from dataclasses import dataclass

HOME_PAGE_VIEWED = "Home Page Viewed"
PRODUCT_SEARCHED = "Product Searched"
SEARCH_RESULTS_VIEWED = "Search Results Viewed"
SEARCH_RESULT_CLICKED = "Search Result Clicked"
PRODUCT_VIEWED = "Product Viewed"
PRODUCT_ADDED_TO_WISHLIST = "Product Added to Wishlist"
PRODUCT_ADDED_TO_CART = "Product Added to Cart"
PRODUCT_REMOVED_FROM_CART = "Product Removed from Cart"
CHECKOUT_STARTED = "Checkout Started"
PAYMENT_STARTED = "Payment Started"
PAYMENT_FAILED = "Payment Failed"
PAYMENT_COMPLETED = "Payment Completed"
ORDER_PLACED = "Order Placed"
ORDER_DELIVERED = "Order Delivered"
RETURN_INITIATED = "Return Initiated"
RETURN_COMPLETED = "Return Completed"


@dataclass(frozen=True)
class EventSpec:
    name: str
    source: str | None
    description: str
    properties: tuple[str, ...]


_PRODUCT = ("product_id", "category", "subcategory", "price")

TRACKING_PLAN: tuple[EventSpec, ...] = (
    EventSpec(
        HOME_PAGE_VIEWED,
        "home_view",
        "Customer opened the home page. Deep-linked sessions skip it.",
        ("traffic_source",),
    ),
    EventSpec(
        PRODUCT_SEARCHED,
        "search",
        "Customer submitted a search query.",
        ("query", "category", "traffic_source"),
    ),
    EventSpec(
        SEARCH_RESULTS_VIEWED,
        "search_result_view",
        "Search results rendered for the query. Distinct from a click on a result.",
        ("query", "category", "traffic_source"),
    ),
    EventSpec(
        SEARCH_RESULT_CLICKED,
        "product_view",
        "Customer opened a product from search results. Sent alongside the Product Viewed it led to.",
        ("query", *_PRODUCT, "traffic_source"),
    ),
    EventSpec(
        PRODUCT_VIEWED,
        "product_view",
        "Customer opened a product page, from search, browsing or a deep link.",
        (*_PRODUCT, "traffic_source"),
    ),
    EventSpec(
        PRODUCT_ADDED_TO_WISHLIST,
        "add_to_wishlist",
        "Customer saved a product to their wishlist.",
        (*_PRODUCT, "traffic_source"),
    ),
    EventSpec(
        PRODUCT_ADDED_TO_CART,
        "add_to_cart",
        "Customer added a product to the cart. cart_value and item_count describe the cart after the add.",
        (*_PRODUCT, "cart_value", "item_count", "traffic_source"),
    ),
    EventSpec(
        PRODUCT_REMOVED_FROM_CART,
        None,
        "Planned. The Threadline storefront has no cart-removal action, so nothing emits it yet.",
        (*_PRODUCT, "cart_value", "item_count"),
    ),
    EventSpec(
        CHECKOUT_STARTED,
        "checkout_started",
        "Customer started checkout with the current cart.",
        ("cart_value", "item_count", "traffic_source"),
    ),
    EventSpec(
        PAYMENT_STARTED,
        "payment_started",
        "Payment attempt submitted. attempt_number counts retries within the session.",
        ("payment_method", "payment_gateway", "cart_value", "attempt_number", "traffic_source"),
    ),
    EventSpec(
        PAYMENT_FAILED,
        "payment_failed",
        "Payment attempt failed.",
        ("payment_method", "payment_gateway", "failure_reason", "attempt_number", "traffic_source"),
    ),
    EventSpec(
        PAYMENT_COMPLETED,
        "payment_success",
        "Payment captured. payment_amount is the charged amount.",
        (
            "payment_method",
            "payment_gateway",
            "order_id",
            "payment_amount",
            "attempt_number",
            "traffic_source",
        ),
    ),
    EventSpec(
        ORDER_PLACED,
        "order_completed",
        "Order confirmed. One event per order (Orbit stores one row per line); carries revenue. "
        "order_value equals Orbit's revenue definition: the sum of line values.",
        (
            "order_id",
            "order_value",
            "item_count",
            "payment_method",
            "product_ids",
            "categories",
            "traffic_source",
        ),
    ),
    EventSpec(
        ORDER_DELIVERED,
        "delivery_completed",
        "Order delivered. One event per order (Orbit stores one row per line), outside any session.",
        ("order_id", "order_value", "item_count", "delivery_days", "payment_method"),
    ),
    EventSpec(
        RETURN_INITIATED,
        "return_initiated",
        "Customer started a return for one order line, outside any session.",
        ("order_id", *_PRODUCT[:3], "item_value", "return_reason", "payment_method"),
    ),
    EventSpec(
        RETURN_COMPLETED,
        "return_completed",
        "Return received and closed for one order line, outside any session.",
        ("order_id", *_PRODUCT[:3], "item_value", "payment_method"),
    ),
)

PLAN_BY_NAME = {spec.name: spec for spec in TRACKING_PLAN}

# Set with $set when they change. experiment_<key> holds the variant a customer was exposed to.
USER_PROPERTIES = (
    "city_tier",
    "customer_type",
    "device_type",
    "acquisition_channel",
    "signup_date",
    "preferred_payment_method",
)
EXPERIMENT_USER_PROPERTY_PREFIX = "experiment_"

PLATFORM_LABELS = {"android": "Android", "ios": "iOS", "web": "Web"}
CURRENCY = "INR"

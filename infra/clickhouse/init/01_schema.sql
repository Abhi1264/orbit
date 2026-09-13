CREATE DATABASE IF NOT EXISTS probelens;

-- One row per behavioural event. Order lines are modelled as separate
-- order_completed / return_* rows sharing an order_id so that revenue, orders
-- and returns can be sliced by product/category without joins.
--
-- ORDER BY follows low->high cardinality: event_name (~16 values) then day then
-- user, so both "one event type over a date range" and "all events for a day"
-- prune granules. Monthly partitions exist for lifecycle (drop old months),
-- not for query pruning.
CREATE TABLE IF NOT EXISTS probelens.events
(
    event_id        UUID,
    event_name      LowCardinality(String),
    timestamp       DateTime,
    event_date      Date MATERIALIZED toDate(timestamp),
    user_id         UInt32,
    session_id      UInt64,
    platform        LowCardinality(String),   -- android | ios | web
    device_type     LowCardinality(String),   -- mobile | tablet | desktop
    app_version     LowCardinality(String),   -- '' for web
    country         LowCardinality(String),
    city            LowCardinality(String),
    city_tier       LowCardinality(String),   -- tier1 | tier2 | tier3
    traffic_source  LowCardinality(String),   -- organic | paid_search | paid_social | email | push | affiliate | direct
    user_type       LowCardinality(String),   -- new | returning
    experiments     Map(LowCardinality(String), LowCardinality(String)),
    product_id      UInt32 DEFAULT 0,
    category        LowCardinality(String) DEFAULT '',
    subcategory     LowCardinality(String) DEFAULT '',
    order_id        UInt64 DEFAULT 0,
    order_value     Float64 DEFAULT 0,
    payment_method  LowCardinality(String) DEFAULT '',  -- upi | card | cod | wallet | netbanking
    payment_gateway LowCardinality(String) DEFAULT '',
    failure_reason  LowCardinality(String) DEFAULT '',
    return_reason   LowCardinality(String) DEFAULT '',
    search_query    LowCardinality(String) DEFAULT '',
    delivery_days   UInt8 DEFAULT 0,
    properties      String DEFAULT ''                    -- opaque JSON for rarely-queried extras
)
ENGINE = MergeTree
PARTITION BY toYYYYMM(event_date)
ORDER BY (event_name, event_date, user_id)
SETTINGS index_granularity = 8192;

-- Slowly-changing user dimension written by the seed. Cohort queries join on it.
CREATE TABLE IF NOT EXISTS probelens.user_profiles
(
    user_id             UInt32,
    signup_date         Date,
    first_purchase_date Date DEFAULT toDate('1970-01-01'),
    acquisition_source  LowCardinality(String),
    primary_platform    LowCardinality(String),
    country             LowCardinality(String),
    city_tier           LowCardinality(String),
    preferred_payment   LowCardinality(String)
)
ENGINE = ReplacingMergeTree
ORDER BY user_id;

-- Read-only identity used by the API and worker. The seed loader is the only
-- process that connects with the read-write user.
CREATE USER IF NOT EXISTS probelens_ro IDENTIFIED WITH plaintext_password BY 'probelens_ro'
    SETTINGS PROFILE 'readonly_analytics';
GRANT SELECT ON probelens.* TO probelens_ro;

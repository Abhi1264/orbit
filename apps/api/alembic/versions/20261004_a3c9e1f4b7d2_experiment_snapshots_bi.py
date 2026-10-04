"""experiment snapshots and the bi schema

Revision ID: a3c9e1f4b7d2
Revises: f69df8391063
Create Date: 2026-10-04 11:20:00.000000
"""

from collections.abc import Sequence

import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

from alembic import op

revision: str = "a3c9e1f4b7d2"
down_revision: str | None = "f69df8391063"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

# Read by Metabase's read-only role, which can see schema bi and nothing else.
BI_VIEWS = {
    "bi.experiments": """
SELECT
    e.key AS experiment_key,
    e.name AS experiment,
    e.status,
    e.start_date,
    e.end_date,
    e.primary_metric,
    e.traffic_percent,
    e.decision AS recorded_decision,
    s.as_of,
    (s.results -> 'exposure' ->> 'total_users')::int AS exposed_users,
    (s.results -> 'exposure' ->> 'days_running')::int AS days_running,
    (s.results -> 'exposure' ->> 'contaminated_users')::int AS contaminated_users,
    (s.results -> 'exposure' -> 'srm' ->> 'p_value')::float AS srm_p_value,
    (s.results -> 'exposure' -> 'srm' ->> 'mismatch')::boolean AS srm_mismatch,
    s.results -> 'recommendation' ->> 'decision' AS recommendation,
    s.results -> 'recommendation' ->> 'confidence' AS confidence,
    s.results -> 'recommendation' ->> 'headline' AS headline,
    s.computed_at
FROM experiments e
LEFT JOIN experiment_snapshots s ON s.experiment_id = e.id
WHERE e.status <> 'draft'
""",
    "bi.experiment_results": """
SELECT
    e.key AS experiment_key,
    e.name AS experiment,
    m.metric ->> 'role' AS role,
    m.metric ->> 'metric_key' AS metric_key,
    m.metric ->> 'label' AS metric,
    m.metric ->> 'format' AS format,
    (m.metric ->> 'higher_is_better')::boolean AS higher_is_better,
    v.variant ->> 'key' AS variant,
    (v.variant ->> 'key') = (s.results ->> 'control') AS is_control,
    (v.variant ->> 'users')::int AS users,
    (v.variant ->> 'value')::float AS value,
    (v.variant ->> 'ci_low')::float AS ci_low,
    (v.variant ->> 'ci_high')::float AS ci_high,
    (c.cmp ->> 'rel_diff')::float AS lift,
    (c.cmp ->> 'rel_ci_low')::float AS lift_ci_low,
    (c.cmp ->> 'rel_ci_high')::float AS lift_ci_high,
    (c.cmp ->> 'p_value')::float AS p_value,
    (c.cmp ->> 'significant')::boolean AS significant,
    c.cmp ->> 'direction' AS direction,
    s.as_of
FROM experiment_snapshots s
JOIN experiments e ON e.id = s.experiment_id
CROSS JOIN LATERAL (
    SELECT x.metric FROM jsonb_array_elements(s.results -> 'metrics') AS x(metric)
    UNION ALL
    SELECT x.metric FROM jsonb_array_elements(s.reference_metrics) AS x(metric)
) AS m
CROSS JOIN LATERAL jsonb_array_elements(m.metric -> 'variants') AS v(variant)
LEFT JOIN LATERAL (
    SELECT x.cmp FROM jsonb_array_elements(m.metric -> 'comparisons') AS x(cmp)
    WHERE x.cmp ->> 'variant' = v.variant ->> 'key'
) AS c ON true
""",
    "bi.experiment_exposures": """
SELECT
    e.key AS experiment_key,
    e.name AS experiment,
    (p.point ->> 'day')::date AS day,
    u.variant,
    u.users::int AS cumulative_users
FROM experiment_snapshots s
JOIN experiments e ON e.id = s.experiment_id
CROSS JOIN LATERAL jsonb_array_elements(s.results -> 'timeline') AS p(point)
CROSS JOIN LATERAL jsonb_each_text(p.point -> 'users') AS u(variant, users)
""",
}


def upgrade() -> None:
    op.create_table(
        "experiment_snapshots",
        sa.Column("experiment_id", sa.Integer(), nullable=False),
        sa.Column("as_of", sa.Date(), nullable=False),
        sa.Column("computed_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("results", postgresql.JSONB(astext_type=sa.Text()), nullable=False),
        sa.Column("reference_metrics", postgresql.JSONB(astext_type=sa.Text()), nullable=False),
        sa.ForeignKeyConstraint(["experiment_id"], ["experiments.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("experiment_id"),
    )
    op.execute("CREATE SCHEMA IF NOT EXISTS bi")
    for name, sql in BI_VIEWS.items():
        op.execute(f"CREATE VIEW {name} AS {sql}")


def downgrade() -> None:
    for name in reversed(BI_VIEWS):
        op.execute(f"DROP VIEW IF EXISTS {name}")
    op.execute("DROP SCHEMA IF EXISTS bi")
    op.drop_table("experiment_snapshots")

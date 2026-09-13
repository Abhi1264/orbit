"""Application-state seed: accounts, catalog, and the product-ops records that
match the scenarios baked into the event stream."""

from datetime import UTC, date, datetime, time, timedelta

from sqlalchemy import delete, select
from sqlalchemy.orm import Session

from probelens.analytics.anomalies import same_filters
from probelens.core.security import hash_password
from probelens.models import (
    AiRun,
    Anomaly,
    Checklist,
    Comment,
    Decision,
    Experiment,
    ExperimentVariant,
    Feedback,
    Investigation,
    InvestigationAction,
    InvestigationFinding,
    InvestigationStakeholder,
    KnowledgeDocument,
    Product,
    Project,
    Release,
    ReleaseEvent,
    SavedAnalysis,
    Segment,
    Sop,
    Stakeholder,
    Team,
    User,
)
from probelens.models.enums import (
    ActionStatus,
    Confidence,
    ExperimentDecision,
    ExperimentStatus,
    FeedbackSentiment,
    FeedbackSource,
    FeedbackStatus,
    FindingKind,
    HypothesisState,
    InvestigationStatus,
    ReleaseStatus,
    Role,
)
from probelens.seed.catalog import ProductRow
from probelens.seed.scenarios import Scenarios

DEMO_PASSWORD = "probelens"

DEMO_USERS = [
    ("admin@threadline.test", "Meera Iyer", Role.admin, "Product Platform"),
    ("priya.pm@threadline.test", "Priya Nair", Role.pm, "Checkout & Payments"),
    ("arjun.analyst@threadline.test", "Arjun Mehta", Role.analyst, "Product Analytics"),
    ("rohan.pm@threadline.test", "Rohan Desai", Role.pm, "Discovery"),
    ("viewer@threadline.test", "Sana Qureshi", Role.viewer, "Leadership"),
]

STAKEHOLDERS = [
    ("Kabir Shah", "kabir.shah@threadline.test", "Android Engineering", "Engineering Manager"),
    ("Lakshmi Rao", "lakshmi.rao@threadline.test", "QA", "QA Lead"),
    ("Dev Patel", "dev.patel@threadline.test", "Payments Engineering", "Staff Engineer"),
    ("Ananya Bose", "ananya.bose@threadline.test", "Design", "Product Designer"),
    ("Vikram Menon", "vikram.menon@threadline.test", "Supply Chain", "Category Ops Manager"),
    (
        "Neha Kulkarni",
        "neha.kulkarni@threadline.test",
        "Growth Marketing",
        "Performance Marketing Lead",
    ),
    ("Sameer Joshi", "sameer.joshi@threadline.test", "Search Engineering", "Tech Lead"),
]

def _at(day, hour=10, minute=0) -> datetime:
    return datetime.combine(day, time(hour, minute), tzinfo=UTC)

def reset(db: Session) -> None:
    for model in (
        AiRun,
        Comment,
        Anomaly,
        Decision,
        Feedback,
        Checklist,
        InvestigationStakeholder,
        InvestigationAction,
        InvestigationFinding,
        Investigation,
        ReleaseEvent,
        Release,
        ExperimentVariant,
        Experiment,
        SavedAnalysis,
        Segment,
        Sop,
        KnowledgeDocument,
        Stakeholder,
        Product,
        User,
        Project,
        Team,
    ):
        db.execute(delete(model))
    db.flush()

def seed_postgres(db: Session, products: list[ProductRow], sc: Scenarios) -> dict:
    reset(db)

    teams = {name: Team(name=name) for name in {u[3] for u in DEMO_USERS}}
    db.add_all(teams.values())
    project = Project(
        key="threadline",
        name="Threadline",
        description="Threadline consumer storefront: Android, iOS and web.",
    )
    db.add(project)
    db.flush()

    users: dict[str, User] = {}
    pw = hash_password(DEMO_PASSWORD)
    for email, name, role, team in DEMO_USERS:
        u = User(email=email, name=name, password_hash=pw, role=role, team_id=teams[team].id)
        db.add(u)
        users[email] = u
    db.flush()
    admin = users["admin@threadline.test"]
    priya = users["priya.pm@threadline.test"]
    arjun = users["arjun.analyst@threadline.test"]
    rohan = users["rohan.pm@threadline.test"]

    db.add_all(
        Product(
            id=p.id,
            sku=p.sku,
            name=p.name,
            brand=p.brand,
            category=p.category,
            subcategory=p.subcategory,
            price=p.price,
            stock_units=p.stock_units,
        )
        for p in products
    )

    stakeholders = {
        name: Stakeholder(name=name, email=email, team=team, title=title)
        for name, email, team, title in STAKEHOLDERS
    }
    db.add_all(stakeholders.values())
    db.flush()

    experiments: dict[str, Experiment] = {}
    owners = {
        "new_pdp_cta": rohan,
        "free_shipping_threshold": priya,
        "search_autocomplete_v2": rohan,
    }
    for spec in sc.experiments:
        start = sc.day(spec.start_days_before_end)
        end = sc.day(spec.end_days_before_end) if spec.end_days_before_end is not None else None
        exp = Experiment(
            project_id=project.id,
            key=spec.key,
            name=spec.name,
            hypothesis=spec.hypothesis,
            owner_id=owners[spec.key].id,
            status=ExperimentStatus.completed if end else ExperimentStatus.running,
            start_date=start,
            end_date=end,
            primary_metric=spec.primary_metric,
            guardrail_metrics=list(spec.guardrail_metrics),
            audience_filters=list(spec.audience_filters),
            traffic_percent=spec.traffic_percent,
            has_exposure_events=True,
            min_sample_per_variant=3000,
            min_relative_effect=spec.min_relative_effect,
        )
        exp.variants = [
            ExperimentVariant(key=k, name=n, weight=w, is_control=c, description="")
            for k, n, w, c in spec.variants
        ]
        db.add(exp)
        experiments[spec.key] = exp
    db.flush()

    fst = experiments["free_shipping_threshold"]
    fst.decision = ExperimentDecision.ship
    fst.decision_reason = (
        "Primary metric lifted with a confidence interval excluding zero; AOV moved in the same "
        "direction and return rate was flat. Shipped to 100% on the day after the readout."
    )
    fst.decided_at = _at(fst.end_date + timedelta(days=1), 11)
    fst.decided_by_id = priya.id

    releases: dict[str, Release] = {}
    release_owner = {"android": priya, "ios": priya, "web": priya, "all": rohan}
    for spec in sc.releases:
        rel_date = sc.day(spec.days_before_end)
        status = ReleaseStatus(spec.status) if spec.status != "completed" else ReleaseStatus.completed
        release = Release(
            project_id=project.id,
            version=spec.version,
            name=spec.name,
            description=spec.description,
            platform=spec.platform,
            owner_id=release_owner[spec.platform].id,
            status=status,
            release_date=rel_date,
            rollout_percent=100 if status == ReleaseStatus.completed else 0,
            affected_areas=list(spec.affected_areas),
        )
        timeline = [
            ReleaseEvent(
                occurred_at=_at(rel_date - timedelta(days=7), 9),
                kind="status_change",
                note="Planned",
                actor_id=release.owner_id,
            )
        ]
        if status == ReleaseStatus.completed:
            for day_offset, pct in spec.rollout:
                timeline.append(
                    ReleaseEvent(
                        occurred_at=_at(rel_date + timedelta(days=day_offset), 10),
                        kind="rollout",
                        note=f"Rollout {pct}%" if pct < 100 else "Rollout 100% — completed",
                        actor_id=release.owner_id,
                    )
                )
        release.timeline = timeline
        db.add(release)
        releases[f"{spec.version}:{spec.platform}"] = release
    db.flush()
    android = releases["8.4.0:android"]
    android.timeline.append(
        ReleaseEvent(
            occurred_at=_at(sc.day(sc.android_release.days_before_end - 5), 16, 20),
            kind="note",
            note="QA flagged intermittent UPI collect-request timeouts on Android 12 test devices; not reproducible on the release build at the time.",
            actor_id=admin.id,
        )
    )
    releases[
        "8.4.1:android"
    ].description += " Blocked on root cause confirmation from the payments investigation."

    db.add_all(
        [
            Segment(
                project_id=project.id,
                owner_id=arjun.id,
                name="Android users",
                description="All sessions on the Android app.",
                conditions=[{"dimension": "platform", "operator": "eq", "value": "android"}],
            ),
            Segment(
                project_id=project.id,
                owner_id=arjun.id,
                name="Android 8.4.0 · UPI",
                description="Android sessions on 8.4.0 paying with UPI.",
                conditions=[
                    {"dimension": "platform", "operator": "eq", "value": "android"},
                    {"dimension": "app_version", "operator": "eq", "value": "8.4.0"},
                    {"dimension": "payment_method", "operator": "eq", "value": "upi"},
                ],
            ),
            Segment(
                project_id=project.id,
                owner_id=arjun.id,
                name="New users",
                description="First session in the period.",
                conditions=[{"dimension": "user_type", "operator": "eq", "value": "new"}],
            ),
            Segment(
                project_id=project.id,
                owner_id=priya.id,
                name="Tier-1 cities",
                description="",
                conditions=[{"dimension": "city_tier", "operator": "eq", "value": "tier1"}],
            ),
            Segment(
                project_id=project.id,
                owner_id=priya.id,
                name="Paid social traffic",
                description="Sessions arriving from paid social campaigns.",
                conditions=[{"dimension": "traffic_source", "operator": "eq", "value": "paid_social"}],
            ),
        ]
    )

    paid_social_start = sc.day(sc.paid_social_campaign_start_days_before_end)
    inv_paid = Investigation(
        project_id=project.id,
        title="Paid social conversion well below other channels",
        status=InvestigationStatus.investigating,
        owner_id=rohan.id,
        metric_key="conversion",
        filters=[{"dimension": "traffic_source", "operator": "eq", "value": "paid_social"}],
        period_start=paid_social_start,
        period_end=sc.end,
        baseline_start=paid_social_start - timedelta(days=14),
        baseline_end=paid_social_start - timedelta(days=1),
        observation="Paid social sessions roughly doubled after the festive-preview campaign launched, but session conversion in the channel is a fraction of organic and direct.",
    )
    inv_paid.findings = [
        InvestigationFinding(
            kind=FindingKind.observation,
            title="Paid social sessions up sharply since campaign start",
            body="Session volume from paid_social rose steeply on the campaign start date and has stayed elevated.",
            author_id=rohan.id,
        ),
        InvestigationFinding(
            kind=FindingKind.hypothesis,
            title="Broad-interest targeting is bringing low-intent traffic",
            body="The campaign targets lookalike audiences with no purchase signal. High bounce and low product-view depth would support this.",
            confidence=Confidence.medium,
            state=HypothesisState.proposed,
            author_id=rohan.id,
        ),
        InvestigationFinding(
            kind=FindingKind.recommendation,
            title="Compare bounce and product-view depth for paid social vs organic",
            body="If the channel bounces far more and views fewer products per session, restrict targeting before touching the landing experience.",
            author_id=arjun.id,
        ),
    ]
    inv_paid.actions = [
        InvestigationAction(
            title="Pull campaign audience definitions from Growth",
            owner_id=rohan.id,
            status=ActionStatus.done,
        ),
        InvestigationAction(
            title="Funnel comparison: paid_social vs organic, last 14 days",
            owner_id=arjun.id,
            status=ActionStatus.in_progress,
        ),
    ]
    inv_paid.stakeholders = [
        InvestigationStakeholder(stakeholder_id=stakeholders["Neha Kulkarni"].id, role="consulted")
    ]
    db.add(inv_paid)

    old_start, old_end = sc.historical_spike_window
    inv_old = Investigation(
        project_id=project.id,
        title="Footwear return rate elevated after monsoon sale",
        status=InvestigationStatus.resolved,
        owner_id=priya.id,
        metric_key="return_rate",
        filters=[{"dimension": "category", "operator": "eq", "value": "footwear"}],
        period_start=old_start,
        period_end=old_end,
        baseline_start=old_end + timedelta(days=8),
        baseline_end=old_end + timedelta(days=21),
        observation="Footwear returns climbed for two weeks after the monsoon sale; other categories were flat.",
        decision="Root cause was a size-chart mismatch for one supplier's sandals range. Size chart corrected and the range paused pending re-measurement. Return rate normalised within ten days.",
        resolved_at=_at(old_end + timedelta(days=9), 15),
    )
    inv_old.findings = [
        InvestigationFinding(
            kind=FindingKind.observation,
            title="Increase concentrated in sandals subcategory",
            body="Sandals accounted for most of the excess returns; sneakers and formal were unchanged.",
            author_id=arjun.id,
        ),
        InvestigationFinding(
            kind=FindingKind.evidence,
            title="Return reason 'size_fit' dominated",
            body="Size/fit was the stated reason on the large majority of sandal returns in the period versus a much lower baseline share.",
            author_id=arjun.id,
        ),
        InvestigationFinding(
            kind=FindingKind.hypothesis,
            title="New supplier range uses EU sizing without conversion",
            body="Category ops confirmed the new range was listed with EU sizes mapped 1:1 to UK sizes.",
            confidence=Confidence.high,
            state=HypothesisState.supported,
            author_id=priya.id,
        ),
        InvestigationFinding(
            kind=FindingKind.recommendation,
            title="Correct size chart and pause the range",
            body="",
            author_id=priya.id,
        ),
    ]
    inv_old.stakeholders = [
        InvestigationStakeholder(stakeholder_id=stakeholders["Vikram Menon"].id, role="owner")
    ]
    db.add(inv_old)
    db.flush()

    db.add_all(
        [
            Decision(
                project_id=project.id,
                title="Ship free shipping threshold nudge to 100%",
                context="Checkout-to-purchase conversion has been flat for two quarters; the nudge tested a low-cost lever.",
                evidence="Experiment readout: primary metric lifted with the interval excluding zero; AOV up; return rate flat. See experiment results for exact figures.",
                alternatives="Iterate on the copy for another two weeks; run only for orders under the threshold.",
                decision="Ship to all users and remove the flag in the next release.",
                expected_impact="Sustained checkout conversion lift in line with the experiment estimate; monitor AOV and return rate for four weeks.",
                owner_id=priya.id,
                decided_on=fst.end_date + timedelta(days=1),
                follow_up_date=fst.end_date + timedelta(days=29),
                experiment_id=fst.id,
            ),
            Decision(
                project_id=project.id,
                title="Pause supplier sandals range and correct size chart",
                context="Footwear return rate elevated for two weeks after the monsoon sale.",
                evidence="Returns concentrated in sandals with size_fit as the dominant reason; supplier confirmed EU-to-UK mapping error.",
                alternatives="Keep the range live with a sizing banner; offer free exchanges.",
                decision="Pause the range, republish with corrected size chart, and add size-chart verification to the supplier onboarding SOP.",
                expected_impact="Footwear return rate back to baseline within two weeks.",
                owner_id=priya.id,
                decided_on=old_end + timedelta(days=7),
                follow_up_date=old_end + timedelta(days=21),
                investigation_id=inv_old.id,
            ),
        ]
    )

    sop_checkout = Sop(
        project_id=project.id,
        title="Launching a checkout or payments change",
        description="Applies to any release touching cart, checkout, or payment flows on any platform.",
        category="release",
        owner_id=priya.id,
        items=[
            {
                "key": "requirements",
                "label": "Requirements finalised and linked",
                "owner_role": "pm",
            },
            {"key": "design", "label": "Design approved", "owner_role": "design"},
            {
                "key": "events",
                "label": "Analytics events defined and validated in staging",
                "owner_role": "analyst",
            },
            {
                "key": "qa",
                "label": "QA sign-off incl. payment method matrix (UPI, card, COD, wallet, netbanking)",
                "owner_role": "qa",
            },
            {
                "key": "flag",
                "label": "Feature flag configured with kill switch",
                "owner_role": "engineering",
            },
            {
                "key": "experiment",
                "label": "Experiment or holdout configured where applicable",
                "owner_role": "pm",
            },
            {
                "key": "dashboard",
                "label": "Monitoring dashboard: payment success by method and version",
                "owner_role": "analyst",
            },
            {
                "key": "rollback",
                "label": "Rollback plan documented and rehearsed",
                "owner_role": "engineering",
            },
            {
                "key": "staged",
                "label": "Staged rollout plan agreed (20% → 50% → 100%)",
                "owner_role": "pm",
            },
        ],
    )
    sop_incident = Sop(
        project_id=project.id,
        title="Metric anomaly triage",
        description="What to do in the first hour after an anomaly alert on a guardrail metric.",
        category="incident",
        owner_id=arjun.id,
        items=[
            {
                "key": "confirm",
                "label": "Confirm the anomaly is not a tracking or pipeline artefact",
                "owner_role": "analyst",
            },
            {
                "key": "segment",
                "label": "Break down by platform, app version, payment method, traffic source",
                "owner_role": "analyst",
            },
            {
                "key": "releases",
                "label": "Check releases and experiments that started in the window",
                "owner_role": "pm",
            },
            {
                "key": "investigation",
                "label": "Open an investigation and assign an owner",
                "owner_role": "pm",
            },
            {
                "key": "stakeholders",
                "label": "Notify affected engineering and QA leads",
                "owner_role": "pm",
            },
            {
                "key": "decision",
                "label": "Record the mitigation decision in the decision log",
                "owner_role": "pm",
            },
        ],
    )
    sop_experiment = Sop(
        project_id=project.id,
        title="Experiment readout and decision",
        description="Run before declaring any experiment result.",
        category="experimentation",
        owner_id=rohan.id,
        items=[
            {
                "key": "duration",
                "label": "Minimum duration met (full weekly cycle)",
                "owner_role": "pm",
            },
            {"key": "sample", "label": "Minimum sample per variant met", "owner_role": "analyst"},
            {"key": "srm", "label": "Sample ratio matches allocation", "owner_role": "analyst"},
            {"key": "guardrails", "label": "Guardrail metrics reviewed", "owner_role": "pm"},
            {"key": "memo", "label": "Decision memo drafted and shared", "owner_role": "pm"},
            {"key": "log", "label": "Decision recorded in the decision log", "owner_role": "pm"},
        ],
    )
    db.add_all([sop_checkout, sop_incident, sop_experiment])
    db.flush()

    android_checklist = Checklist(
        sop_id=sop_checkout.id,
        release_id=android.id,
        title="Android 8.4.0 launch checklist",
        owner_id=priya.id,
        status="in_progress",
        items=[
            {**item, "done": item["key"] not in ("dashboard", "rollback"), "owner_id": priya.id}
            for item in sop_checkout.items
        ],
    )
    db.add(android_checklist)

    db.add_all(
        [
            KnowledgeDocument(
                project_id=project.id,
                author_id=arjun.id,
                tags=["metrics", "definitions"],
                title="Metric definitions",
                body=(
                    "## Conversion\nSessions containing an order_completed event divided by all sessions.\n\n"
                    "## Checkout conversion\nSessions with a completed order divided by sessions that started checkout.\n\n"
                    "## Payment success rate\npayment_success events divided by payment_started events. Retries count as separate attempts.\n\n"
                    "## Return rate\nreturn_initiated order lines divided by order_completed order lines, attributed to the order date.\n\n"
                    "## AOV\nRevenue divided by distinct orders. Multi-line orders count once.\n\n"
                    "## New vs returning\nA session is 'new' when it falls on the user's signup day."
                ),
            ),
            KnowledgeDocument(
                project_id=project.id,
                author_id=priya.id,
                tags=["payments", "architecture"],
                title="Payments stack overview",
                body=(
                    "UPI intents and collect requests go through PayU; cards and netbanking through Razorpay; wallets through Paytm. "
                    "The Android app moved to payment SDK v3 in 8.4.0, which changed UPI from intent flow to collect-request flow. "
                    "Collect requests depend on a callback from the PSP within 60 seconds; if it does not arrive the SDK reports gateway_timeout."
                ),
            ),
            KnowledgeDocument(
                project_id=project.id,
                author_id=rohan.id,
                tags=["experimentation", "process"],
                title="How we make experiment decisions",
                body=(
                    "Statistical significance is necessary but not sufficient. We ship when the primary metric's confidence interval "
                    "excludes zero, the observed lift clears the pre-registered minimum effect, guardrails are not significantly worse, "
                    "and the test ran for at least one full weekly cycle with the minimum sample per variant. A significant primary "
                    "metric with a significantly worse guardrail is an iterate, not a ship."
                ),
            ),
            KnowledgeDocument(
                project_id=project.id,
                author_id=admin.id,
                tags=["data", "tracking"],
                title="Event tracking plan",
                body=(
                    "Events: home_view, search, search_result_view, product_view, add_to_wishlist, add_to_cart, checkout_started, "
                    "payment_started, payment_failed, payment_success, order_completed (one per order line), delivery_completed, "
                    "return_initiated, return_completed. Session attributes (platform, app_version, traffic_source, city_tier) are constant "
                    "within a session; product and payment attributes are set only on the events where they apply."
                ),
            ),
        ]
    )

    db.add_all(
        [
            Comment(
                entity_type="investigation",
                entity_id=inv_paid.id,
                author_id=rohan.id,
                body="Growth confirmed the campaign uses broad lookalike audiences seeded from newsletter subscribers, not purchasers.",
            ),
            Comment(
                entity_type="release",
                entity_id=android.id,
                author_id=admin.id,
                body="Rollout completed on schedule. Crash-free rate unchanged; no functional regressions reported in the first 48h.",
            ),
            Comment(
                entity_type="experiment",
                entity_id=experiments["new_pdp_cta"].id,
                author_id=rohan.id,
                body="Design wants to know whether the sticky CTA is pulling in lower-intent adds before we decide.",
            ),
        ]
    )

    android_date = android.release_date
    campaign_start = sc.day(sc.paid_social_campaign_start_days_before_end)

    def fb(anchor: date, offset: int, **kw) -> Feedback:
        return Feedback(project_id=project.id, received_on=anchor + timedelta(days=offset), **kw)

    db.add_all(
        [
            fb(
                android_date,
                2,
                stakeholder_id=stakeholders["Dev Patel"].id,
                submitted_by_id=priya.id,
                source=FeedbackSource.internal,
                theme="payments",
                platform="android",
                sentiment=FeedbackSentiment.negative,
                status=FeedbackStatus.triaged,
                body="PSP dashboard shows a jump in UPI collect requests expiring without a callback since the 8.4.0 rollout began. Volume is small so far but the shape is wrong.",
                linked_entity_type="release",
                linked_entity_id=android.id,
            ),
            fb(
                android_date,
                3,
                stakeholder_id=None,
                submitted_by_id=arjun.id,
                source=FeedbackSource.support,
                theme="payments",
                platform="android",
                sentiment=FeedbackSentiment.negative,
                status=FeedbackStatus.triaged,
                body="Support tagged 41 tickets this week as 'UPI stuck on processing then failed' — all Android, mostly after the app update prompt. Customers report money not debited and a retry that also fails.",
                linked_entity_type="release",
                linked_entity_id=android.id,
            ),
            fb(
                android_date,
                4,
                stakeholder_id=None,
                submitted_by_id=priya.id,
                source=FeedbackSource.app_review,
                theme="payments",
                platform="android",
                sentiment=FeedbackSentiment.negative,
                status=FeedbackStatus.new,
                body='Play Store 1-star cluster: "Payment keeps failing after update", "Can\'t pay with GPay anymore", "Went back to the website to order". 23 reviews in three days versus a usual 3–4.',
            ),
            fb(
                android_date,
                5,
                stakeholder_id=stakeholders["Kabir Shah"].id,
                submitted_by_id=priya.id,
                source=FeedbackSource.internal,
                theme="payments",
                platform="android",
                sentiment=FeedbackSentiment.neutral,
                status=FeedbackStatus.planned,
                body="Android team can ship 8.4.1 with the collect-request timeout raised to 120s and the intent flow restored as fallback within two days if we hold the rollout at the current percentage.",
                linked_entity_type="release",
                linked_entity_id=android.id,
            ),
            fb(
                campaign_start,
                6,
                stakeholder_id=stakeholders["Neha Kulkarni"].id,
                submitted_by_id=rohan.id,
                source=FeedbackSource.internal,
                theme="acquisition",
                platform=None,
                sentiment=FeedbackSentiment.neutral,
                status=FeedbackStatus.triaged,
                body="Paid social CPMs are excellent on the new lookalike campaign and click-through is above benchmark. Growth would like to scale spend 3x next week unless product sees a quality problem.",
                linked_entity_type="investigation",
                linked_entity_id=inv_paid.id,
            ),
            fb(
                campaign_start,
                9,
                stakeholder_id=None,
                submitted_by_id=arjun.id,
                source=FeedbackSource.survey,
                theme="acquisition",
                platform=None,
                sentiment=FeedbackSentiment.negative,
                status=FeedbackStatus.triaged,
                body="Exit survey on landing pages from paid social: top answer to 'why are you leaving' is 'I was just browsing' (54%), followed by 'prices higher than expected' (21%). Organic visitors pick 'couldn't find my size' first.",
                linked_entity_type="investigation",
                linked_entity_id=inv_paid.id,
            ),
            fb(
                sc.day(20),
                0,
                stakeholder_id=stakeholders["Ananya Bose"].id,
                submitted_by_id=rohan.id,
                source=FeedbackSource.interview,
                theme="product_page",
                platform=None,
                sentiment=FeedbackSentiment.neutral,
                status=FeedbackStatus.triaged,
                body="In five usability sessions on the sticky CTA variant, three participants added to cart before reading the size guide and two of those said they would 'sort it out at checkout'. Worth watching return reasons.",
                linked_entity_type="experiment",
                linked_entity_id=experiments["new_pdp_cta"].id,
            ),
            fb(
                sc.day(16),
                0,
                stakeholder_id=stakeholders["Sameer Joshi"].id,
                submitted_by_id=rohan.id,
                source=FeedbackSource.internal,
                theme="search",
                platform=None,
                sentiment=FeedbackSentiment.positive,
                status=FeedbackStatus.addressed,
                body="Relevance v2 halved zero-result searches for brand+colour queries in the offline eval. Would like a product read on whether search-to-product-view moved after launch.",
            ),
            fb(
                sc.day(12),
                0,
                stakeholder_id=None,
                submitted_by_id=priya.id,
                source=FeedbackSource.support,
                theme="delivery",
                platform=None,
                sentiment=FeedbackSentiment.negative,
                status=FeedbackStatus.new,
                body="Tier-3 city customers asking why the delivery estimate on the product page says 4–5 days but the order confirmation says 7–9. Fourteen tickets, all Tier 3, all from the last ten days.",
            ),
            fb(
                sc.day(9),
                0,
                stakeholder_id=stakeholders["Vikram Menon"].id,
                submitted_by_id=priya.id,
                source=FeedbackSource.internal,
                theme="returns",
                platform=None,
                sentiment=FeedbackSentiment.positive,
                status=FeedbackStatus.addressed,
                body="Sandals range republished with corrected size chart; first week return rate on the range is back in line with the footwear baseline. Supplier onboarding SOP updated with the size-chart check.",
                linked_entity_type="investigation",
                linked_entity_id=inv_old.id,
            ),
            fb(
                sc.day(4),
                0,
                stakeholder_id=None,
                submitted_by_id=arjun.id,
                source=FeedbackSource.sales,
                theme="pricing",
                platform=None,
                sentiment=FeedbackSentiment.neutral,
                status=FeedbackStatus.new,
                body="B2B team reports two boutique partners asking for the free-shipping threshold to apply to bulk orders too; they are currently splitting carts to get under it.",
                linked_entity_type="experiment",
                linked_entity_id=fst.id,
            ),
        ]
    )

    db.add(
        SavedAnalysis(
            project_id=project.id,
            owner_id=arjun.id,
            kind="analysis",
            name="Payment success by platform",
            description="Weekly payment success rate broken down by platform.",
            config={
                "metric": "payment_success_rate",
                "breakdown": "platform",
                "granularity": "day",
                "filters": [],
            },
        )
    )
    db.flush()

    return {
        "project_id": project.id,
        "users": {email: u.id for email, u in users.items()},
        "android_release_id": android.id,
        "investigations": {"paid_social": inv_paid.id, "footwear": inv_old.id},
    }

def link_anomalies_to_investigations(db: Session, project_id: int) -> int:
    """Attach detected anomalies to the seeded investigations that are about them.

    Matching is on metric + scope + overlapping window, the same rule a PM would
    apply by hand. Runs after detection so the demo opens with the paid-social
    investigation already tied to its inbox entry.
    """
    linked = 0
    investigations = db.scalars(select(Investigation).where(Investigation.project_id == project_id)).all()
    anomalies = db.scalars(
        select(Anomaly).where(Anomaly.project_id == project_id, Anomaly.investigation_id.is_(None))
    ).all()
    for inv in investigations:
        for a in anomalies:
            if a.investigation_id is not None or a.metric_key != inv.metric_key:
                continue
            if not same_filters(a.filters, inv.filters):
                continue
            if a.period_end < inv.period_start or a.period_start > inv.period_end:
                continue
            a.investigation_id = inv.id
            closed = inv.status in (InvestigationStatus.resolved, InvestigationStatus.closed)
            a.status = "resolved" if closed else "investigating"
            linked += 1
    db.flush()
    return linked

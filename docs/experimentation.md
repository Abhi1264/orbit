# Experimentation

How Orbit assigns users, reads results, and turns a readout into a
ship / iterate / stop / continue recommendation. Code lives in
`apps/api/probelens/experiments/`.

## Lifecycle

```
draft ──start──▶ running ──end──▶ completed
                    │
                    └──stop──▶ stopped
```

* **Draft.** Everything is editable: hypothesis, primary metric, guardrails,
  audience, variants, traffic, decision rules.
* **Running.** The design is frozen. Only bookkeeping (name, description,
  end date) can change; changing the design mid-flight would be a different
  experiment, so the API refuses (`400`).
* **Completed / stopped.** Recording a decision on a running experiment moves it
  here automatically (`stop` → stopped, anything else → completed) and sets the
  end date to the data's latest day.

Decision rules are written down **before** the experiment starts and drive the
recommendation later:

| Rule | Default | Meaning |
|---|---|---|
| `min_relative_effect` | 2% | The smallest relative lift on the primary metric worth shipping for. Drives the power check. |
| `min_sample_per_variant` | 2,000 | Users per variant before a result is read at all. |
| `min_duration_days` | 7 | Covers weekday seasonality. |

## Assignment

Two kinds of experiment are analysed identically:

1. **Exposure events in the stream** (the seeded ones). Each event carries an
   `experiments` map (`Map(String, String)`, experiment key → variant). A user's
   variant is the value on their **first** exposure; users seen under more than
   one variant are counted as *cross-exposed* and analysed under their first.
2. **App-created experiments** (no logged exposures). Users are assigned
   retroactively by deterministic hashing, so an experiment created in the UI
   can still be read against historical data. Without a real treatment this
   yields an A/A test, which is what it should do.

The hash is `MD5("{experiment_key}:{user_id}")`, first four bytes little-endian,
modulo 10,000 buckets. Traffic allocation takes the first `traffic_percent` of
buckets; variants split that range proportionally to weight. The Python
(`assignment.assign`) and ClickHouse (`assignment.variant_case_sql`)
implementations are verified against each other in
`tests/test_assignment_sql.py`, because a silent divergence there would make
every retroactive readout wrong.

## Statistics

**Unit of analysis is the user**, not the session or the order. This matters
because most of our metrics are session rates (add-to-cart rate, checkout
conversion) and users have many sessions: treating sessions as independent
would understate variance and overstate significance.

Each metric is a ratio of per-user sums, `Σnum / Σden`. Per variant we compute
the per-user sufficient statistics in ClickHouse (`n`, `Σnum`, `Σden`,
`varSamp(num)`, `varSamp(den)`, `covarSamp(num, den)`) and derive the
estimator's variance with the **delta method**:

```
Var(R) ≈ (Var(num) − 2·R·Cov(num, den) + R²·Var(den)) / (mean(den)² · n)
```

Per-user means (revenue per user) are the special case `den = 1`, where this
reduces to the ordinary t-test variance. Differences between variants use a
two-sided z-test with 95% intervals reported on both the absolute and relative
lift. `tests/test_experiment_stats.py` checks that the interval widens
appropriately under clustering and that the false-positive rate on A/A data
sits near α.

**Outcome window.** Exposures are counted between the experiment's start and
end dates; outcomes are measured from each user's first exposure through the
latest day in the data. Lagged metrics (returns, deliveries) therefore get
their tail even after the experiment ends, and the readout says so in its
notes.

**Sample ratio mismatch.** A chi-square goodness-of-fit test compares exposure
counts against the configured weights. The alarm threshold is strict
(`p < 0.001`) because with tens of thousands of users a benign-looking
50.4/49.6 split is wildly unlikely. An SRM invalidates every other number and
the recommendation says so first.

**Power.** From the control's per-user variance we compute the sample size
needed to detect `min_relative_effect` at 80% power (α = 0.05), the effect
detectable with the current sample, and, for running experiments, the days
until powered at the current exposure rate.

**Segments** (platform, new vs returning) use the user's attribute at first
exposure so each user lands in exactly one segment. They are labelled
exploratory in the UI and memo: with several segments some will look
significant by chance.

## Recommendation

`decision.recommend` is deliberately rule-based and lists every check it ran.
In order:

1. **Sample ratio.** Mismatch → `stop`, "do not read these results".
2. **Minimums.** Sample and duration; both are reported, neither alone blocks.
3. **Power.** Whether the current sample can detect the target lift.
4. **Primary metric.** Significantly better / worse / flat.
5. **Guardrails.** Any significantly worse guardrail is a regression. A
   guardrail that is *not* significant but whose point estimate leans the
   wrong way and whose interval allows more than 10% relative degradation is
   flagged **inconclusive**: "not significant" is not "safe".

| Primary | Guardrails | Minimums | Result |
|---|---|---|---|
| better | intact | met | **ship** (high if powered, medium otherwise; downgraded once more if a guardrail is inconclusive) |
| better | intact | not met | **continue**: early significance often shrinks |
| better | regressed | – | **iterate**: a trade-off, not a ship decision |
| worse | – | – | **stop** |
| flat | regressed | – | **stop** |
| flat | intact | powered | **stop**: any real effect is below the lift worth shipping |
| flat | intact | underpowered, ended | **iterate**: inconclusive |
| flat | intact | underpowered, running | **continue**, with an ETA |

The recommendation is input to the human decision. Recording a decision
(`POST /experiments/{id}/decision`) stores the decision, rationale and author
on the experiment and, by default, appends an entry to the decision log with
the primary-metric readout as evidence. Overruling the recommendation is
allowed and shown as such in both the UI and the memo.

## Decision memo

`GET /experiments/{id}/memo` renders a Markdown memo from the same readout:
header, hypothesis, recommendation (with the recorded decision and rationale
if any), per-metric tables with intervals and p-values, segments, validity
checks, notes and a short method section. No LLM is involved, so it is
reproducible and every number traces to a query. The UI renders it, and offers
copy / download for pasting into the decision doc.

## Seeded experiments

| Key | Story |
|---|---|
| `free_shipping_threshold` | Clean win on checkout conversion, AOV up, returns flat. Completed and shipped. |
| `new_pdp_cta` | Add-to-cart rate up ~7%, but the return-rate guardrail is *inconclusive* (point estimate worse, wide interval). Ships with a follow-up monitor. |
| `search_autocomplete_v2` | Running at 30% traffic, six days in; underpowered, keep running. |

## API

| Method | Path | Permission |
|---|---|---|
| `GET` | `/api/experiments` | view |
| `POST` | `/api/experiments` | manage_experiments |
| `GET` | `/api/experiments/{id}` | view |
| `PATCH` | `/api/experiments/{id}` | manage_experiments (owner, PM or admin) |
| `DELETE` | `/api/experiments/{id}` | manage_experiments; drafts only |
| `GET` | `/api/experiments/{id}/results?as_of=` | view |
| `GET` | `/api/experiments/{id}/memo?as_of=` | view |
| `POST` | `/api/experiments/{id}/decision` | decide_experiments |

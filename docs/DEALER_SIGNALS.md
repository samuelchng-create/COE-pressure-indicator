# Dealer-signal dataset and ingestion workflow (2024–2026)

## Observation grain and provenance

One row is one observed dealer offer for a brand/model/variant at a point in
time. `observed_at` is the time the offer was visibly effective;
`retrieved_at` is the immutable capture time. Every row has a stable
`observation_id` and `source_url`. Raw captures or hashes should be retained
outside this repository so later corrections do not overwrite history.

The versioned CSV schema covers advertised and previous price, COE rebate,
guaranteed-COE status/bid count/terms, finance/trade-in/cash/other incentives,
promotion deadlines, roadshow windows and market-share weight. Monetary fields
are SGD and missing values mean “not observed,” not zero, except that incentive
components are summed with missing components treated as zero only after the
row has passed validation.

## Collection workflow

1. Capture dealer pages, price lists, advertisements and roadshow offers on a
   regular cadence. Record both observation and retrieval timestamps.
2. Append; never revise a historical row in place. Corrections receive a new
   observation ID and an audit note.
3. Validate required fields, category values, positive advertised prices,
   Boolean guaranteed-COE terms and non-negative market-share weights.
4. Maintain a separate official tender schedule with `tender_id`, `category`,
   `forecast_cutoff_at`, actual close time, quota announcement URL and release
   time.
5. At each frozen forecast cutoff, aggregate only rows with `retrieved_at` and
   `observed_at` no later than the cutoff, normally over a 21-day lookback.
6. Store the resulting tender feature row and model version before the result is
   known. Do not recompute a published forecast using later corrections.

Market-share weights must come from a versioned source available at that cutoff.
They are observation weights for aggregation, not hand-tuned index weights.

## Empirical test

Use exactly the same outer walk-forward origins, structural features, training
window and inner model-selection procedure for both candidates:

1. structural-only;
2. structural plus pre-cutoff dealer aggregates.

Report paired differences in absolute and squared error by category, direction
accuracy, interval coverage and sample count. Because the dealer history starts
in 2024, also report a structural-only back-test restricted to the same 2024–
2026 origins. The primary claim requires lower out-of-sample MAE than the
structural-only model; RMSE, direction and coverage are supporting metrics.
Feature definitions and candidate models must be frozen before examining the
final holdout period. If uplift is absent or unstable, publish that negative
result and do not release calibrated weights or probabilities.

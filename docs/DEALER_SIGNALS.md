# Dealer-signal dataset and ingestion workflow (2024–2026)

## Observation grain and provenance

The SGCarMart v0.8 research row is a brand/category/page summary at a point in
time, not a claim that every model and variant was normalized. `observed_at` is
the dated price-list effective time; `available_at` is the evidence-based
public availability time used for historical cutoffs; `retrieved_at` is the
later immutable research capture time. Every row has a stable `observation_id`,
source URL and PDF checksum. The source manifest preserves failed requests and
retrieval timestamps.

Because the historical archive supplies a document date rather than a precise
publication time, `available_at` is conservatively set to 23:59:59 Singapore
time on that date. When contemporaneous collection proves the document was
public earlier, the recorded collection time is used instead. A historical
price list dated on a tender's opening day is therefore not treated as
available at the noon forecast cutoff without such evidence.

The versioned CSV schema covers advertised and previous price, COE rebate,
guaranteed-COE status/bid count/terms, finance/trade-in/cash/other incentives,
explicitly labelled advertised `finance_rate_pct`, promotion deadlines,
roadshow windows and market-share weight. Monetary fields
are SGD and missing values mean “not observed,” not zero, except that incentive
components are summed with missing components treated as zero only after the
row has passed validation.

## Collection workflow

1. Enumerate SGCarMart's public authorised-dealer price-list archive and retain
   all dated PDFs for the selected brands from 2024 through the collection
   cutoff. Respect the site's crawl delay.
2. OCR each page. Accept a page into the experiment only when it has an
   explicit Cat A/B heading and at least one advertised price. Keep
   unclassified pages as review/context rows.
3. Summarize repeated advertised-price column values, explicit COE
   package/rebate amounts, guaranteed/non-guaranteed bid terms, discounts,
   finance/trade-in text and offer validity dates. Never impute missing terms.
4. Record observation, evidenced availability and research retrieval
   timestamps separately.
5. Append; never revise a historical row in place. Corrections receive a new
   observation ID and an audit note.
6. Validate required fields, category values, positive advertised prices,
   Boolean guaranteed-COE terms and non-negative market-share weights.
7. Maintain a separate official tender schedule with `tender_id`, `category`,
   `forecast_cutoff_at`, actual close time, quota announcement URL and release
   time.
8. At each retrospective cutoff, aggregate only rows with `available_at` and
   `observed_at` no later than the cutoff, over a declared lookback. The later
   `retrieved_at` timestamp remains visible to distinguish archive
   reconstruction from contemporaneous collection.
9. Store the resulting tender feature row and model version before the result is
   known. Do not recompute a published forecast using later corrections.

Market-share weights are calculated from LTA monthly registrations over the 12
complete months preceding each observation month. They are observation weights
for aggregation, not hand-tuned index weights. Brand-level registrations are
not a category-specific sales split, which is a stated limitation.

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

## v0.8 twenty-brand-group rerun (collection cutoff 2 September 2026)

- 1,487 dated PDFs from 23 SGCarMart source marques representing the 20
  requested groups were retrieved without a failed request; 3,774 PDF page
  summaries remain in the audit table. The source dates run through 1 September
  2026.
- 1,124 observations passed the explicit Cat A/B label and advertised-price
  rules: 673 Cat A and 451 Cat B rows across BYD, Toyota/Lexus,
  Chery/Omoda/Jaecoo, GAC/Aion, Honda, Hyundai, Kia, Mazda, Nissan, Suzuki and
  Zeekr. The other requested groups remain context-only because their pages did
  not satisfy the same deterministic eligibility rules.
- Toyota and Lexus retain separate source attribution but use the consolidated
  LTA Toyota registration series; Omoda and Jaecoo map to Chery; Aion maps to
  GAC; and MG maps to LTA's `M.G.` label. The latest official LTA release was
  published in August 2026 and its CSV runs through July 2026.
- 135 observations contain a valid explicitly labelled advertised finance
  rate, all from Honda and ranging from 2.58% to 2.78%. Broad percentage text
  is not parsed as interest, and no motorcycle rate is inferred.
- The paired dealer test contains 51 one-tender-ahead forecasts per category.
- Cat A structural-plus-dealer MAE was S$3,284 versus S$3,327 structural-only,
  a 1.27% improvement. RMSE improved only 0.03%; direction accuracy was
  unchanged at 68.6%. The combined 80% interval covered 92.3% and remained
  materially wider.
- Cat B structural-plus-dealer MAE was S$4,814 versus S$4,348 structural-only,
  a 10.71% deterioration. RMSE deteriorated 14.22%; direction accuracy was
  47.1% versus 51.0%. The combined 80% interval covered 82.1% and was wider.

The category results are mixed and the Cat A improvement is small,
retrospectively reconstructed and accompanied by a much wider interval. This
does not support publishing a composite Dealer Pressure Index, calibrated
probabilities, or a dealer-model forecasting-edge claim. A prospectively frozen
dealer archive remains the next validation stage.

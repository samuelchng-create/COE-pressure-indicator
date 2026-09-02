# v0.8 dealer and exact-cutoff economy refresh methodology

## Common analysis window

All charts, structural features, expanding training windows, inner tuning
folds, conformal calibration errors and benchmark metrics begin in October
2015. No pre-October-2015 COE tender can enter any fitted model. The SGCarMart
dealer archive begins in 2024, while its underlying structural forecast is
trained only on the same post-policy COE window. Economic features are likewise
materialized only from October 2015 onward.

## MVP audit findings

1. Numeric strings containing commas were coerced to missing values. This made
   recent live charts empty and excluded recent tenders from evaluation.
2. The original Ridge model was fit on unscaled features with a fixed penalty,
   making the effective shrinkage depend on each column's units.
3. Month number was treated as an ordinal variable rather than cyclical
   seasonality.
4. Cat E and announced target-tender supply were not represented.
5. Only persistence MAE was shown. RMSE, multiple naïve benchmarks, forecast
   interval coverage and the number of evaluated predictions were absent.
6. The dealer CSV had no provenance/retrieval timestamps, market-share weight,
   or enforceable as-of cutoff, so it could not support a leakage-safe test.

The original premium and bid-pressure features were lagged, so no direct
same-tender outcome leakage was found in those columns. Its approximate chart
date was not an actual tender closing date.

## Forecast contract

The unit is one category in one bidding exercise. The model predicts premium
change from the preceding completed tender. All outcome-derived inputs are
shifted by one or more tenders. Target-tender quota and target-tender Cat E quota
are the only contemporaneous structural inputs and are treated as announced
before bidding.

The data.gov.sg results table records month and bidding number but not the quota
announcement timestamp or actual closing timestamp. This is sufficient for
ordered structural back-testing, but prospective forecasts and the dealer test
must use an archived tender schedule with `forecast_cutoff_at` and the source
quota announcement.

## Evaluation

Each outer step trains only on earlier tenders. Ridge alpha is selected only
inside that training sample with time-ordered inner folds. Predictions are never
revised. Metrics are reported over identical outer test origins for:

- structural model;
- persistence (next premium equals previous premium);
- expanding historical mean drift; and
- two-tender seasonal persistence.

The app reports direction accuracy, MAE, RMSE, improvement over the lowest-MAE
naïve benchmark, and coverage of an 80% prequential conformal interval. The
interval at a tender uses only absolute errors from earlier outer predictions.

## Interpretation

Back-test improvement is descriptive, not a guarantee. Where structural MAE
does not beat the best naïve benchmark, the app says so. v0.2 publishes neither
an upcoming-tender probability nor a composite Dealer Pressure Index.

## v0.8 dealer experiment contract

The experiment predicts the already out-of-sample structural model's residual
using only dealer features from earlier tender cutoffs. It uses an expanding
window; Ridge regularization is selected in time-ordered inner folds. The
comparison is therefore structural-only versus structural-plus-dealer over the
same outer origins. It reports MAE, RMSE, direction accuracy and 80% prequential
interval coverage, with persistence retained as a reference.

The dealer history is a retrospective reconstruction from dated SGCarMart
price-list documents. `available_at` uses the document's dated effective/public
availability evidence; `retrieved_at` records the later research collection.
PDF checksums and source URLs make that assumption auditable. This is weaker
than a prospectively frozen archive and must be followed by live frozen
validation before any calibrated probability or dealer index is published.
Date-only historical archive availability is assigned to end-of-day Singapore
time, so a document dated on a tender opening day cannot enter that noon cutoff.
When contemporaneous collection directly proves an earlier public time, that
recorded collection timestamp is used instead.

The v0.8 archive covers 20 requested groups through 23 SGCarMart source
marques. Toyota/Lexus, Chery/Omoda/Jaecoo and GAC/Aion are grouped for display
and mapped to the corresponding consolidated LTA make series, while the source
marque remains in each audit note. Only 11 groups produce model-eligible rows;
the rest remain visible context and are not imputed.

The candidate includes only explicitly labelled advertised finance rates.
Values outside 0.1%–15% are invalid, preventing percentages for discounts,
deposits or other terms from being misclassified as interest. The usable rate
history contains 135 Honda observations between 2.58% and 2.78%; it is neither
market-wide nor motorcycle data. The car dealer experiment continues to exclude
Category D.

## v0.8 economy, financial-markets and vehicle-financing contract

The economy experiment fits the same standardized Ridge change model and makes
a three-way paired comparison: structural-only, structural plus 13 economy and
market variables, and that block plus the MAS three-year new-vehicle
hire-purchase rate and its staleness. All candidates use identical outer
forecast origins and separately select regularization inside each training
window. The primary structural forecast is not replaced unless an augmented
model improves frozen out-of-sample error.

Daily SGD/USD, Nasdaq Composite, VIX, US 10-year Treasury and Brent observations are assigned an
availability timestamp of noon Singapore time on the following calendar day.
Changes compare the last observation before the tender cutoff with the last
observation at least 30 calendar days earlier. Singapore CPI is treated as
available 45 days after month-end; real-GDP growth and unemployment are treated
as available 75 days after quarter-end.

From 2024 onward, the tender cutoff is the exact opening timestamp in the
versioned official LTA schedule. Earlier tenders retain an ordered 1st/15th
approximation because the historical results table lacks opening timestamps.

The MAS monthly vehicle rate is assigned a conservative month-end-plus-45-day
availability date. MAS does not publish separate car and motorcycle histories
in this table, so the rate is a common market proxy for Categories A, B and D.
The retrieved series ends in April 2023. A staleness-days feature accompanies
the last available value, and no vehicle-type-specific history is imputed.

These macro rules are conservative publication buffers, not reconstructed
release timestamps. SingStat serves current-vintage data that may contain later
revisions. Therefore the economy results are a revision-risk sensitivity test, not
a fully vintage-correct real-time back-test. The post-policy paired test covers
193 forecasts per category. The 13-variable economy core worsens MAE by 0.37%
for Cat A, improves it by 0.43% for Cat B, and worsens it by 4.29% for Cat D.
This mixed, marginal result leaves the
variant as a visible research candidate rather than the deployed primary model.
Adding financing to that economy block worsens MAE a further 0.33% for Cat A,
1.21% for Cat B and 1.02% for Cat D. Against structural-only, the 15-variable
variant worsens MAE by 0.70%, 0.78% and 5.36%, respectively, so it also remains
experimental.

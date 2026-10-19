# v0.14 consultation, multi-cycle, tender-timing, probability, dealer and economy methodology

## v0.14 October 2026 consultation scenarios

The consultation tab transcribes LTA's indicative three-band and five-band OMV
feebate structures and applies them to a disclosed quota-weighted Category A/B
price proxy. Historical proxy values use only completed tender premiums and
quotas from the common October 2015 analysis window. The next-exercise planning
proxy quota-weights the existing separate Cat A/B forecasts with the official
announced quotas when the tender identity matches.

This is not a merged-auction model. Aggregate LTA results do not disclose
individual bid values, so the merged order book, demand substitution and market
clearing price are not identified. The counterfactual therefore separates the
mechanical feebate effects from the unknown auction equilibrium and excludes
Category E redesign, renewal transitions and dealer absorption. Full assumptions
and metrics are in `docs/COE_CONSULTATION_SCENARIOS.md`.

## Direct multi-cycle forecast contract

The experimental v0.12 layer predicts the terminal premium 1, 2, 4 and 6
completed exercises ahead. A separate direct Ridge model is fitted for every
category and horizon. Forecasts are not recursively chained. At an origin
exercise `t`, inputs contain completed outcomes through `t`, the announced
quota for `t+1`, calendar-known timing and seasonality, and no outcome from
`t+1` onward. Supply after `t+1` is not represented as known.

Multi-horizon labels overlap, so ordinary expanding-window slicing would leak
future outcomes. For a test made at origin `t`, a training example is eligible
only when its own target exercise had completed by `t`. Ridge tuning uses only
that embargoed training set. Conformal intervals and empirical direction
probabilities use earlier out-of-sample errors from the same category and
horizon.

Categories A and B use a dealer-oriented Stay definition of ±S$2,000 in this
tab; Category D retains ±S$1,000 because a ±S$2,000 motorcycle band classifies
almost every historical outcome as Stay. The original one-cycle category tabs
retain their ±S$1,000 definition for comparability. Exact dollar changes are
shown in both views.

## Tender-calendar and extended-demand exposure

Official LTA annual schedules provide opening and closing timestamps from 2017
through 2026. The 2017 source is the revised calendar issued after the February
policy postponement. Close-to-close days, weeks, intervals of at least 19 days,
quota per week and lagged bids per week enter the experimental timing-aware
model. Calendar spans are computed over the actual sequence of completed
exercises, so the April–June 2020 bidding suspension is treated as a long gap
rather than as ordinary planned tenders.

When a live horizon extends beyond the bundled official schedule, the app
projects only the missing close-to-close interval at 14 days and labels that
calendar input as projected. The current six-exercise outlook contains one such
interval in January 2027; it is not represented as an official LTA date.

The analysis window still begins in October 2015. Historical multi-horizon test
origins begin only after the 60-example training requirement, by which point
official calendar coverage is available. No 2015–2016 timestamp is silently
reconstructed.

Normal paths and paths containing at least one extended interval are reported
separately. A longer interval is an exposure feature, not an assumed fixed
premium uplift; the coefficient is estimated inside each historical training
window.

## Dealer-package horizon alignment

For observations with an explicit guaranteed bid count, coverage begins at the
first exercise opening strictly after the document's evidenced availability
timestamp. The audit dataset stores the first and last covered tender, calendar
days to the final closing date and intervening extended-gap count. This is a
conservative reproducible alignment assumption, not a claim about a dealer's
unobserved internal bidding plan. Dealer uplift remains separately experimental
because only the 2024–2026 reconstructed archive is available.

For each 1/2/4/6-exercise test, dealer variables are frozen at the official
opening cutoff of the first upcoming exercise. A Ridge model predicts the
direct structural forecast's residual. A historical residual becomes eligible
for training only when its own terminal target exercise had completed by the
new forecast origin. This second embargo is necessary because simply ordering
dealer rows by first upcoming tender would leak unfinished multi-cycle labels.
The paired sample contains 54/52/48/44 forecasts at horizons 1/2/4/6. Only Cat
A at one exercise improves MAE (+2.9%); Cat A at 2/4/6 and Cat B at all four
horizons worsen MAE. No live dealer adjustment is therefore published.

## Multi-horizon economy, markets and financing comparison

The 13-variable economy/markets block and the 15-variable block that also
contains the MAS vehicle hire-purchase rate and its age are re-fitted directly
at every category/horizon pair. Each comparison uses the same origins as its
structural model and the same terminal-label embargo. The economy/markets block
improves Cat A MAE at 2/4/6 exercises and Cat B MAE at all four horizons (from
+0.1% to +4.3%), but is slightly worse for Cat A at one exercise and worse for
Cat D. Adding the financing proxy worsens all twelve comparisons. These
are current-vintage macro sensitivity tests, not prospectively frozen model
upgrades, so neither candidate changes the live structural forecast.

## v0.10 official final-results bridge

The app normally reads completed tender records from data.gov.sg. Because that
archive can synchronise after LTA publishes the result on OneMotoring, the app
also checks the official OneMotoring COE Open Bidding page. It accepts a record
from that page only when a confirmed `Results for ... Open Bidding Exercise`
or `Final Results for ... Open Bidding Exercise` heading is present and both result tables contain Categories A–E exactly once,
including premium, quota, bids received and successful bids. A live bidding
table or a page saying results are being finalised is not admitted to model
training. Once data.gov.sg contains the same tender, its archive record takes
precedence and the bridge adds nothing. Both checks use a five-minute cache.
The separate quota parser may read only the announced quota column from an
identified next-exercise or live-bidding table; current prices and bid counts
remain excluded from both training and forecasting inputs.

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
does not beat the best naïve benchmark, the app says so. No composite Dealer
Pressure Index is published.

## v0.9 three-way probability contract

The next-exercise display classifies the premium change as Increase when it is
above S$1,000, Stay when it is between −S$1,000 and +S$1,000 inclusive, and
Decrease when it is below −S$1,000. The structural Ridge point forecast is not
converted to a probability with an assumed normal distribution. Instead, it is
shifted by the empirical distribution of earlier expanding-window
out-of-sample residuals. The shares falling in the three outcome regions become
probabilities after one-count Laplace smoothing.

Probability evaluation is itself prequential. At every historical origin, the
residual distribution and historical-frequency baseline contain only earlier
outcomes. Evaluation begins after 20 earlier out-of-sample residuals and reports
multiclass Brier score, log loss, highest-probability three-way accuracy and
Brier improvement versus the historical-frequency probability baseline. A
future outcome cannot revise any earlier probability.

The live next-exercise row uses the official LTA announced category and Cat E
quotas only when OneMotoring identifies the same tender ID that the completed
results sequence expects. If that strict match is unavailable, the last
completed quotas are carried forward and disclosed as a fallback. Provisional
prices and live bid counts never enter the feature row. The probabilities
remain experimental and are not called calibrated until future frozen forecasts
validate them.

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
history contains 138 Honda observations between 2.58% and 2.78%; it is neither
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
196 forecasts per category. The 13-variable economy core worsens MAE by 0.74%
for Cat A, worsens it by 0.14% for Cat B, and worsens it by 4.22% for Cat D.
This result leaves the
variant as a visible research candidate rather than the deployed primary model.
Adding financing to that economy block worsens MAE a further 0.36% for Cat A,
1.21% for Cat B and 1.06% for Cat D. Against structural-only, the 15-variable
variant worsens MAE by 1.10%, 1.36% and 5.32%, respectively, so it also remains
experimental.

# v0.2 methodology and audit

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

# Singapore COE Pressure Indicator — v0.9 three-way outlook

An experimental Streamlit tracker for Singapore COE Categories A, B and D. It
loads official tender-level results, runs leakage-safe expanding-window
back-tests, compares the structural forecast with three naïve benchmarks, and
reports direction accuracy, MAE, RMSE and prequential interval coverage.

The app does **not** claim that a Dealer Pressure Index, model probability or
forecast edge is prospectively calibrated. Negative benchmark results remain visible.

Every chart, training window, tuning fold, uncertainty interval and benchmark
now uses a common October 2015 analysis start. Earlier tenders are excluded to
avoid mixing materially different policy regimes into the reported results.

## v0.9 next-exercise probability outlook

- Reports an experimental three-way forecast for each category: **Increase**
  above S$1,000, **Stay** within ±S$1,000 inclusive, or **Decrease** below
  −S$1,000.
- Forms probabilities from the current structural point forecast plus the
  empirical distribution of earlier out-of-sample structural errors. Laplace
  smoothing prevents unsupported zero probabilities.
- Back-tests every historical probability prequentially: a tender can use only
  errors observed before that tender. Multiclass Brier score, three-way
  accuracy and improvement over an earlier-outcome-frequency probability
  baseline are displayed beside the forecast.
- Treats the probabilities as experimental even when the retrospective Brier
  score improves. Prospective frozen forecasts are still required before any
  calibration claim.
- Carries the last completed category and Cat E quotas into the upcoming row as
  a disclosed neutral supply assumption until a timestamped upcoming quota
  announcement is added. The structural point forecast and the most probable
  outcome can differ when the historical residual distribution is asymmetric.
- Adds plain-language hover help to every headline dashboard indicator.

## v0.8 SGCarMart dealer refresh

- Reconstructs dated 2024–2026 authorised-dealer price-list signals for 20
  requested groups: BYD; Toyota/Lexus; Tesla; Mercedes-Benz; BMW;
  Chery/Omoda/Jaecoo; GAC/Aion; MG; Honda; Nissan; Kia; Zeekr; Xpeng; Hyundai;
  Audi; Suzuki; Dongfeng; Porsche; Volvo; and Mazda. These correspond to 23
  distinct SGCarMart source marques.
- Stores each source URL, PDF date, later research retrieval timestamp and
  SHA-256 checksum. `available_at` is separate from `retrieved_at` so the
  retrospective as-of assumption is explicit and auditable.
- Produces model-eligible page summaries only when the PDF contains an explicit
  Category A or B heading and advertised prices. Unclassified pages remain in
  the research workbook for review.
- Uses the median advertised package price on each eligible category-labelled
  page, explicit COE package/rebate terms, bid guarantees, discounts,
  promotion deadlines, finance/trade-in text and explicitly labelled advertised
  interest rates. It does not claim complete model/variant normalization.
- Weights brands using their LTA new registrations over the preceding 12
  complete months, divided by all makes. These are aggregation weights, not a
  hand-built Dealer Pressure Index.
- Tests a Ridge residual correction over exactly the structural model's
  out-of-sample predictions with expanding windows and reports whether dealer
  data actually improves MAE/RMSE/direction/interval coverage.
- Excludes Category D because SGCarMart's car price-list archive is not a
  motorcycle dealer archive.

The refreshed archive contains 1,487 source PDFs, 3,774 auditable page rows and
1,124 model-eligible observations from 11 grouped brands. It contains 135 explicit
advertised car-finance rates, all from Honda documents and ranging from 2.58%
to 2.78%; this narrow coverage is disclosed. The latest SGCarMart document is
dated 1 September 2026. Over 51 paired forecasts per category, the v0.8 dealer
variant improved Cat A MAE by 1.27% but worsened Cat B MAE by 10.71%. The small
retrospective Cat A result is not treated as a validated edge, and no calibrated
Dealer Pressure Index or probabilities are published.

## v0.8 economy, markets and vehicle-financing refresh

- Retains 13 tender-aligned variables: SGD/USD level and 21-day change, VIX level
  and change, US 10-year Treasury yield and change, Brent price and return,
  Nasdaq Composite level and return,
  Singapore real-GDP growth, CPI inflation and unemployment.
- Adds the MAS three-year finance-company hire-purchase rate for new vehicles
  and the number of days since its underlying month. MAS does not split this
  official series between cars and motorcycles, so it is tested as a common
  market-financing proxy for Cat A, B and D rather than a type-specific rate.
- Treats daily market observations as available in Singapore only on the next
  calendar day. Monthly CPI uses a 45-day publication buffer; quarterly GDP
  and unemployment use 75 days.
- Uses exact official LTA tender-opening cutoffs from 2024 onward. Earlier
  tenders retain the ordered first/second-exercise date approximation because
  the results table does not contain historical opening timestamps.
- Runs a three-way paired expanding-window comparison at the same 193 forecast
  origins: structural, structural plus the 13-variable economy block, and that
  block plus financing. Relative to the economy block, financing worsened MAE
  by 0.33% for Cat A, 1.21% for Cat B and 1.02% for Cat D. Relative to the
  structural model, the 15-variable version worsened MAE by 0.70%, 0.78% and
  5.36%, respectively. It is not promoted over the structural model.
- The official rate currently ends in April 2023. The explicit staleness
  feature prevents a carried-forward value from being mistaken for a fresh
  observation. No unsupported motorcycle-specific history is imputed.
- Uses current-vintage SingStat macro tables. The publication buffers prevent
  use of the current period too early, but historical revisions remain a known
  limitation until a real-time vintage archive is obtained.

## v0.5 structural method

- Predicts the next tender's premium change separately by category.
- Uses lagged premiums, momentum, lagged bid-to-quota/excess demand, announced
  target-tender quota, lagged Cat E signals, and cyclical seasonality.
- Treats target-tender quota as known pre-tender supply. The official results
  table has no publication timestamp, so future forecasts must archive the
  source LTA announcement.
- Selects Ridge regularization inside each expanding training window with
  time-ordered inner validation folds.
- Compares against persistence, historical mean drift and two-tender seasonal
  persistence.
- Builds 80% prequential conformal intervals from earlier out-of-sample errors
  only.

Across 193 post-policy forecasts, structural MAE is S$2,844 for Cat A, S$3,933
for Cat B and S$427 for Cat D. It beats the best naïve MAE by 5.45% for Cat A
and 1.22% for Cat B, but trails it by 4.84% for Cat D.

See [docs/METHODOLOGY.md](docs/METHODOLOGY.md) and
[docs/DEALER_SIGNALS.md](docs/DEALER_SIGNALS.md), plus
[docs/ECONOMIC_FEATURES.md](docs/ECONOMIC_FEATURES.md).

## Run locally

```bash
pip install -r requirements.txt
streamlit run coe_pressure_app.py
```

## Verify

```bash
pytest -q
python scripts/run_backtest.py
python scripts/build_tender_schedule.py
python scripts/run_dealer_experiment.py
python scripts/validate_sgcarmart_dataset.py
python scripts/build_economic_features.py
python scripts/run_economic_experiment.py
python scripts/validate_economic_dataset.py
```

## Deployment

The Streamlit entry point remains `coe_pressure_app.py`, preserving the existing
Community Cloud deployment configuration.

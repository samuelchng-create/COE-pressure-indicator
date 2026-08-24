# Singapore COE Pressure Indicator — v0.7 vehicle-financing experiment

An experimental Streamlit tracker for Singapore COE Categories A, B and D. It
loads official tender-level results, runs leakage-safe expanding-window
back-tests, compares the structural forecast with three naïve benchmarks, and
reports direction accuracy, MAE, RMSE and prequential interval coverage.

The app does **not** claim that a Dealer Pressure Index, model probability or
forecast edge is calibrated. Negative benchmark results remain visible.

Every chart, training window, tuning fold, uncertainty interval and benchmark
now uses a common October 2015 analysis start. Earlier tenders are excluded to
avoid mixing materially different policy regimes into the reported results.

## v0.7 SGCarMart dealer and advertised car-financing experiment

- Reconstructs dated 2024–2026 authorised-dealer price-list signals for BMW,
  BYD, GAC, Honda, Hyundai, Kia, Mazda, Mercedes-Benz, Nissan, Subaru, Tesla
  and Toyota from SGCarMart's public archive.
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

The archive contains 863 source PDFs, 2,629 auditable page rows and 997
model-eligible observations from nine brands. It contains 135 explicit
advertised car-finance rates, all from Honda documents and ranging from 2.58%
to 2.78%; this narrow coverage is disclosed. Over 51 paired forecasts per
category, the v0.7 dealer variant worsened Cat A MAE by 4.62% and Cat B MAE by
10.73%. The app publishes this negative result and does not claim a calibrated
dealer forecasting edge.

## v0.7 economy, markets and vehicle-financing experiment

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
- Runs a three-way paired expanding-window comparison at the same 193 forecast
  origins: structural, structural plus the 13-variable economy block, and that
  block plus financing. Relative to the economy block, financing worsened MAE
  by 0.20% for Cat A, 1.43% for Cat B and 1.01% for Cat D. Relative to the
  structural model, the 15-variable version worsened MAE by 0.12%, 1.07% and
  6.59%, respectively. It is not promoted over the structural model.
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

# Singapore COE Pressure Indicator — v0.2 structural + v0.3 dealer + v0.4 economy experiment

An experimental Streamlit tracker for Singapore COE Categories A, B and D. It
loads official tender-level results, runs leakage-safe expanding-window
back-tests, compares the structural forecast with three naïve benchmarks, and
reports direction accuracy, MAE, RMSE and prequential interval coverage.

The app does **not** claim that a Dealer Pressure Index, model probability or
forecast edge is calibrated. Negative benchmark results remain visible.

## v0.3 SGCarMart dealer archive

- Reconstructs dated 2024–2026 authorised-dealer price-list signals for BYD,
  Toyota, Mercedes-Benz, BMW, Honda and Tesla from SGCarMart's public archive.
- Stores each source URL, PDF date, later research retrieval timestamp and
  SHA-256 checksum. `available_at` is separate from `retrieved_at` so the
  retrospective as-of assumption is explicit and auditable.
- Produces model-eligible page summaries only when the PDF contains an explicit
  Category A or B heading and advertised prices. Unclassified pages remain in
  the research workbook for review.
- Uses the median advertised package price on each eligible category-labelled
  page, explicit COE package/rebate terms, bid guarantees, discounts,
  promotion deadlines and finance/trade-in text. It does not claim complete
  model/variant normalization.
- Weights brands using their LTA new registrations over the preceding 12
  complete months, divided by all makes. These are aggregation weights, not a
  hand-built Dealer Pressure Index.
- Tests a Ridge residual correction over exactly the structural model's
  out-of-sample predictions with expanding windows and reports whether dealer
  data actually improves MAE/RMSE/direction/interval coverage.
- Excludes Category D because SGCarMart's car price-list archive is not a
  motorcycle dealer archive.

The frozen v0.3 archive contains 441 source PDFs, 1,458 auditable page rows and
403 model-eligible observations. Over 51 paired forecasts per category, dealer
signals improved Cat A MAE by 5.45% but worsened Cat B MAE by 8.97%. The app
shows both results and does not treat the Cat A result as calibrated.

## v0.4 economy and financial-markets experiment

- Adds 13 tender-aligned variables: SGD/USD level and 21-day change, VIX level
  and change, US 10-year Treasury yield and change, Brent price and return,
  Nasdaq Composite level and return,
  Singapore real-GDP growth, CPI inflation and unemployment.
- Treats daily market observations as available in Singapore only on the next
  calendar day. Monthly CPI uses a 45-day publication buffer; quarterly GDP
  and unemployment use 75 days.
- Runs a paired expanding-window comparison at the same 331 forecast origins
  per category. The full block worsened MAE by 0.43% for Cat A, 0.30% for Cat B
  and 2.14% for Cat D, so it is visible in the app but is not promoted over the
  structural model.
- Uses current-vintage SingStat macro tables. The publication buffers prevent
  use of the current period too early, but historical revisions remain a known
  limitation until a real-time vintage archive is obtained.

## v0.2 structural method

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
python scripts/build_economic_features.py
python scripts/run_economic_experiment.py
python scripts/validate_economic_dataset.py
```

## Deployment

The Streamlit entry point remains `coe_pressure_app.py`, preserving the existing
Community Cloud deployment configuration.

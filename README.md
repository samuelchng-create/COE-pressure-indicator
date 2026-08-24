# Singapore COE Pressure Indicator — v0.2

An experimental Streamlit tracker for Singapore COE Categories A, B and D. It
loads official tender-level results, runs leakage-safe expanding-window
back-tests, compares the structural forecast with three naïve benchmarks, and
reports direction accuracy, MAE, RMSE and prequential interval coverage.

The app does **not** claim that a Dealer Pressure Index, model probability or
forecast edge is calibrated. Negative benchmark results remain visible.

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
[docs/DEALER_SIGNALS.md](docs/DEALER_SIGNALS.md).

## Run locally

```bash
pip install -r requirements.txt
streamlit run coe_pressure_app.py
```

## Verify

```bash
pytest -q
python scripts/run_backtest.py
```

## Deployment

The Streamlit entry point remains `coe_pressure_app.py`, preserving the existing
Community Cloud deployment configuration.

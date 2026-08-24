# Economy and financial-market feature dataset

## Variables

| Feature | Interpretation | Historical availability rule |
|---|---|---|
| `sgd_per_usd` | SGD required for one US dollar | Daily value, next Singapore calendar day |
| `sgd_per_usd_change_21d` | Approximate one-month FX change | Current as-of value versus value at least 30 calendar days earlier |
| `vix` / `vix_change_21d` | Global equity-risk level and change | Daily value, next Singapore calendar day |
| `us_10y_yield` / change | Global long-term financing conditions | Daily value, next Singapore calendar day |
| `brent_usd` / return | Oil-price and inflation pressure | Daily value, next Singapore calendar day |
| `nasdaq_composite` / return | Global equity-market level and approximate one-month performance | Daily value, next Singapore calendar day |
| `sg_real_gdp_yoy` | Singapore real economic growth | Quarter-end plus 75 days |
| `sg_cpi_yoy` | Singapore consumer-price inflation | Month-end plus 45 days |
| `sg_unemployment_rate` | Singapore total unemployment, seasonally adjusted | Quarter-end plus 75 days |

The downloadable tender-level file records the forecast cutoff and latest
availability timestamps. The source manifest records series identifiers,
providers, retrieval time, lags and revision risk.

## Sources

Singapore GDP and CPI are from the Singapore Department of Statistics via
SingStat Table Builder. Unemployment is from the Ministry of Manpower via
SingStat. Daily SGD/USD, Nasdaq Composite, VIX, US 10-year Treasury yields and Brent observations
are downloaded from FRED; the manifest retains the underlying series IDs.

## Limits

The SingStat API exposes the latest revised historical series, not the value as
first published at every historical tender. Fixed 45/75-day lags stop future
periods from entering early but cannot remove later revisions. The app labels
this limitation and does not claim a calibrated economy-driven forecasting
edge.

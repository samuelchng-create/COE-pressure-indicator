# Economy and financial-market feature dataset

The materialized dataset starts in October 2015 to match the common COE model
analysis boundary.

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
| `vehicle_hire_purchase_3y_rate` | Finance-company hire-purchase rate for new vehicles, three-year term | MAS month-end plus 45 days |
| `vehicle_hire_purchase_rate_staleness_days` | Age of the underlying MAS rate month at the tender cutoff | Derived from the latest historically available rate period |

The downloadable tender-level file records the forecast cutoff and latest
availability timestamps. The source manifest records series identifiers,
providers, retrieval time, lags and revision risk.

## Sources

Singapore GDP and CPI are from the Singapore Department of Statistics via
SingStat Table Builder. Unemployment is from the Ministry of Manpower via
SingStat. Daily SGD/USD, Nasdaq Composite, VIX, US 10-year Treasury yields and Brent observations
are downloaded from FRED; the manifest retains the underlying series IDs. The
vehicle rate comes from the Monetary Authority of Singapore's monthly
“Interest Rates of Banks and Finance Companies” table, specifically finance
companies' hire purchase of new vehicles for three years.

## Vehicle-financing interpretation and result

MAS publishes one new-vehicle series, not separate car and motorcycle series.
The model therefore treats it as a common financing-market proxy for Cat A, B
and D. The retrieved official history ends in April 2023; its value is carried
forward only together with an explicit age feature. No motorcycle-specific
historical rate is fabricated from current dealer quotations.

At the same 193 post-policy forecast origins per category, adding the two
financing features to the 13-variable economy block worsened MAE by 0.20% for
Cat A, 1.43% for Cat B and 1.01% for Cat D. Against structural-only, the full
15-variable model worsened MAE by 0.12%, 1.07% and 6.59%, respectively. This is
a negative experiment, not evidence of a financing-rate forecasting edge.

## Limits

The SingStat API exposes the latest revised historical series, not the value as
first published at every historical tender. Fixed 45/75-day lags stop future
periods from entering early but cannot remove later revisions. The app labels
this limitation and does not claim a calibrated economy-driven forecasting
edge.

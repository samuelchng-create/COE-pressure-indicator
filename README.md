# Singapore COE Pressure Indicator — v0.15 October Exercise 2 refresh

An experimental Streamlit tracker for Singapore COE Categories A, B and D. It
loads official tender-level results, runs leakage-safe expanding-window
back-tests, compares the structural forecast with three naïve benchmarks, and
reports direction accuracy, MAE, RMSE and prequential interval coverage.

The app does **not** claim that a Dealer Pressure Index, model probability or
forecast edge is prospectively calibrated. Negative benchmark results remain visible.

## v0.15 October 2026 Exercise 2 refresh

- Adds the confirmed 21 October 2026 results: Cat A S$132,004, Cat B
  S$131,901 and Cat D S$10,778. The data.gov.sg records were checked against
  the final OneMotoring table before rebuilding the outputs.
- Extends structural, economy and multi-horizon walk-forward comparisons to
  197 one-cycle forecasts per category, and the eligible dealer comparison to
  55 forecasts for Categories A and B.
- Rebuilds the 1/2/4/6-cycle outlook from the new endpoint. Until LTA identifies
  the November Exercise 1 quota on OneMotoring, the live forecast visibly uses
  the last completed quotas rather than assuming an unpublished supply value.
- Refreshes the consultation tab's completed pooled-price proxy and its
  next-exercise mechanical projection. The merged-auction limitation is unchanged.

## v0.14 October 2026 consultation counterfactual

- Adds LTA's indicative three-band and five-band OMV feebate structures in a
  dedicated public tab.
- Compares registration shares, weighted mean and mean absolute adjustment,
  dispersion, adjacent-band cliffs and the lowest-to-highest effective-cost
  spread.
- Builds a quota-weighted Cat A/B historical price proxy from October 2015 and
  applies both structures to a next-exercise planning proxy formed from the
  existing separate-category forecasts and announced quotas.
- Does not present the proxy as a merged-auction clearing price. Public tender
  results do not contain individual bid values, so demand switching and the
  counterfactual merged order book cannot be reconstructed.

## v0.13 prior data refresh

- Extends official completed outcomes through October 2026 Exercise 1: Cat A
  S$130,001, Cat B S$130,100 and Cat D S$11,012.
- Uses LTA's announced October Exercise 2 quotas in the live forecast instead
  of carrying the previous tender's supply forward. Live bid counts and
  provisional prices remain excluded.
- Refreshes the SGCarMart archive through 16 October 2026 and the economy,
  markets and vehicle-financing feature set through the current tender cutoff.
- Explicitly labels the one six-exercise calendar interval extending into 2027
  as projected because the bundled official schedule currently ends in 2026.

## v0.12 direct multi-cycle outlook

- Adds separately trained direct forecasts for 1, 2, 4 and 6 bidding exercises
  ahead; later forecasts are not recursively chained from earlier predictions.
- Embargoes every multi-horizon training label until its target exercise had
  actually completed at the historical forecast origin.
- Uses versioned official LTA opening and closing schedules from 2017 through
  2026. The 2017 calendar uses LTA's revised February–May schedule.
- Measures actual close-to-close demand exposure, flags intervals of at least
  19 days, and adds calendar span, next-gap length, quota per week, lagged bids
  per week and extended-gap counts to the experimental horizon model.
- Uses a dealer-oriented ±S$2,000 Stay band for Categories A and B while
  retaining ±S$1,000 for Category D. Exact dollar forecasts remain visible.
- Maps 578 dated guaranteed-COE package observations to both their stated bid
  count and the official calendar date of the last covered exercise.
- Re-runs paired dealer, economy/markets and vehicle-financing candidates at
  every horizon. Dealer residual labels receive the same terminal-target
  embargo as the structural labels.
- Reports horizon-matched persistence, historical-drift and horizon-momentum
  benchmarks plus MAE, RMSE, three-way accuracy, Brier score and interval
  coverage. Models that fail to beat the best naïve MAE remain labelled as
  research candidates.

The timing-aware model beats the best naïve MAE for Cat A at one exercise
(+7.5%), Cat B at one, two and four exercises (+5.4%, +3.2% and +1.3%), and
Cat D at one and two exercises by only +0.1% and +0.6%. It trails the benchmark
at the other horizons, so the existing one-cycle structural model remains the
primary published model.

The 13-variable economy/markets candidate improves structural MAE for Cat A at
all horizons (+0.1%, +1.0%, +4.4%, +4.8%) and Cat B at all horizons (+0.4%,
+1.1%, +0.3%, +1.7%), but remains worse for
Cat D throughout. Adding the vehicle-financing proxy worsens all 12 comparisons.
On the smaller reconstructed 2024–2026 sample, dealer signals improve only Cat
A at one exercise (+3.3%); the other seven
category/horizon tests worsen MAE. These retrospective candidates do not alter
the live structural forecast and are not presented as calibrated edges.

## v0.11 earlier refresh

- Extends official completed COE outcomes through September 2026 Exercise 2.
- Refreshes tender-aligned market and macroeconomic features through that
  tender using the same historical-availability rules.
- Extends structural and economy comparisons to 195 forecasts per category,
  and the eligible dealer comparison to 53 forecasts for Categories A and B.
- Keeps the audited SGCarMart source corpus through 1 September 2026; no later
  dealer observations are imputed when a dated source document is unavailable.
- Targets October 2026 Exercise 1 in the live next-exercise outlook.

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
- Uses official announced category and Cat E quotas when OneMotoring identifies
  the exact expected tender, otherwise visibly falls back to the last completed
  quotas. The structural point forecast and the most probable outcome can
  differ when the historical residual distribution is asymmetric.
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

The refreshed archive contains 1,562 source PDFs, 4,012 auditable page rows and
1,182 model-eligible observations from 11 grouped brands. It contains 138 explicit
advertised car-finance rates, all from Honda documents and ranging from 2.58%
to 2.78%; this narrow coverage is disclosed. The latest SGCarMart document is
dated 16 October 2026. Over 55 paired forecasts per category, the v0.8 dealer
variant improved Cat A MAE by 1.50% but worsened Cat B MAE by 11.47%. The small
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
- Runs a three-way paired expanding-window comparison at the same 197 forecast
  origins: structural, structural plus the 13-variable economy block, and that
  block plus financing. Relative to the economy block, financing worsened MAE
  by 0.32% for Cat A, 1.22% for Cat B and 1.10% for Cat D. Relative to the
  structural model, the 15-variable version worsened MAE by 0.93%, 1.36% and
  5.44%, respectively. It is not promoted over the structural model.
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

Across 197 post-policy forecasts, structural MAE is S$2,821 for Cat A, S$3,889
for Cat B and S$434 for Cat D. It beats the best naïve MAE by about 5.8% for Cat A
and 1.7% for Cat B, but trails it by about 4.5% for Cat D.

See [docs/METHODOLOGY.md](docs/METHODOLOGY.md) and
[docs/DEALER_SIGNALS.md](docs/DEALER_SIGNALS.md), plus
[docs/ECONOMIC_FEATURES.md](docs/ECONOMIC_FEATURES.md) and
[docs/COE_CONSULTATION_SCENARIOS.md](docs/COE_CONSULTATION_SCENARIOS.md).

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
python scripts/run_horizon_experiment.py
python scripts/run_horizon_signal_experiments.py
python scripts/build_dealer_horizon_alignment.py
python scripts/validate_horizon_dataset.py
python scripts/run_dealer_experiment.py
python scripts/validate_sgcarmart_dataset.py
python scripts/build_economic_features.py
python scripts/run_economic_experiment.py
python scripts/validate_economic_dataset.py
```

## Deployment

The Streamlit entry point remains `coe_pressure_app.py`, preserving the existing
Community Cloud deployment configuration.

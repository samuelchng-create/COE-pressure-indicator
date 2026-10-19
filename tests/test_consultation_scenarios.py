import pandas as pd
import pytest

from consultation_scenarios import (
    apply_feebates,
    build_merged_proxy_history,
    summarize_options,
    weighted_premium,
)


def test_published_options_have_expected_distributional_mechanics():
    summary = summarize_options().set_index("option")
    three = summary.loc["Option A — 3 bands"]
    five = summary.loc["Option B — 5 bands"]
    assert three.mean_adjustment == pytest.approx(2_250)
    assert five.mean_adjustment == pytest.approx(2_250)
    assert three.mean_absolute_adjustment == pytest.approx(12_750)
    assert five.mean_absolute_adjustment == pytest.approx(9_000)
    assert three.largest_adjacent_step == 15_000
    assert five.largest_adjacent_step == 7_500
    assert three.lowest_to_highest_spread == five.lowest_to_highest_spread == 30_000


def test_merged_history_uses_quota_weighted_a_b_premiums():
    rows = []
    for tender, date, a_price, b_price in (
        ("2026-01-1", "2026-01-07", 100_000, 120_000),
        ("2026-01-2", "2026-01-21", 110_000, 130_000),
    ):
        rows.extend(
            [
                {"tender_id": tender, "display_date": date, "vehicle_class": "Category A", "premium": a_price, "quota": 3, "bids_received": 4},
                {"tender_id": tender, "display_date": date, "vehicle_class": "Category B", "premium": b_price, "quota": 1, "bids_received": 2},
            ]
        )
    history = build_merged_proxy_history(pd.DataFrame(rows))
    assert history.iloc[0].pooled_price_proxy == pytest.approx(105_000)
    assert history.iloc[1].pooled_proxy_change == pytest.approx(10_000)
    assert history.iloc[0].combined_quota == 4


def test_projection_applies_adjustments_without_changing_the_base():
    projection = apply_feebates(130_000)
    assert projection.effective_coe_cost.min() == 115_000
    assert projection.effective_coe_cost.max() == 145_000
    assert weighted_premium(
        {"Category A": 100_000, "Category B": 120_000},
        {"Category A": 3, "Category B": 1},
    ) == pytest.approx(105_000)

import pandas as pd

from dealer_experiment import walk_forward_dealer_uplift
from horizon_model import add_horizon_probabilities, prepare_tender_calendar, stay_band_for


def test_calendar_computes_close_to_close_gap_and_extended_flag():
    schedule = pd.DataFrame(
        [
            {"tender_id": "2026-01-1", "exercise_end_at": "2026-01-07T16:00:00+08:00", "source_url": "official"},
            {"tender_id": "2026-01-2", "exercise_end_at": "2026-01-21T16:00:00+08:00", "source_url": "official"},
            {"tender_id": "2026-02-1", "exercise_end_at": "2026-02-11T16:00:00+08:00", "source_url": "official"},
        ]
    )
    result = prepare_tender_calendar(schedule)
    assert result.iloc[1]["gap_days"] == 14
    assert result.iloc[1]["extended_gap"] == 0
    assert result.iloc[2]["gap_days"] == 21
    assert result.iloc[2]["extended_gap"] == 1


def test_category_specific_commercial_stay_bands():
    assert stay_band_for("Category A") == 2_000
    assert stay_band_for("Category B") == 2_000
    assert stay_band_for("Category D") == 1_000


def test_dealer_uplift_embargoes_unfinished_multi_horizon_targets():
    rows = []
    features = []
    for position in range(20):
        tender_id = f"2026-{position + 1:02d}-1"
        rows.append(
            {
                "category": "Category A",
                "horizon": 6,
                "tender_id": tender_id,
                "actual": 100_000 + position,
                "previous_premium": 100_000,
                "structural": 100_000,
                "persistence": 100_000,
                "lower": 99_000,
                "upper": 101_000,
                "origin_position": position,
                "target_position": position + 6,
            }
        )
        features.append(
            {
                "tender_id": tender_id,
                "category": "Category A",
                "forecast_cutoff_at": "2026-01-01T00:00:00Z",
                "dealer_observation_count": 1,
                "dealer_brand_count": 1,
                "weighted_advertised_price": 150_000 + position,
                "weighted_price_change": 0,
                "weighted_coe_rebate": 90_000,
                "weighted_total_incentive": 1_000,
                "weighted_finance_rate_pct": 2.5,
                "weighted_guaranteed_coe_share": 1,
                "weighted_promotion_deadline_days": 7,
                "weighted_active_roadshow_share": 0,
            }
        )

    result = walk_forward_dealer_uplift(
        pd.DataFrame(rows), pd.DataFrame(features), min_train=4, alphas=(1.0,)
    )

    assert int(result.iloc[0]["origin_position"]) == 9
    assert int(result.iloc[0]["dealer_n_train"]) == 4


def test_probability_calibration_embargoes_unfinished_horizon_errors():
    backtest = pd.DataFrame(
        [
            {
                "category": "Category A",
                "horizon": 6,
                "origin_position": position,
                "target_position": position + 6,
                "actual": 101_000 + position,
                "previous_premium": 100_000,
                "structural": 100_500,
            }
            for position in range(15)
        ]
    )

    result = add_horizon_probabilities(backtest, min_calibration=3)
    first_probability = result["probability_stay"].first_valid_index()

    assert first_probability == 8

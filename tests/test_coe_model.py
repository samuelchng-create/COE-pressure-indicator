import numpy as np
import pandas as pd

from coe_model import build_feature_frame, prepare_coe_data, walk_forward_backtest


def synthetic_records(tenders: int = 90) -> list[dict]:
    records = []
    categories = ["Category A", "Category B", "Category C", "Category D", "Category E"]
    for tender in range(tenders):
        month = pd.Timestamp("2020-01-01") + pd.DateOffset(months=tender // 2)
        bidding_no = tender % 2 + 1
        for category_number, category in enumerate(categories):
            premium = 20_000 + category_number * 2_000 + tender * 110 + (tender % 5) * 30
            quota = 800 + category_number * 10 + tender % 7
            records.append(
                {
                    "month": month.strftime("%Y-%m"),
                    "bidding_no": str(bidding_no),
                    "vehicle_class": category,
                    "quota": f"{quota:,}",
                    "bids_success": str(quota - 2),
                    "bids_received": f"{quota + 150:,}",
                    "premium": f"{premium:,}",
                }
            )
    return records


def test_prepare_parses_thousands_separators():
    data = prepare_coe_data(synthetic_records(4))
    assert data["premium"].notna().all()
    assert data["quota"].notna().all()
    assert data["bids_received"].notna().all()


def test_prepare_enforces_october_2015_analysis_start():
    records = synthetic_records(4)
    for row in records[:10]:
        row["month"] = "2015-09"
    for row in records[10:]:
        row["month"] = "2015-10"
    data = prepare_coe_data(records)
    assert not data.empty
    assert data["month"].min() == pd.Timestamp("2015-10-01")


def test_outcome_features_do_not_use_current_tender_results():
    data = prepare_coe_data(synthetic_records(10))
    before = build_feature_frame(data, "Category A")
    target_id = before.iloc[-1]["tender_id"]
    changed = data.copy()
    mask = (changed["tender_id"] == target_id) & (changed["vehicle_class"] == "Category A")
    changed.loc[mask, ["premium", "bids_received"]] *= 10
    cat_e_mask = (changed["tender_id"] == target_id) & (changed["vehicle_class"] == "Category E")
    changed.loc[cat_e_mask, ["premium", "bids_received"]] *= 10
    after = build_feature_frame(changed, "Category A")
    feature_columns = [
        "premium_lag1",
        "momentum_lag1",
        "bid_pressure_lag1",
        "excess_demand_lag1",
        "announced_quota",
        "cat_e_premium_lag1",
        "cat_e_bid_pressure_lag1",
    ]
    pd.testing.assert_series_equal(
        before.loc[before["tender_id"] == target_id, feature_columns].iloc[0],
        after.loc[after["tender_id"] == target_id, feature_columns].iloc[0],
    )


def test_future_mutation_cannot_change_earlier_predictions():
    data = prepare_coe_data(synthetic_records())
    original = walk_forward_backtest(data, "Category A", min_train=30, min_calibration=5)
    changed = data.copy()
    final_tenders = set(changed["tender_id"].drop_duplicates().tail(3))
    changed.loc[changed["tender_id"].isin(final_tenders), "premium"] *= 3
    revised = walk_forward_backtest(changed, "Category A", min_train=30, min_calibration=5)
    cutoff = original.iloc[-4]["tender_id"]
    left = original[original["tender_id"] <= cutoff].reset_index(drop=True)
    right = revised[revised["tender_id"] <= cutoff].reset_index(drop=True)
    np.testing.assert_allclose(left["structural"], right["structural"])
    assert (left["train_end_tender"] < left["tender_id"]).all()

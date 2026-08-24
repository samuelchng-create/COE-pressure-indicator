import pandas as pd

from coe_model import build_feature_frame, prepare_coe_data, walk_forward_backtest
from economic_features import ECONOMIC_FEATURE_COLUMNS, validate_economic_features
from test_coe_model import synthetic_records


def economic_rows(tenders: int = 10) -> pd.DataFrame:
    rows = []
    for tender in range(tenders):
        month = pd.Timestamp("2020-01-01") + pd.DateOffset(months=tender // 2)
        bidding_no = tender % 2 + 1
        row = {
            "tender_id": f"{month:%Y-%m}-{bidding_no}",
            "forecast_cutoff_at": (month + pd.Timedelta(days=(bidding_no - 1) * 14)).isoformat(),
        }
        row.update({column: float(tender + offset) for offset, column in enumerate(ECONOMIC_FEATURE_COLUMNS)})
        rows.append(row)
    return pd.DataFrame(rows)


def test_economic_dataset_requires_unique_complete_rows():
    data, errors = validate_economic_features(economic_rows())
    assert not errors
    assert len(data) == 10
    duplicated = pd.concat([data, data.iloc[[0]]], ignore_index=True)
    _, errors = validate_economic_features(duplicated)
    assert any("duplicate" in error for error in errors)


def test_economic_features_merge_by_target_tender():
    coe = prepare_coe_data(synthetic_records(10))
    frame = build_feature_frame(coe, "Category A", economic_features=economic_rows())
    target = frame.iloc[-1]
    source = economic_rows().set_index("tender_id").loc[target["tender_id"]]
    for column in ECONOMIC_FEATURE_COLUMNS:
        assert target[column] == source[column]


def test_future_economic_mutation_cannot_change_earlier_forecasts():
    coe = prepare_coe_data(synthetic_records(90))
    economic = economic_rows(90)
    original = walk_forward_backtest(
        coe, "Category A", economic_features=economic, min_train=30, min_calibration=5
    )
    changed = economic.copy()
    changed.loc[changed.index[-3:], list(ECONOMIC_FEATURE_COLUMNS)] *= 100
    revised = walk_forward_backtest(
        coe, "Category A", economic_features=changed, min_train=30, min_calibration=5
    )
    cutoff = original.iloc[-4]["tender_id"]
    left = original[original["tender_id"] <= cutoff].reset_index(drop=True)
    right = revised[revised["tender_id"] <= cutoff].reset_index(drop=True)
    pd.testing.assert_series_equal(left["structural"], right["structural"])

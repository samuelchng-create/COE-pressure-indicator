import numpy as np
import pandas as pd

from dealer_experiment import DEALER_FEATURE_COLUMNS, walk_forward_dealer_uplift


def experiment_frames(n=24):
    tender_ids = [f"2025-{1 + i // 2:02d}-{1 + i % 2}" for i in range(n)]
    signal = np.linspace(-2, 2, n)
    structural = pd.DataFrame(
        {
            "tender_id": tender_ids,
            "actual": 100_000 + 500 * signal,
            "previous_premium": 100_000,
            "structural": 100_000,
            "persistence": 100_000,
            "lower": 98_000,
            "upper": 102_000,
        }
    )
    features = pd.DataFrame({"tender_id": tender_ids})
    for column in DEALER_FEATURE_COLUMNS:
        features[column] = 1.0
    features["weighted_price_change"] = signal
    return structural, features


def test_dealer_uplift_is_expanding_and_future_safe():
    structural, features = experiment_frames()
    original = walk_forward_dealer_uplift(structural, features, min_train=12)
    revised = structural.copy()
    revised.loc[revised.index[-1], "actual"] += 50_000
    changed = walk_forward_dealer_uplift(revised, features, min_train=12)
    assert len(original) == 12
    pd.testing.assert_series_equal(
        original.iloc[:-1]["structural_plus_dealer"].reset_index(drop=True),
        changed.iloc[:-1]["structural_plus_dealer"].reset_index(drop=True),
    )
    assert original.iloc[-1]["dealer_n_train"] == 23

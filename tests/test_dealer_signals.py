import pandas as pd

from dealer_signals import aggregate_before_cutoff, validate_dealer_observations


def observations() -> pd.DataFrame:
    return pd.DataFrame(
        [
            {
                "observation_id": "one",
                "observed_at": "2026-08-01T00:00:00Z",
                "retrieved_at": "2026-08-01T01:00:00Z",
                "source_url": "https://example.test/one",
                "category": "Category A",
                "brand": "Example",
                "model": "One",
                "advertised_price": 150000,
                "previous_advertised_price": 152000,
                "guaranteed_coe": True,
                "market_share_weight": 2,
            },
            {
                "observation_id": "future",
                "observed_at": "2026-08-20T00:00:00Z",
                "retrieved_at": "2026-08-20T01:00:00Z",
                "source_url": "https://example.test/future",
                "category": "Category A",
                "brand": "Example",
                "model": "Two",
                "advertised_price": 999999,
                "previous_advertised_price": 999999,
                "guaranteed_coe": False,
                "market_share_weight": 1,
            },
        ]
    )


def test_validator_and_cutoff_exclude_future_observations():
    validated, errors = validate_dealer_observations(observations())
    assert errors == []
    features = aggregate_before_cutoff(validated, "Category A", pd.Timestamp("2026-08-10T00:00:00Z"))
    assert features["dealer_observation_count"] == 1
    assert features["weighted_advertised_price"] == 150000
    assert features["weighted_price_change"] == -2000


def test_retrieval_before_observation_is_rejected():
    frame = observations().iloc[[0]].copy()
    frame.loc[:, "retrieved_at"] = "2026-07-31T00:00:00Z"
    _, errors = validate_dealer_observations(frame)
    assert any("cannot precede" in error for error in errors)

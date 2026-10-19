"""Transparent counterfactuals for LTA's October 2026 COE consultation.

The public tender dataset contains only category-level clearing prices and bid
counts, not individual bids.  A merged auction therefore cannot be replayed.
This module deliberately uses a quota-weighted Category A/B premium as an
accounting proxy and keeps the mechanical feebate calculation separate from
any claim about a future merged-market equilibrium.
"""

from __future__ import annotations

import numpy as np
import pandas as pd


CONSULTATION_VERSION = "v0.1-lta-october-2026-feebate-counterfactual"
CONSULTATION_PAPER_URL = "https://go.gov.sg/coe-public-consult"


def feebate_bands() -> pd.DataFrame:
    """Return LTA's two indicative structures and registration-percentile shares."""
    rows = [
        ("Option A — 3 bands", 1, "0th–35th", 0.35, -15_000),
        ("Option A — 3 bands", 2, "35th–50th", 0.15, 0),
        ("Option A — 3 bands", 3, "Above 50th", 0.50, 15_000),
        ("Option B — 5 bands", 1, "0th–10th", 0.10, -15_000),
        ("Option B — 5 bands", 2, "10th–35th", 0.25, -7_500),
        ("Option B — 5 bands", 3, "35th–50th", 0.15, 0),
        ("Option B — 5 bands", 4, "50th–75th", 0.25, 7_500),
        ("Option B — 5 bands", 5, "Above 75th", 0.25, 15_000),
    ]
    result = pd.DataFrame(
        rows,
        columns=["option", "band", "omv_percentile", "registration_share", "adjustment"],
    )
    shares = result.groupby("option")["registration_share"].sum()
    if not np.allclose(shares.to_numpy(dtype=float), 1.0):
        raise ValueError("Feebate registration shares must sum to one for each option")
    return result


def summarize_options() -> pd.DataFrame:
    """Summarise distributional mechanics implied by the published percentiles."""
    rows = []
    for option, group in feebate_bands().groupby("option", sort=False):
        weights = group["registration_share"].to_numpy(dtype=float)
        adjustments = group["adjustment"].to_numpy(dtype=float)
        mean_adjustment = float(np.average(adjustments, weights=weights))
        rows.append(
            {
                "option": option,
                "bands": len(group),
                "rebate_share": float(group.loc[group.adjustment.lt(0), "registration_share"].sum()),
                "no_adjustment_share": float(group.loc[group.adjustment.eq(0), "registration_share"].sum()),
                "surcharge_share": float(group.loc[group.adjustment.gt(0), "registration_share"].sum()),
                "mean_adjustment": mean_adjustment,
                "mean_absolute_adjustment": float(np.average(np.abs(adjustments), weights=weights)),
                "adjustment_standard_deviation": float(
                    np.sqrt(np.average((adjustments - mean_adjustment) ** 2, weights=weights))
                ),
                "largest_adjacent_step": float(np.abs(np.diff(adjustments)).max()),
                "lowest_to_highest_spread": float(adjustments.max() - adjustments.min()),
            }
        )
    return pd.DataFrame(rows)


def build_merged_proxy_history(data: pd.DataFrame) -> pd.DataFrame:
    """Build a quota-weighted A/B price proxy from completed tender results."""
    required = {"tender_id", "display_date", "vehicle_class", "premium", "quota", "bids_received"}
    missing = required - set(data.columns)
    if missing:
        raise ValueError(f"COE data is missing: {', '.join(sorted(missing))}")
    cars = data[data["vehicle_class"].isin(["Category A", "Category B"])].copy()
    index = ["tender_id", "display_date"]
    premiums = cars.pivot(index=index, columns="vehicle_class", values="premium")
    quotas = cars.pivot(index=index, columns="vehicle_class", values="quota")
    bids = cars.pivot(index=index, columns="vehicle_class", values="bids_received")
    required_categories = {"Category A", "Category B"}
    if not required_categories.issubset(premiums.columns):
        raise ValueError("Both Category A and Category B are required")
    complete = premiums.notna().all(axis=1) & quotas.notna().all(axis=1) & bids.notna().all(axis=1)
    premiums = premiums.loc[complete]
    quotas = quotas.loc[complete]
    bids = bids.loc[complete]
    combined_quota = quotas.sum(axis=1)
    result = pd.DataFrame(index=premiums.index)
    result["cat_a_premium"] = premiums["Category A"]
    result["cat_b_premium"] = premiums["Category B"]
    result["cat_a_quota"] = quotas["Category A"]
    result["cat_b_quota"] = quotas["Category B"]
    result["combined_quota"] = combined_quota
    result["combined_bids_received"] = bids.sum(axis=1)
    result["pooled_price_proxy"] = (
        premiums["Category A"] * quotas["Category A"]
        + premiums["Category B"] * quotas["Category B"]
    ) / combined_quota
    result["absolute_a_b_gap"] = (result["cat_a_premium"] - result["cat_b_premium"]).abs()
    result["cat_a_change"] = result["cat_a_premium"].diff()
    result["cat_b_change"] = result["cat_b_premium"].diff()
    result["pooled_proxy_change"] = result["pooled_price_proxy"].diff()
    return result.reset_index().sort_values("display_date").reset_index(drop=True)


def apply_feebates(base_premium: float) -> pd.DataFrame:
    """Apply both official indicative feebate schedules to a disclosed base proxy."""
    if not np.isfinite(base_premium) or base_premium < 0:
        raise ValueError("Base premium must be a finite non-negative value")
    result = feebate_bands()
    result["base_premium"] = float(base_premium)
    result["effective_coe_cost"] = result["base_premium"] + result["adjustment"]
    return result


def weighted_premium(premiums: dict[str, float], quotas: dict[str, float]) -> float:
    """Return the quota-weighted A/B premium used for the planning proxy."""
    categories = ("Category A", "Category B")
    if not all(category in premiums and category in quotas for category in categories):
        raise ValueError("Category A and B premiums and quotas are required")
    weights = np.array([float(quotas[category]) for category in categories])
    values = np.array([float(premiums[category]) for category in categories])
    if not np.isfinite(weights).all() or not np.isfinite(values).all() or (weights <= 0).any():
        raise ValueError("Premiums and quotas must be finite, with positive quotas")
    return float(np.average(values, weights=weights))

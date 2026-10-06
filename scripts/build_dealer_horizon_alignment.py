"""Map dated guaranteed-COE packages to official exercise and calendar horizons."""

from pathlib import Path
import sys

import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from dealer_signals import validate_dealer_observations
from horizon_model import prepare_tender_calendar
from tender_timing import load_tender_schedule


ROOT = Path(__file__).resolve().parents[1]


def main() -> None:
    raw = pd.read_csv(ROOT / "data" / "dealer_observations_sgcarmart_2024_2026.csv")
    observations, errors = validate_dealer_observations(raw)
    if errors:
        raise ValueError("; ".join(errors))
    schedule = load_tender_schedule(ROOT / "data" / "tender_schedule_2017_2026.csv")
    calendar = prepare_tender_calendar(schedule)
    rows = []
    eligible = observations[
        observations["guaranteed_coe_bid_count"].notna()
        & observations["guaranteed_coe_bid_count"].gt(0)
    ]
    for observation in eligible.itertuples(index=False):
        available = pd.Timestamp(observation.available_at).tz_convert("UTC")
        future = calendar[calendar["forecast_cutoff_at"].gt(available)].sort_values("forecast_cutoff_at")
        count = int(observation.guaranteed_coe_bid_count)
        if len(future) < count:
            continue
        covered = future.iloc[:count]
        first = covered.iloc[0]
        last = covered.iloc[-1]
        closes = covered["exercise_end_at"].tolist()
        extended = sum((later - earlier).total_seconds() / 86_400 >= 19 for earlier, later in zip(closes, closes[1:]))
        promotion_deadline = pd.Timestamp(observation.promotion_deadline) if pd.notna(observation.promotion_deadline) else pd.NaT
        roadshow_start = pd.Timestamp(observation.roadshow_start) if pd.notna(observation.roadshow_start) else pd.NaT
        roadshow_end = pd.Timestamp(observation.roadshow_end) if pd.notna(observation.roadshow_end) else pd.NaT
        roadshow_close_overlap = (
            sum(roadshow_start <= close <= roadshow_end for close in closes)
            if pd.notna(roadshow_start) and pd.notna(roadshow_end)
            else 0
        )
        rows.append(
            {
                "observation_id": observation.observation_id,
                "category": observation.category,
                "brand": observation.brand,
                "available_at": observation.available_at,
                "guaranteed_bid_count": count,
                "first_covered_tender": first.tender_id,
                "last_covered_tender": last.tender_id,
                "calendar_days_to_last_close": (last.exercise_end_at - available).total_seconds() / 86_400,
                "extended_gap_count": extended,
                "promotion_deadline": promotion_deadline,
                "promotion_deadline_days_from_first_close": (promotion_deadline - first.exercise_end_at).total_seconds() / 86_400 if pd.notna(promotion_deadline) else pd.NA,
                "promotion_deadline_days_from_last_close": (promotion_deadline - last.exercise_end_at).total_seconds() / 86_400 if pd.notna(promotion_deadline) else pd.NA,
                "roadshow_start": roadshow_start,
                "roadshow_end": roadshow_end,
                "covered_closes_during_roadshow": roadshow_close_overlap,
                "alignment_assumption": "coverage begins at first exercise opening strictly after evidenced availability",
                "source_url": observation.source_url,
            }
        )
    target = ROOT / "data" / "dealer_package_horizon_alignment.csv"
    pd.DataFrame(rows).to_csv(target, index=False)
    print(f"wrote {len(rows)} dealer-package horizon mappings to {target}")


if __name__ == "__main__":
    main()

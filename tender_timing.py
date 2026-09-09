from pathlib import Path

import pandas as pd


def load_tender_schedule(path: str | Path) -> pd.DataFrame:
    schedule = pd.read_csv(path)
    schedule["forecast_cutoff_at"] = pd.to_datetime(
        schedule["forecast_cutoff_at"], utc=True
    ).dt.tz_convert("Asia/Singapore")
    schedule["exercise_end_at"] = pd.to_datetime(
        schedule["exercise_end_at"], utc=True
    ).dt.tz_convert("Asia/Singapore")
    return schedule


def _time_text(timestamp: pd.Timestamp) -> str:
    hour = timestamp.hour % 12 or 12
    return f"{hour}:{timestamp.minute:02d} {timestamp.strftime('%p')}"


def _date_time_text(timestamp: pd.Timestamp) -> str:
    return (
        f"{timestamp.strftime('%A')}, {timestamp.day} {timestamp.strftime('%B %Y')} "
        f"at {_time_text(timestamp)}"
    )


def exercise_status(
    schedule: pd.DataFrame,
    tender_id: str,
    now: pd.Timestamp | None = None,
) -> tuple[str, str, str] | None:
    """Describe the official exercise timing without implying live bid data."""
    matches = schedule[schedule["tender_id"].eq(tender_id)]
    if matches.empty:
        return None
    row = matches.iloc[0]
    opens = pd.Timestamp(row["forecast_cutoff_at"])
    closes = pd.Timestamp(row["exercise_end_at"])
    if now is None:
        now = pd.Timestamp.now(tz="Asia/Singapore")
    elif now.tzinfo is None:
        now = now.tz_localize("Asia/Singapore")
    else:
        now = now.tz_convert("Asia/Singapore")

    if now < opens:
        message = (
            f"Bidding opens {_date_time_text(opens)} and closes "
            f"{_date_time_text(closes)} (Singapore time)."
        )
        level = "info"
    elif now <= closes:
        day_word = "today" if now.date() == closes.date() else closes.strftime("%A")
        message = (
            f"Bidding is open and closes {day_word} at {_time_text(closes)} "
            "Singapore time."
        )
        level = "warning"
    else:
        day_word = "today" if now.date() == closes.date() else f"{closes.day} {closes.strftime('%B')}"
        message = (
            f"Bidding closed {day_word} at {_time_text(closes)} Singapore time; "
            "awaiting the official result."
        )
        level = "info"
    return level, message, str(row["source_url"])

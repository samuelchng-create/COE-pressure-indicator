import pandas as pd

from tender_timing import exercise_status


def schedule() -> pd.DataFrame:
    return pd.DataFrame(
        [
            {
                "tender_id": "2026-09-1",
                "category": "Category A",
                "forecast_cutoff_at": pd.Timestamp("2026-09-07T12:00:00+08:00"),
                "exercise_end_at": pd.Timestamp("2026-09-09T16:00:00+08:00"),
                "source_url": "https://example.test/lta-schedule.pdf",
            }
        ]
    )


def test_open_exercise_reports_same_day_deadline():
    level, message, source = exercise_status(
        schedule(), "2026-09-1", pd.Timestamp("2026-09-09T10:00:00+08:00")
    )
    assert level == "warning"
    assert message == "Bidding is open and closes today at 4:00 PM Singapore time."
    assert source.endswith("lta-schedule.pdf")


def test_closed_exercise_reports_pending_result():
    level, message, _ = exercise_status(
        schedule(), "2026-09-1", pd.Timestamp("2026-09-09T16:00:01+08:00")
    )
    assert level == "info"
    assert message == (
        "Bidding closed today at 4:00 PM Singapore time; awaiting the official result."
    )


def test_future_exercise_reports_full_open_and_close_times():
    level, message, _ = exercise_status(
        schedule(), "2026-09-1", pd.Timestamp("2026-09-06T10:00:00+08:00")
    )
    assert level == "info"
    assert "Monday, 7 September 2026 at 12:00 PM" in message
    assert "Wednesday, 9 September 2026 at 4:00 PM" in message


def test_unknown_exercise_has_no_schedule_message():
    assert exercise_status(schedule(), "2026-09-2") is None

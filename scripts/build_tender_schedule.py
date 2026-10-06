"""Build the official 2024–2026 Cat A/B tender schedule used for cutoffs."""

from __future__ import annotations

import calendar
from pathlib import Path

import pandas as pd


SCHEDULES = {
    2024: [
        ("01-1", "01-02", "01-04"), ("01-2", "01-15", "01-17"),
        ("02-1", "02-05", "02-07"), ("02-2", "02-19", "02-21"),
        ("03-1", "03-04", "03-06"), ("03-2", "03-18", "03-20"),
        ("04-1", "04-01", "04-03"), ("04-2", "04-15", "04-17"),
        ("05-1", "05-06", "05-08"), ("05-2", "05-20", "05-23"),
        ("06-1", "06-03", "06-05"), ("06-2", "06-18", "06-20"),
        ("07-1", "07-01", "07-03"), ("07-2", "07-15", "07-17"),
        ("08-1", "08-05", "08-07"), ("08-2", "08-19", "08-21"),
        ("09-1", "09-02", "09-04"), ("09-2", "09-16", "09-18"),
        ("10-1", "10-07", "10-09"), ("10-2", "10-21", "10-23"),
        ("11-1", "11-04", "11-06"), ("11-2", "11-18", "11-20"),
        ("12-1", "12-02", "12-04"), ("12-2", "12-16", "12-18"),
    ],
    2025: [
        ("01-1", "01-06", "01-08"), ("01-2", "01-20", "01-22"),
        ("02-1", "02-03", "02-05"), ("02-2", "02-17", "02-19"),
        ("03-1", "03-03", "03-05"), ("03-2", "03-17", "03-19"),
        ("04-1", "04-07", "04-09"), ("04-2", "04-21", "04-23"),
        ("05-1", "05-05", "05-07"), ("05-2", "05-19", "05-21"),
        ("06-1", "06-02", "06-04"), ("06-2", "06-16", "06-18"),
        ("07-1", "07-07", "07-09"), ("07-2", "07-21", "07-23"),
        ("08-1", "08-04", "08-06"), ("08-2", "08-18", "08-20"),
        ("09-1", "09-01", "09-03"), ("09-2", "09-15", "09-17"),
        ("10-1", "10-06", "10-08"), ("10-2", "10-21", "10-23"),
        ("11-1", "11-03", "11-05"), ("11-2", "11-17", "11-19"),
        ("12-1", "12-01", "12-03"), ("12-2", "12-15", "12-17"),
    ],
    2026: [
        ("01-1", "01-05", "01-07"), ("01-2", "01-19", "01-21"),
        ("02-1", "02-02", "02-04"), ("02-2", "02-16", "02-20"),
        ("03-1", "03-02", "03-04"), ("03-2", "03-16", "03-18"),
        ("04-1", "04-06", "04-08"), ("04-2", "04-20", "04-22"),
        ("05-1", "05-04", "05-06"), ("05-2", "05-18", "05-20"),
        ("06-1", "06-02", "06-04"), ("06-2", "06-15", "06-17"),
        ("07-1", "07-06", "07-08"), ("07-2", "07-20", "07-22"),
        ("08-1", "08-03", "08-05"), ("08-2", "08-17", "08-19"),
        ("09-1", "09-07", "09-09"), ("09-2", "09-21", "09-23"),
        ("10-1", "10-05", "10-07"), ("10-2", "10-19", "10-21"),
        ("11-1", "11-02", "11-04"), ("11-2", "11-16", "11-18"),
        ("12-1", "12-07", "12-09"), ("12-2", "12-21", "12-23"),
    ],
}


HISTORICAL_SOURCES = {
    2017: "https://onemotoring.lta.gov.sg/content/dam/onemotoring/pdf/Circulars%20to%20ESAs/2017/VRL_06_2017.pdf",
    2018: "https://onemotoring.lta.gov.sg/content/dam/onemotoring/pdf/Circulars%20to%20ESAs/2017/VRL_13_2017.pdf",
    2019: "https://onemotoring.lta.gov.sg/content/dam/onemotoring/pdf/Circulars%20to%20ESAs/2018/Circular_06-2018_COE_Bidding_Schedule_for_Year_2019.pdf",
    2020: "https://onemotoring.lta.gov.sg/content/dam/onemotoring/pdf/Circulars%20to%20ESAs/2019/VRL_18_2019.pdf",
    2021: "https://onemotoring.lta.gov.sg/content/dam/onemotoring/pdf/Circulars%20to%20ESAs/2020/VRL_41_2020.pdf",
    2022: "https://onemotoring.lta.gov.sg/content/dam/onemotoring/Buying/PDF/COE/COE_Bidding_Schedule_for_Year_2022.pdf",
    2023: "https://onemotoring.lta.gov.sg/content/dam/onemotoring/pdf/Circulars%20to%20ESAs/2022/VRL_17_2022.pdf",
}

# Official annual schedules follow the first/third Monday rule except for the
# explicitly published holiday and policy adjustments below. These overrides
# are transcribed from the source PDFs above. The 2017 entries use LTA's revised
# schedule issued on 20 February 2017, not the superseded annual calendar.
HISTORICAL_OVERRIDES = {
    "2017-01-1": ("2017-01-03", "2017-01-05"),
    "2017-02-2": ("2017-02-22", "2017-02-24"),
    "2017-03-1": ("2017-03-13", "2017-03-15"),
    "2017-03-2": ("2017-03-27", "2017-03-29"),
    "2017-04-1": ("2017-04-10", "2017-04-12"),
    "2017-04-2": ("2017-04-24", "2017-04-26"),
    "2017-05-1": ("2017-05-08", "2017-05-11"),
    "2017-05-2": ("2017-05-22", "2017-05-24"),
    "2017-08-1": ("2017-08-07", "2017-08-10"),
    "2017-10-2": ("2017-10-16", "2017-10-19"),
    "2018-01-1": ("2018-01-02", "2018-01-04"),
    "2018-08-2": ("2018-08-20", "2018-08-23"),
    "2018-11-1": ("2018-11-05", "2018-11-08"),
    "2019-02-1": ("2019-02-04", "2019-02-08"),
    "2019-05-2": ("2019-05-21", "2019-05-23"),
    "2019-06-1": ("2019-06-03", "2019-06-06"),
    "2021-07-2": ("2021-07-19", "2021-07-22"),
    "2022-05-1": ("2022-05-04", "2022-05-06"),
    "2022-05-2": ("2022-05-17", "2022-05-19"),
    "2023-01-1": ("2023-01-03", "2023-01-05"),
    "2023-05-1": ("2023-05-02", "2023-05-04"),
    "2023-08-1": ("2023-08-07", "2023-08-10"),
}


def historical_schedules() -> dict[int, list[tuple[str, str, str]]]:
    result: dict[int, list[tuple[str, str, str]]] = {}
    for year in HISTORICAL_SOURCES:
        exercises = []
        for month in range(1, 13):
            month_calendar = calendar.monthcalendar(year, month)
            mondays = [week[calendar.MONDAY] for week in month_calendar if week[calendar.MONDAY]]
            for bidding_no, start_day in ((1, mondays[0]), (2, mondays[2])):
                tender_id = f"{year}-{month:02d}-{bidding_no}"
                start = pd.Timestamp(year=year, month=month, day=start_day)
                end = start + pd.Timedelta(days=2)
                if tender_id in HISTORICAL_OVERRIDES:
                    start_text, end_text = HISTORICAL_OVERRIDES[tender_id]
                    start, end = pd.Timestamp(start_text), pd.Timestamp(end_text)
                exercises.append(
                    (f"{month:02d}-{bidding_no}", start.strftime("%m-%d"), end.strftime("%m-%d"))
                )
        result[year] = exercises
    return result


def main() -> None:
    rows = []
    all_schedules = {**historical_schedules(), **SCHEDULES}
    for year, exercises in all_schedules.items():
        source = HISTORICAL_SOURCES.get(year) or (
            f"https://onemotoring.lta.gov.sg/content/dam/onemotoring/Buying/PDF/COE/COE_Bidding_Schedule_for_Year_{year}.pdf"
            if year < 2026
            else "https://onemotoring.lta.gov.sg/content/dam/onemotoring/pdf/Circulars%20to%20ESAs/2025/Circular%2021-2025_COE%20Bidding%20Schedule%20for%20Year%202026.pdf"
        )
        for suffix, start, end in exercises:
            for category in ("Category A", "Category B", "Category D"):
                rows.append({
                    "tender_id": f"{year}-{suffix}",
                    "category": category,
                    "forecast_cutoff_at": f"{year}-{start}T12:00:00+08:00",
                    "exercise_end_at": f"{year}-{end}T16:00:00+08:00",
                    "source_url": source,
                })
    target = Path(__file__).resolve().parents[1] / "data" / "tender_schedule_2017_2026.csv"
    pd.DataFrame(rows).to_csv(target, index=False)
    print(f"wrote {len(rows)} rows to {target}")


if __name__ == "__main__":
    main()

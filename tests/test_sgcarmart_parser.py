import pandas as pd

from scripts.sgcarmart.build_sgcarmart_dataset import category_for_page
from scripts.sgcarmart.export_dealer_observations import evidenced_available_at


def line(text: str, y: float = 0.85) -> dict:
    return {"text": text, "y": y}


def test_category_accepts_explicit_prefixed_page_heading():
    assert category_for_page([line("PRICE LIST: CATEGORY A")]) == (
        "A",
        "explicit_page_label",
    )


def test_category_rejects_mixed_category_page():
    assert category_for_page(
        [line("Hybrid - Category A"), line("Electric - Category B")]
    ) == ("A/B", "multiple_explicit_page_labels")


def test_category_ignores_footer_mentions():
    assert category_for_page([line("Terms for Category A", y=0.20)]) == (
        "Unclassified",
        "no_explicit_page_label",
    )


def test_historical_availability_defaults_to_singapore_end_of_day():
    row = pd.Series(
        {
            "source_document_date": "2024-01-05",
            "retrieved_at_utc": "2026-08-24T12:00:00+00:00",
        }
    )
    assert evidenced_available_at(row) == "2024-01-05T23:59:59+08:00"


def test_contemporaneous_retrieval_evidences_earlier_availability():
    row = pd.Series(
        {
            "source_document_date": "2026-08-24",
            "retrieved_at_utc": "2026-08-24T13:39:05.483674+00:00",
        }
    )
    assert evidenced_available_at(row) == "2026-08-24T21:39:05+08:00"

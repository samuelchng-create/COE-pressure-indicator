import pandas as pd

from scripts.sgcarmart.build_sgcarmart_dataset import category_for_page, page_features
from scripts.sgcarmart.export_dealer_observations import evidenced_available_at


def line(text: str, y: float = 0.85, x: float = 0.5) -> dict:
    return {"text": text, "y": y, "x": x, "width": 0.1, "height": 0.02}


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


def test_finance_rate_requires_an_explicit_plausible_rate_label():
    assert page_features([line("2.68% Interest Rate")])["finance_rate_pct"] == 2.68
    false_match = page_features(
        [line("Finance rebate for a $100,000 seven-year loan; discount 20%")]
    )
    assert pd.isna(false_match["finance_rate_pct"])

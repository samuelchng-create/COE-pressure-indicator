import pytest

from official_results import parse_one_motoring_final_results


FINAL_HTML = """
<h2>Results for SEPTEMBER 2026 1st Open Bidding Exercise</h2>
<table>
<tr><th colspan="2">Category</th><th>Quota</th><th>QP($)</th></tr>
<tr><td>A</td><td>Cars</td><td>1,195</td><td>133,009</td></tr>
<tr><td>B</td><td>Cars</td><td>934</td><td>135001</td></tr>
<tr><td>C</td><td>Goods</td><td>310</td><td>93101</td></tr>
<tr><td>D</td><td>Motorcycle</td><td>514</td><td>12556</td></tr>
<tr><td>E</td><td>Open</td><td>300</td><td>137890</td></tr>
</table>
<table>
<tr><th colspan="2">Category</th><th>Received</th><th>Successful</th><th>Unsuccessful</th><th>Unused</th></tr>
<tr><td>A</td><td>Cars</td><td>1708</td><td>1152</td><td>556</td><td>43</td></tr>
<tr><td>B</td><td>Cars</td><td>1333</td><td>910</td><td>423</td><td>24</td></tr>
<tr><td>C</td><td>Goods</td><td>565</td><td>306</td><td>259</td><td>4</td></tr>
<tr><td>D</td><td>Motorcycle</td><td>657</td><td>495</td><td>162</td><td>19</td></tr>
<tr><td>E</td><td>Open</td><td>513</td><td>300</td><td>213</td><td>0</td></tr>
</table>
"""


def test_parses_confirmed_one_motoring_result():
    records = parse_one_motoring_final_results(FINAL_HTML)
    assert len(records) == 5
    assert records[0] == {
        "month": "2026-09",
        "bidding_no": "1",
        "vehicle_class": "Category A",
        "quota": "1195",
        "premium": "133009",
        "bids_received": "1708",
        "bids_success": "1152",
    }


def test_provisional_table_without_final_result_heading_is_ignored():
    provisional = FINAL_HTML.replace(
        "<h2>Results for SEPTEMBER 2026 1st Open Bidding Exercise</h2>",
        "<h2>Bidding status as at 09/09/2026 15:59:00 hrs</h2>",
    )
    assert parse_one_motoring_final_results(provisional) == []


def test_incomplete_confirmed_result_is_rejected():
    incomplete = FINAL_HTML.replace(
        "<tr><td>E</td><td>Open</td><td>513</td><td>300</td><td>213</td><td>0</td></tr>",
        "",
    )
    with pytest.raises(ValueError, match="Categories A–E"):
        parse_one_motoring_final_results(incomplete)

import re
from html.parser import HTMLParser


MONTHS = {
    month.upper(): number
    for number, month in enumerate(
        (
            "January",
            "February",
            "March",
            "April",
            "May",
            "June",
            "July",
            "August",
            "September",
            "October",
            "November",
            "December",
        ),
        start=1,
    )
}


class _TableParser(HTMLParser):
    def __init__(self) -> None:
        super().__init__()
        self.headings: list[str] = []
        self.tables: list[list[list[str]]] = []
        self._heading: list[str] | None = None
        self._table: list[list[str]] | None = None
        self._row: list[str] | None = None
        self._cell: list[str] | None = None
        self.text: list[str] = []

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        del attrs
        if tag == "h2":
            self._heading = []
        elif tag == "table":
            self._table = []
        elif tag == "tr" and self._table is not None:
            self._row = []
        elif tag in {"td", "th"} and self._row is not None:
            self._cell = []

    def handle_data(self, data: str) -> None:
        cleaned = " ".join(data.split())
        if cleaned:
            self.text.append(cleaned)
        if self._heading is not None:
            self._heading.append(data)
        if self._cell is not None:
            self._cell.append(data)

    def handle_endtag(self, tag: str) -> None:
        if tag == "h2" and self._heading is not None:
            self.headings.append(" ".join("".join(self._heading).split()))
            self._heading = None
        elif tag in {"td", "th"} and self._cell is not None and self._row is not None:
            self._row.append(" ".join("".join(self._cell).split()))
            self._cell = None
        elif tag == "tr" and self._row is not None and self._table is not None:
            self._table.append(self._row)
            self._row = None
        elif tag == "table" and self._table is not None:
            self.tables.append(self._table)
            self._table = None


def _integer(value: str) -> int:
    if not re.fullmatch(r"[\d,]+", value.strip()):
        raise ValueError(f"Invalid numeric result value: {value!r}")
    return int(value.replace(",", ""))


def parse_one_motoring_final_results(html: str) -> list[dict[str, str]]:
    """Parse only a confirmed OneMotoring result, never a live/provisional table."""
    parser = _TableParser()
    parser.feed(html)
    heading_pattern = re.compile(
        r"^(?:Final )?Results for ([A-Z]+) (\d{4}) (1st|2nd) Open Bidding Exercise$",
        re.IGNORECASE,
    )
    heading_match = next(
        (match for heading in parser.headings if (match := heading_pattern.match(heading))),
        None,
    )
    if heading_match is None:
        return []

    month_name, year, ordinal = heading_match.groups()
    month_number = MONTHS.get(month_name.upper())
    if month_number is None:
        raise ValueError(f"Unknown result month: {month_name}")
    bidding_no = "1" if ordinal.lower() == "1st" else "2"

    result_table = next(
        (table for table in parser.tables if table and table[0][-2:] == ["Quota", "QP($)"]),
        None,
    )
    bid_table = next(
        (
            table
            for table in parser.tables
            if table and table[0][-4:] == ["Received", "Successful", "Unsuccessful", "Unused"]
        ),
        None,
    )
    if result_table is None or bid_table is None:
        raise ValueError("Confirmed OneMotoring result tables are incomplete")

    prices = {row[0]: (_integer(row[-2]), _integer(row[-1])) for row in result_table[1:] if len(row) >= 4}
    bids = {row[0]: (_integer(row[-4]), _integer(row[-3])) for row in bid_table[1:] if len(row) >= 6}
    expected = set("ABCDE")
    if set(prices) != expected or set(bids) != expected:
        raise ValueError("Confirmed OneMotoring result does not contain Categories A–E exactly once")

    month = f"{year}-{month_number:02d}"
    return [
        {
            "month": month,
            "bidding_no": bidding_no,
            "vehicle_class": f"Category {category}",
            "quota": str(prices[category][0]),
            "premium": str(prices[category][1]),
            "bids_received": str(bids[category][0]),
            "bids_success": str(bids[category][1]),
        }
        for category in "ABCDE"
    ]


def parse_one_motoring_upcoming_quotas(html: str) -> tuple[str, dict[str, int]] | None:
    """Return a strictly identified upcoming/active tender and announced quotas.

    During bidding, only the quota column is admitted. Provisional prices and
    bid counts from the live status table are deliberately ignored.
    """
    parser = _TableParser()
    parser.feed(html)
    text = " ".join(parser.text)
    match = re.search(
        r"Next COE Open Bidding Exercise Starts on (\d{1,2})/(\d{1,2})/(\d{4})",
        text,
        re.IGNORECASE,
    )
    active = False
    if match is None:
        match = re.search(
            r"Bidding status as at (\d{1,2})/(\d{1,2})/(\d{4})",
            text,
            re.IGNORECASE,
        )
        active = match is not None
    if match is None:
        return None
    day, month, year = map(int, match.groups())
    bidding_no = 1 if day <= 15 else 2
    tender_id = f"{year:04d}-{month:02d}-{bidding_no}"
    if active:
        quota_table = next(
            (
                table
                for table in parser.tables
                if table
                and table[0][-3:] == ["Current COE Price ($)", "Quota", "Bids Received"]
            ),
            None,
        )
        quota_position = -2
    else:
        quota_table = next(
            (
                table
                for table in parser.tables
                if table
                and table[0][-1:] == ["Quota"]
                and "QP($)" not in table[0]
            ),
            None,
        )
        quota_position = -1
    if quota_table is None:
        raise ValueError("Upcoming OneMotoring quota table is missing")
    quotas = {
        f"Category {row[0]}": _integer(row[quota_position])
        for row in quota_table[1:]
        if len(row) >= 2 and row[0] in set("ABCDE")
    }
    expected = {f"Category {category}" for category in "ABCDE"}
    if set(quotas) != expected:
        raise ValueError("Upcoming OneMotoring quota table does not contain Categories A–E exactly once")
    return tender_id, quotas

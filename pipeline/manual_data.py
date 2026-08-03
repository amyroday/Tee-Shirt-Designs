"""Optional manual data drop-in (e.g. a ListingView export).

ListingView (listingview.io) has real competitive marketplace data --
monthly sales, monthly units sold, month-over-month trend/variance across
listings and shops -- but only through its browser extension/dashboard, with
no public API. Rather than build a private-API integration against an
undocumented backend, the pipeline just looks for a CSV the user exports and
drops in by hand before a run.

If nothing is present, the report simply proceeds without this section and
says so -- it's a bonus input, not a dependency.

Recommended CSV columns (matching what ListingView's own dashboard shows;
extra/missing columns are fine -- everything present is preserved and passed
to the research step, nothing downstream requires a fixed schema):
    listing_title, shop_name, monthly_sales_usd, monthly_units_sold,
    mom_trend_pct, price, tags
"""

from __future__ import annotations

import csv
from pathlib import Path

MANUAL_DATA_DIR = Path(__file__).resolve().parent.parent / "data" / "manual"


def load_manual_exports() -> list[dict]:
    """Reads every *.csv in data/manual/, returns combined rows (empty list if none)."""
    if not MANUAL_DATA_DIR.exists():
        return []

    rows: list[dict] = []
    for csv_path in sorted(MANUAL_DATA_DIR.glob("*.csv")):
        with csv_path.open(newline="", encoding="utf-8") as f:
            reader = csv.DictReader(f)
            for row in reader:
                row["_source_file"] = csv_path.name
                rows.append(row)
    return rows


def format_manual_rows_context(rows: list[dict], max_rows: int = 40) -> str:
    """Renders manual rows as a compact text block for the LLM research prompt."""
    if not rows:
        return "No manual ListingView export provided for this run."

    lines = []
    for row in rows[:max_rows]:
        fields = {k: v for k, v in row.items() if k != "_source_file" and v}
        lines.append("- " + ", ".join(f"{k}: {v}" for k, v in fields.items()))
    if len(rows) > max_rows:
        lines.append(f"...and {len(rows) - max_rows} more rows.")
    return "\n".join(lines)

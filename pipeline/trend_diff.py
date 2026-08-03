"""Week-over-week trend diffing.

Loads the most recent prior week's data.json (if any) from weekly_reports/
and compares niches + Google Trends interest scores against this week's,
so the report can call out what's rising, falling, or shifting apparel type.
"""

from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path
from typing import Optional

WEEKLY_REPORTS_DIR = Path(__file__).resolve().parent.parent / "weekly_reports"


@dataclass
class TrendDiff:
    rising_niches: list[str]
    falling_niches: list[str]
    new_niches: list[str]
    prior_report_date: Optional[str]


def _extract_niches(research: dict) -> set[str]:
    niches = {item.get("niche", "") for item in research.get("overall_top_sellers", [])}
    return {n for n in niches if n}


def find_prior_week_data(before_date: str) -> Optional[dict]:
    """Finds the most recent data.json strictly before `before_date` (YYYY-MM-DD)."""
    if not WEEKLY_REPORTS_DIR.exists():
        return None

    candidates: list[tuple[str, Path]] = []
    for data_path in WEEKLY_REPORTS_DIR.glob("*/*/data.json"):
        report_date = data_path.parent.name  # weekly_reports/{YYYY}/{YYYY-MM-DD}/data.json
        if report_date < before_date:
            candidates.append((report_date, data_path))

    if not candidates:
        return None

    candidates.sort(key=lambda pair: pair[0])
    latest_date, latest_path = candidates[-1]
    with latest_path.open(encoding="utf-8") as f:
        payload = json.load(f)
    payload["_report_date"] = latest_date
    return payload


def diff_against_prior(current_research: dict, current_date: str) -> TrendDiff:
    prior = find_prior_week_data(current_date)
    if prior is None:
        return TrendDiff(
            rising_niches=[],
            falling_niches=[],
            new_niches=sorted(_extract_niches(current_research)),
            prior_report_date=None,
        )

    prior_research = prior.get("research", {})
    prior_niches = _extract_niches(prior_research)
    current_niches = _extract_niches(current_research)

    return TrendDiff(
        rising_niches=sorted(current_niches & prior_niches),
        falling_niches=sorted(prior_niches - current_niches),
        new_niches=sorted(current_niches - prior_niches),
        prior_report_date=prior.get("_report_date"),
    )

"""Google Trends search-interest signal via pytrends.

Not an official Google API (no public one exists for this), but pytrends is
the standard, widely-used wrapper around the same public trends.google.com
data the website itself shows -- distinct from scraping a marketplace's
private bestseller data, which we're avoiding.
"""

from __future__ import annotations

import time
from dataclasses import dataclass

from pytrends.request import TrendReq

MAX_KEYWORDS_PER_BATCH = 5


@dataclass
class KeywordTrend:
    keyword: str
    current_interest: int  # 0-100, Google Trends' relative scale
    pct_change_vs_prior_period: float  # rough momentum signal


def _chunks(items: list[str], size: int) -> list[list[str]]:
    return [items[i : i + size] for i in range(0, len(items), size)]


def get_keyword_trends(keywords: list[str], timeframe: str = "today 3-m") -> list[KeywordTrend]:
    """Fetch current interest + momentum for each keyword.

    Batches into groups of 5 (pytrends/Google Trends limit) and is tolerant
    of individual batch failures (rate limiting is common) -- failed
    keywords are simply omitted rather than crashing the whole report.
    """
    pytrends = TrendReq(hl="en-US", tz=360)
    results: list[KeywordTrend] = []

    for batch in _chunks(keywords, MAX_KEYWORDS_PER_BATCH):
        try:
            pytrends.build_payload(batch, timeframe=timeframe)
            df = pytrends.interest_over_time()
        except Exception:
            time.sleep(2)
            continue

        if df is None or df.empty:
            continue

        midpoint = len(df) // 2
        for kw in batch:
            if kw not in df.columns:
                continue
            series = df[kw]
            current = int(series.iloc[-4:].mean()) if len(series) >= 4 else int(series.iloc[-1])
            prior = series.iloc[:midpoint].mean() if midpoint > 0 else series.mean()
            pct_change = 0.0
            if prior and prior > 0:
                pct_change = round(((series.iloc[midpoint:].mean() - prior) / prior) * 100, 1)

            results.append(
                KeywordTrend(keyword=kw, current_interest=current, pct_change_vs_prior_period=pct_change)
            )

        time.sleep(1)  # be polite between batches

    return results

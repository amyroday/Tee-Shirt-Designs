"""Renders the weekly report (Markdown + HTML + data.json) and updates the
GitHub Pages dashboard's index.html to point at it.
"""

from __future__ import annotations

import json
import re
from pathlib import Path
from typing import Any, Optional

from trend_diff import TrendDiff

REPO_ROOT = Path(__file__).resolve().parent.parent
WEEKLY_REPORTS_DIR = REPO_ROOT / "weekly_reports"
INDEX_HTML_PATH = REPO_ROOT / "index.html"


def _fmt_currency(value: Any) -> str:
    try:
        return f"${float(value):.2f}"
    except (TypeError, ValueError):
        return "n/a"


def render_markdown(
    date: str,
    research: dict,
    etsy_top_listings: list,
    trends_rows: list,
    diff: TrendDiff,
    manual_rows: list,
) -> str:
    lines: list[str] = []
    lines.append(f"# Weekly Tee & Sweatshirt Trends – {date}")
    lines.append("")
    lines.append("## Summary & Key Recommendations")
    lines.append(research.get("summary", ""))
    lines.append("")

    lines.append("## Overall Top Sellers (All Niches)")
    lines.append("")
    lines.append("| Product Type | Printify Product | Niche | Design | Price | Est. Profit | Source |")
    lines.append("|---|---|---|---|---|---|---|")
    for item in research.get("overall_top_sellers", []):
        lines.append(
            "| {product_type} | {printify_product_hint} | {niche} | {design_description} | "
            "{price} | {profit} | [link]({source_url}) |".format(
                product_type=item.get("product_type", ""),
                printify_product_hint=item.get("printify_product_hint", ""),
                niche=item.get("niche", ""),
                design_description=item.get("design_description", ""),
                price=_fmt_currency(item.get("price_usd")),
                profit=_fmt_currency(item.get("estimated_profit_usd")),
                source_url=item.get("source_url", "#"),
            )
        )
    lines.append("")

    political = research.get("political", {})
    lines.append("## Political & Election Tees (2026 Midterms)")
    lines.append("")
    lines.append(political.get("narrative", ""))
    lines.append("")
    if political.get("apparel_type_shift_note"):
        lines.append(f"**Apparel type shift:** {political['apparel_type_shift_note']}")
        lines.append("")
    lines.append("| Slogan / Theme | Visual Motif | Tone | Product Type | Printify Product |")
    lines.append("|---|---|---|---|---|")
    for item in political.get("items", []):
        lines.append(
            "| {slogan_or_theme} | {visual_motif} | {tone} | {product_type} | {printify_product_hint} |".format(
                **{k: item.get(k, "") for k in
                   ["slogan_or_theme", "visual_motif", "tone", "product_type", "printify_product_hint"]}
            )
        )
    lines.append("")

    seasonal = research.get("seasonal", {})
    lines.append("## Seasonal Tees (Fall / Thanksgiving / Football / Christmas)")
    lines.append("")
    if seasonal.get("apparel_type_shift_note"):
        lines.append(f"**Apparel type shift:** {seasonal['apparel_type_shift_note']}")
        lines.append("")
    for sub_season in ["fall", "thanksgiving", "football", "christmas"]:
        lines.append(f"### {sub_season.title()}")
        for entry in seasonal.get(sub_season, []):
            lines.append(f"- {entry}")
        lines.append("")

    hcp = research.get("historical_vs_current_vs_predicted", {})
    lines.append("## Historical vs Current vs Predicted Trends")
    lines.append("")
    lines.append("**Historical (evergreen):**")
    for entry in hcp.get("historical", []):
        lines.append(f"- {entry}")
    lines.append("")
    lines.append("**Current (last 30-90 days):**")
    for entry in hcp.get("current", []):
        lines.append(f"- {entry}")
    lines.append("")
    lines.append("**Predicted (next 1-3 months):**")
    for entry in hcp.get("predicted", []):
        lines.append(f"- {entry}")
    lines.append("")

    lines.append("## Week-over-Week Movement")
    lines.append("")
    if diff.prior_report_date is None:
        lines.append("No prior week to compare against -- this is the first report.")
    else:
        lines.append(f"Compared against the {diff.prior_report_date} report.")
        lines.append("")
        lines.append(f"- **Persisting niches:** {', '.join(diff.rising_niches) or 'none'}")
        lines.append(f"- **New this week:** {', '.join(diff.new_niches) or 'none'}")
        lines.append(f"- **Dropped off:** {', '.join(diff.falling_niches) or 'none'}")
    lines.append("")

    if etsy_top_listings:
        lines.append("## Your Shop's Real Top Sellers (Last 60 Days)")
        lines.append("")
        lines.append("| Listing | Units Sold | Revenue |")
        lines.append("|---|---|---|")
        for listing in etsy_top_listings[:15]:
            lines.append(
                f"| {listing.title} | {listing.units_sold_in_window} | "
                f"{_fmt_currency(listing.revenue_usd_in_window)} |"
            )
        lines.append("")

    if trends_rows:
        lines.append("## Google Trends Signals")
        lines.append("")
        lines.append("| Keyword | Interest (0-100) | Momentum |")
        lines.append("|---|---|---|")
        for row in trends_rows:
            lines.append(f"| {row.keyword} | {row.current_interest} | {row.pct_change_vs_prior_period:+.1f}% |")
        lines.append("")

    if manual_rows:
        lines.append("## Manual Competitive Data (ListingView Export)")
        lines.append("")
        lines.append(f"{len(manual_rows)} rows imported from data/manual/ -- see data.json for full detail.")
        lines.append("")

    lines.append("## Design Gaps We Can Exploit")
    for entry in research.get("design_gaps", []):
        lines.append(f"- {entry}")
    lines.append("")

    action = research.get("action_plan", {})
    lines.append("## Action Plan to Reach $10,000 Net Income")
    lines.append("")
    lines.append(f"**Designs to launch this week:** {action.get('designs_to_launch_this_week', 'n/a')}")
    lines.append("")
    lines.append("**Priority niches:** " + ", ".join(action.get("priority_niches", [])))
    lines.append("")
    lines.append(f"**Pricing notes:** {action.get('pricing_notes', '')}")
    lines.append("")
    lines.append("**This week's tasks:**")
    for task in action.get("weekly_tasks", []):
        lines.append(f"- {task}")
    lines.append("")

    return "\n".join(lines)


def render_html(date: str, markdown_body: str) -> str:
    # Minimal, dependency-free Markdown -> HTML: headings, bold, lists, tables, links.
    html_lines: list[str] = []
    in_list = False
    in_table = False

    def close_list():
        nonlocal in_list
        if in_list:
            html_lines.append("</ul>")
            in_list = False

    def close_table():
        nonlocal in_table
        if in_table:
            html_lines.append("</table>")
            in_table = False

    def inline(text: str) -> str:
        text = re.sub(r"\*\*(.+?)\*\*", r"<strong>\1</strong>", text)
        text = re.sub(r"\[(.+?)\]\((.+?)\)", r'<a href="\2">\1</a>', text)
        return text

    for raw_line in markdown_body.split("\n"):
        line = raw_line.rstrip()

        if line.startswith("# "):
            close_list(); close_table()
            html_lines.append(f"<h1>{inline(line[2:])}</h1>")
        elif line.startswith("### "):
            close_list(); close_table()
            html_lines.append(f"<h3>{inline(line[4:])}</h3>")
        elif line.startswith("## "):
            close_list(); close_table()
            html_lines.append(f"<h2>{inline(line[3:])}</h2>")
        elif line.startswith("|"):
            close_list()
            cells = [c.strip() for c in line.strip("|").split("|")]
            if all(re.fullmatch(r"-+", c) for c in cells):
                continue  # markdown table separator row
            if not in_table:
                html_lines.append('<table class="report-table">')
                in_table = True
                tag = "th"
            else:
                tag = "td"
            html_lines.append("<tr>" + "".join(f"<{tag}>{inline(c)}</{tag}>" for c in cells) + "</tr>")
        elif line.startswith("- "):
            close_table()
            if not in_list:
                html_lines.append("<ul>")
                in_list = True
            html_lines.append(f"<li>{inline(line[2:])}</li>")
        elif line == "":
            close_list(); close_table()
        else:
            close_list(); close_table()
            html_lines.append(f"<p>{inline(line)}</p>")

    close_list(); close_table()
    body = "\n".join(html_lines)

    return f"""<!DOCTYPE html>
<html lang="en">
<head>
  <meta charset="UTF-8">
  <title>Tee Research Report - {date}</title>
  <link rel="stylesheet" href="../../../assets/css/style.css">
  <style>
    .report-table {{ border-collapse: collapse; width: 100%; margin: 12px 0; }}
    .report-table th, .report-table td {{ border: 1px solid #ddd; padding: 6px 10px; text-align: left; }}
    .report-table th {{ background: #1a1a2e; color: white; }}
  </style>
</head>
<body>
<header>
  <h1>Whimsical Ember Apparel</h1>
  <p>Weekly Tee &amp; Sweatshirt Trend Report - {date}</p>
</header>
<nav>
  <a href="../../../index.html">Home</a>
  <a href="../../">All Reports</a>
</nav>
<div class="container">
{body}
</div>
</body>
</html>
"""


def write_report(
    date: str,
    research: dict,
    etsy_top_listings: list,
    trends_rows: list,
    diff: TrendDiff,
    manual_rows: list,
) -> dict[str, Path]:
    year = date.split("-")[0]
    report_dir = WEEKLY_REPORTS_DIR / year / date
    report_dir.mkdir(parents=True, exist_ok=True)

    markdown_body = render_markdown(date, research, etsy_top_listings, trends_rows, diff, manual_rows)
    html_body = render_html(date, markdown_body)

    md_path = report_dir / f"Tee_Research_Report_{date}.md"
    html_path = report_dir / f"Tee_Research_Report_{date}.html"
    data_path = report_dir / "data.json"

    md_path.write_text(markdown_body, encoding="utf-8")
    html_path.write_text(html_body, encoding="utf-8")
    data_path.write_text(
        json.dumps(
            {
                "date": date,
                "research": research,
                "etsy_top_listings": [
                    {
                        "listing_id": listing.listing_id,
                        "title": listing.title,
                        "units_sold_in_window": listing.units_sold_in_window,
                        "revenue_usd_in_window": listing.revenue_usd_in_window,
                    }
                    for listing in etsy_top_listings
                ],
                "trends": [
                    {
                        "keyword": row.keyword,
                        "current_interest": row.current_interest,
                        "pct_change_vs_prior_period": row.pct_change_vs_prior_period,
                    }
                    for row in trends_rows
                ],
                "manual_rows": manual_rows,
            },
            indent=2,
        ),
        encoding="utf-8",
    )

    return {"markdown": md_path, "html": html_path, "data": data_path}


def update_index_html(date: str, max_list_entries: int = 10) -> None:
    """Rewrites index.html's 'latest report' link and prepends this week to the report list."""
    html = INDEX_HTML_PATH.read_text(encoding="utf-8")
    year = date.split("-")[0]
    report_rel_path = f"weekly_reports/{year}/{date}/Tee_Research_Report_{date}.html"

    latest_html = f'<p id="latest-report"><a href="{report_rel_path}">View Latest Report ({date})</a></p>'
    html = re.sub(
        r"<!-- LATEST_REPORT_START -->.*?<!-- LATEST_REPORT_END -->",
        f"<!-- LATEST_REPORT_START -->\n{latest_html}\n<!-- LATEST_REPORT_END -->",
        html,
        flags=re.DOTALL,
    )

    list_match = re.search(r"<!-- REPORT_LIST_START -->(.*?)<!-- REPORT_LIST_END -->", html, flags=re.DOTALL)
    existing_items = []
    if list_match:
        existing_items = re.findall(r"<li>.*?</li>", list_match.group(1), flags=re.DOTALL)

    new_item = f'<li><a href="{report_rel_path}">Week of {date}</a></li>'
    # Avoid duplicating an entry if this date was already run today.
    existing_items = [item for item in existing_items if date not in item]
    updated_items = [new_item] + existing_items
    updated_items = updated_items[:max_list_entries]

    new_list_block = "<!-- REPORT_LIST_START -->\n    " + "\n    ".join(updated_items) + "\n    <!-- REPORT_LIST_END -->"
    html = re.sub(
        r"<!-- REPORT_LIST_START -->.*?<!-- REPORT_LIST_END -->",
        new_list_block,
        html,
        flags=re.DOTALL,
    )

    INDEX_HTML_PATH.write_text(html, encoding="utf-8")

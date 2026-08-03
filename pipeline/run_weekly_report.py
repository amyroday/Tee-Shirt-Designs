"""Orchestrator entry point for the weekly trend report.

    python pipeline/run_weekly_report.py [--dry-run]

--dry-run writes the report files locally but skips the git commit/push and
skips persisting a rotated Etsy refresh token -- use it for local testing.
"""

from __future__ import annotations

import argparse
import json
import subprocess
import sys
from datetime import date as date_cls
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

import github_secrets
import llm_research
import report_builder
import trend_diff
from config import Config, MissingConfigError
from etsy_client import EtsyClient
from manual_data import format_manual_rows_context, load_manual_exports
from printify_client import PrintifyClient
from trends_client import get_keyword_trends

REPO_ROOT = Path(__file__).resolve().parent.parent

CANDIDATE_PRODUCT_TYPES = ["tee", "long sleeve tee", "sweatshirt", "hoodie"]

TRENDS_KEYWORDS = [
    "graphic tee", "crewneck sweatshirt", "political t shirt",
    "christmas sweatshirt", "thanksgiving shirt", "football shirt",
    "fall t shirt", "funny sweatshirt", "vintage graphic tee",
    "coquette shirt", "y2k shirt", "comfort colors shirt",
]


def build_printify_context(client: PrintifyClient) -> tuple[str, dict]:
    lines = []
    resolved = {}
    for product_type in CANDIDATE_PRODUCT_TYPES:
        product = client.resolve_product(product_type)
        if product is None:
            lines.append(f"- {product_type}: no catalog match found")
            continue
        resolved[product_type] = product
        has_cost = product.sample_variant and product.sample_variant.cost_cents is not None
        cost_str = f"${product.sample_variant.cost_cents / 100:.2f}" if has_cost else "not available from Printify's catalog API -- target $7-$10 net profit/unit instead"
        lines.append(
            f"- {product_type}: {product.blueprint_title} via {product.print_provider_title}, "
            f"base cost {cost_str}, colors: {', '.join(product.all_colors[:8])}"
        )
    return "\n".join(lines), resolved


def build_etsy_context(listings: list) -> str:
    if not listings:
        return "No Etsy sales data available."
    lines = [
        f"- {listing.title}: {listing.units_sold_in_window} units, "
        f"${listing.revenue_usd_in_window:.2f} revenue (last 60 days)"
        for listing in listings[:15]
    ]
    return "\n".join(lines)


def build_trends_context(rows: list) -> str:
    if not rows:
        return "No Google Trends data available."
    return "\n".join(
        f"- {row.keyword}: interest {row.current_interest}/100, momentum {row.pct_change_vs_prior_period:+.1f}%"
        for row in rows
    )


def build_prior_week_context(diff: trend_diff.TrendDiff) -> str:
    if diff.prior_report_date is None:
        return ""
    return (
        f"Last report was {diff.prior_report_date}. "
        f"Niches that persisted: {', '.join(diff.rising_niches) or 'none'}. "
        f"Niches that dropped off: {', '.join(diff.falling_niches) or 'none'}."
    )


def git_commit_and_push(paths: list[Path], date: str) -> None:
    rel_paths = [str(p.relative_to(REPO_ROOT)) for p in paths]
    subprocess.run(["git", "add", *rel_paths, "index.html"], cwd=REPO_ROOT, check=True)
    subprocess.run(
        ["git", "commit", "-m", f"Weekly tee trend report - {date}"],
        cwd=REPO_ROOT,
        check=True,
    )
    subprocess.run(["git", "push"], cwd=REPO_ROOT, check=True)


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--dry-run", action="store_true")
    args = parser.parse_args()

    try:
        config = Config.load(require_all=not args.dry_run)
    except MissingConfigError as e:
        print(f"Config error: {e}", file=sys.stderr)
        sys.exit(1)

    today = date_cls.today().isoformat()
    print(f"Building weekly report for {today} (dry_run={args.dry_run})")

    printify_context = ""
    if config.printify_token:
        printify = PrintifyClient(config.printify_token, config.printify_shop_id)
        printify_context, _ = build_printify_context(printify)

    etsy_listings: list = []
    if config.etsy_api_key and config.etsy_refresh_token:
        def on_refresh(new_token: str) -> None:
            if not args.dry_run:
                github_secrets.update_secret(
                    config.github_repository, "ETSY_REFRESH_TOKEN", new_token, config.gh_pat_for_secrets
                )

        etsy = EtsyClient(
            config.etsy_api_key,
            config.etsy_shared_secret,
            config.etsy_shop_id,
            config.etsy_refresh_token,
            on_token_refreshed=on_refresh,
        )
        etsy_listings = etsy.summarize_sales_window(days=60)

    trends_rows = []
    try:
        trends_rows = get_keyword_trends(TRENDS_KEYWORDS)
    except Exception as e:
        print(f"Google Trends fetch failed (continuing without it): {e}", file=sys.stderr)

    manual_rows = load_manual_exports()
    manual_context = format_manual_rows_context(manual_rows)
    if manual_rows:
        print(f"Loaded {len(manual_rows)} manual rows from data/manual/")

    etsy_context = build_etsy_context(etsy_listings)
    trends_context = build_trends_context(trends_rows)

    # Prior-week context for the LLM needs a niche diff computed against a
    # placeholder empty research dict first, since we don't have this week's
    # niches yet -- trend_diff only needs the prior file, so this is safe.
    preliminary_diff = trend_diff.diff_against_prior({}, today)
    prior_week_context = build_prior_week_context(preliminary_diff)

    if not config.anthropic_api_key:
        print("ANTHROPIC_API_KEY not set -- cannot run research step.", file=sys.stderr)
        sys.exit(1)

    research = llm_research.run_research(
        printify_context, etsy_context, trends_context, prior_week_context, manual_context, config.anthropic_api_key
    )

    diff = trend_diff.diff_against_prior(research, today)

    paths = report_builder.write_report(today, research, etsy_listings, trends_rows, diff, manual_rows)
    report_builder.update_index_html(today)

    print("Wrote:")
    for label, path in paths.items():
        print(f"  {label}: {path}")

    if args.dry_run:
        print("Dry run -- skipping git commit/push.")
        return

    git_commit_and_push(list(paths.values()) + [REPO_ROOT / "index.html"], today)
    print("Committed and pushed.")


if __name__ == "__main__":
    main()

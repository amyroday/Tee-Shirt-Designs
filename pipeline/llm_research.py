"""Qualitative trend research via the Anthropic API.

No public API exposes competitor bestseller data on Etsy or anywhere else in
this space (confirmed by the old routine's own methodology notes). This is
the one step that still needs an LLM: it reads public trend sources with the
web search tool and synthesizes the same kind of "top designs / political /
seasonal / forecast" narrative the old routine produced by hand -- but now
grounded in the shop's *real* Printify/Etsy/Trends numbers passed in as
context, instead of working from nothing.
"""

from __future__ import annotations

import json
from typing import Any

import anthropic

MODEL = "claude-opus-5"

RESPONSE_SCHEMA = {
    "type": "object",
    "properties": {
        "summary": {"type": "string"},
        "overall_top_sellers": {
            "type": "array",
            "items": {
                "type": "object",
                "properties": {
                    "product_type": {"type": "string"},
                    "printify_product_hint": {"type": "string"},
                    "niche": {"type": "string"},
                    "design_description": {"type": "string"},
                    "price_usd": {"type": "number"},
                    "estimated_profit_usd": {"type": "number"},
                    "source_url": {"type": "string"},
                },
                "required": [
                    "product_type",
                    "printify_product_hint",
                    "niche",
                    "design_description",
                    "price_usd",
                    "estimated_profit_usd",
                    "source_url",
                ],
                "additionalProperties": False,
            },
        },
        "political": {
            "type": "object",
            "properties": {
                "narrative": {"type": "string"},
                "apparel_type_shift_note": {"type": "string"},
                "items": {
                    "type": "array",
                    "items": {
                        "type": "object",
                        "properties": {
                            "slogan_or_theme": {"type": "string"},
                            "visual_motif": {"type": "string"},
                            "tone": {"type": "string"},
                            "product_type": {"type": "string"},
                            "printify_product_hint": {"type": "string"},
                        },
                        "required": [
                            "slogan_or_theme",
                            "visual_motif",
                            "tone",
                            "product_type",
                            "printify_product_hint",
                        ],
                        "additionalProperties": False,
                    },
                },
            },
            "required": ["narrative", "apparel_type_shift_note", "items"],
            "additionalProperties": False,
        },
        "seasonal": {
            "type": "object",
            "properties": {
                "fall": {"type": "array", "items": {"type": "string"}},
                "thanksgiving": {"type": "array", "items": {"type": "string"}},
                "football": {"type": "array", "items": {"type": "string"}},
                "christmas": {"type": "array", "items": {"type": "string"}},
                "apparel_type_shift_note": {"type": "string"},
            },
            "required": ["fall", "thanksgiving", "football", "christmas", "apparel_type_shift_note"],
            "additionalProperties": False,
        },
        "historical_vs_current_vs_predicted": {
            "type": "object",
            "properties": {
                "historical": {"type": "array", "items": {"type": "string"}},
                "current": {"type": "array", "items": {"type": "string"}},
                "predicted": {"type": "array", "items": {"type": "string"}},
            },
            "required": ["historical", "current", "predicted"],
            "additionalProperties": False,
        },
        "design_gaps": {"type": "array", "items": {"type": "string"}},
        "action_plan": {
            "type": "object",
            "properties": {
                "designs_to_launch_this_week": {"type": "integer"},
                "priority_niches": {"type": "array", "items": {"type": "string"}},
                "pricing_notes": {"type": "string"},
                "weekly_tasks": {"type": "array", "items": {"type": "string"}},
            },
            "required": [
                "designs_to_launch_this_week",
                "priority_niches",
                "pricing_notes",
                "weekly_tasks",
            ],
            "additionalProperties": False,
        },
    },
    "required": [
        "summary",
        "overall_top_sellers",
        "political",
        "seasonal",
        "historical_vs_current_vs_predicted",
        "design_gaps",
        "action_plan",
    ],
    "additionalProperties": False,
}

SYSTEM_PROMPT = """You are the research analyst for Whimsical Ember Apparel, a print-on-demand \
tee/sweatshirt shop on Etsy fulfilled via Printify. Use web search to find current, real trend \
signals (Etsy's own /trends pages, POD trend blogs like Printify/Printful/Kittl, Pinterest-driven \
consumer trend coverage) -- do not invent sources. You are given the shop's actual Printify \
catalog options, the shop's own real recent sales data, and Google Trends search-interest scores \
as grounding context; use them to make recommendations concrete and specific to products this \
shop can actually make. Focus areas: overall top sellers across niches, political/2026-midterm \
election tees, and seasonal tees (Fall/Thanksgiving/Football/Christmas). For every design \
recommendation, note the product type (tee/long sleeve/sweatshirt/hoodie) and explicitly flag \
when the winning apparel type is shifting (e.g. tees to sweatshirts as fall progresses). \
When a manual ListingView export is provided, treat it as your most reliable signal -- it's \
real monthly sales/units/trend data from actual competing listings, not a web search estimate \
-- and prioritize items and niches it surfaces over generic blog-sourced trend claims."""


def run_research(
    printify_context: str,
    etsy_context: str,
    trends_context: str,
    prior_week_context: str,
    manual_context: str,
    anthropic_api_key: str,
) -> dict[str, Any]:
    client = anthropic.Anthropic(api_key=anthropic_api_key)

    user_prompt = f"""Research this week's tee/sweatshirt trends and produce the report data.

## This shop's real Printify catalog options
{printify_context}

## This shop's real Etsy sales (last 60 days)
{etsy_context}

## Google Trends search-interest signals
{trends_context}

## Manual ListingView export (real competitive monthly sales/units/trend data, if provided)
{manual_context}

## Last week's report (for comparison -- note what's rising/falling)
{prior_week_context or "No prior week data available -- this is the first run."}
"""

    messages = [{"role": "user", "content": user_prompt}]

    for _ in range(3):  # allow a couple of pause_turn resumes for the server-side search loop
        response = client.messages.create(
            model=MODEL,
            max_tokens=8000,
            system=SYSTEM_PROMPT,
            tools=[{"type": "web_search_20260209", "name": "web_search"}],
            output_config={"format": {"type": "json_schema", "schema": RESPONSE_SCHEMA}},
            messages=messages,
        )

        if response.stop_reason == "pause_turn":
            messages = [{"role": "user", "content": user_prompt}, {"role": "assistant", "content": response.content}]
            continue

        text = next(block.text for block in response.content if block.type == "text")
        return json.loads(text)

    raise RuntimeError("Research call did not complete after multiple pause_turn resumes")

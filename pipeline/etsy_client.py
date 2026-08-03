"""Thin client over the official Etsy Open API v3.

Pulls the shop's own real sales/listings data (receipts + active listings)
for the trailing N days. This replaces guesswork with actual numbers for
"what's selling in my shop right now."

Etsy rotates the refresh_token every time it's used (old one stops working),
so callers should pass `on_token_refreshed` to persist the new token --
see pipeline/github_secrets.py for how the orchestrator does this in CI.
"""

from __future__ import annotations

import time
from dataclasses import dataclass, field
from typing import Callable, Optional

import requests

OAUTH_TOKEN_URL = "https://api.etsy.com/v3/public/oauth/token"
API_BASE = "https://openapi.etsy.com/v3/application"


@dataclass
class ShopListingSummary:
    listing_id: int
    title: str
    price_usd: float
    units_sold_in_window: int = 0
    revenue_usd_in_window: float = 0.0


class EtsyClient:
    def __init__(
        self,
        api_key: str,
        shared_secret: str,
        shop_id: str,
        refresh_token: str,
        on_token_refreshed: Optional[Callable[[str], None]] = None,
    ):
        self.api_key = api_key
        self.shared_secret = shared_secret
        self.shop_id = shop_id
        self._refresh_token = refresh_token
        self._access_token: Optional[str] = None
        self._access_token_expires_at: float = 0.0
        self._on_token_refreshed = on_token_refreshed
        self._session = requests.Session()

    def _ensure_access_token(self) -> str:
        if self._access_token and time.time() < self._access_token_expires_at - 60:
            return self._access_token

        resp = requests.post(
            OAUTH_TOKEN_URL,
            data={
                "grant_type": "refresh_token",
                "client_id": self.api_key,
                "refresh_token": self._refresh_token,
            },
            timeout=30,
        )
        resp.raise_for_status()
        payload = resp.json()

        self._access_token = payload["access_token"]
        self._access_token_expires_at = time.time() + payload.get("expires_in", 3600)

        new_refresh_token = payload.get("refresh_token")
        if new_refresh_token and new_refresh_token != self._refresh_token:
            self._refresh_token = new_refresh_token
            if self._on_token_refreshed:
                self._on_token_refreshed(new_refresh_token)

        return self._access_token

    def _headers(self) -> dict:
        return {
            "x-api-key": f"{self.api_key}:{self.shared_secret}",
            "Authorization": f"Bearer {self._ensure_access_token()}",
        }

    def _get(self, path: str, params: Optional[dict] = None) -> dict:
        resp = self._session.get(
            f"{API_BASE}{path}", headers=self._headers(), params=params or {}, timeout=30
        )
        resp.raise_for_status()
        return resp.json()

    def get_receipts_since(self, min_created_epoch: int) -> list[dict]:
        """Paginated fetch of shop receipts (orders) created after the given epoch."""
        results: list[dict] = []
        offset = 0
        limit = 100
        while True:
            page = self._get(
                f"/shops/{self.shop_id}/receipts",
                params={"min_created": min_created_epoch, "limit": limit, "offset": offset},
            )
            batch = page.get("results", [])
            results.extend(batch)
            if len(batch) < limit:
                break
            offset += limit
        return results

    def get_active_listings(self) -> list[dict]:
        results: list[dict] = []
        offset = 0
        limit = 100
        while True:
            page = self._get(
                f"/shops/{self.shop_id}/listings/active",
                params={"limit": limit, "offset": offset},
            )
            batch = page.get("results", [])
            results.extend(batch)
            if len(batch) < limit:
                break
            offset += limit
        return results

    def summarize_sales_window(self, days: int = 60) -> list[ShopListingSummary]:
        """Aggregate receipts' transactions into per-listing units/revenue for the trailing window."""
        min_created = int(time.time()) - days * 86400
        receipts = self.get_receipts_since(min_created)

        listings_by_id: dict[int, ShopListingSummary] = {}
        for listing in self.get_active_listings():
            listings_by_id[listing["listing_id"]] = ShopListingSummary(
                listing_id=listing["listing_id"],
                title=listing.get("title", ""),
                price_usd=(listing.get("price", {}) or {}).get("amount", 0)
                / max((listing.get("price", {}) or {}).get("divisor", 100), 1),
            )

        for receipt in receipts:
            for txn in receipt.get("transactions", []):
                listing_id = txn.get("listing_id")
                if listing_id is None:
                    continue
                summary = listings_by_id.get(listing_id)
                if summary is None:
                    price = (txn.get("price", {}) or {}).get("amount", 0) / max(
                        (txn.get("price", {}) or {}).get("divisor", 100), 1
                    )
                    summary = ShopListingSummary(
                        listing_id=listing_id, title=txn.get("title", ""), price_usd=price
                    )
                    listings_by_id[listing_id] = summary

                qty = txn.get("quantity", 1)
                price = (txn.get("price", {}) or {}).get("amount", 0) / max(
                    (txn.get("price", {}) or {}).get("divisor", 100), 1
                )
                summary.units_sold_in_window += qty
                summary.revenue_usd_in_window += price * qty

        return sorted(
            listings_by_id.values(), key=lambda s: s.revenue_usd_in_window, reverse=True
        )

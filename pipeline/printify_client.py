"""Thin client over the official Printify REST API (api.printify.com/v1).

Used to resolve "top design -> real Printify product" (brand/model/color)
and to pull the actual base cost so the report can compute margins.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Optional

import requests

BASE_URL = "https://api.printify.com/v1"

# Priority-ordered blueprint title keywords per product type, seeded from
# what the business has historically found sells (Comfort Colors garment-dyed,
# Bella+Canvas / Gildan basics). Used to pick a default candidate when the
# report doesn't have a more specific match.
DEFAULT_BLUEPRINT_PREFERENCES: dict[str, list[str]] = {
    "tee": ["Comfort Colors 1717", "Bella+Canvas 3001", "Gildan 5000"],
    "long sleeve tee": ["Comfort Colors 6014", "Bella+Canvas 3501", "Gildan 5400"],
    "sweatshirt": ["Comfort Colors 1566", "Gildan 18000", "Independent Trading Co SS3000"],
    "hoodie": ["Independent Trading Co SS4500", "Gildan 18500", "Bella+Canvas 3719"],
}


@dataclass
class VariantCost:
    variant_id: int
    color: str
    size: str
    cost_cents: int


@dataclass
class ResolvedProduct:
    product_type: str
    blueprint_id: int
    blueprint_title: str
    print_provider_id: int
    print_provider_title: str
    sample_variant: Optional[VariantCost]
    all_colors: list[str]


class PrintifyClient:
    def __init__(self, token: str, shop_id: str = ""):
        self.shop_id = shop_id
        self._session = requests.Session()
        self._session.headers.update(
            {"Authorization": f"Bearer {token}", "User-Agent": "whimsical-ember-report/1.0"}
        )
        self._blueprint_cache: Optional[list[dict]] = None

    def _get(self, path: str) -> dict | list:
        resp = self._session.get(f"{BASE_URL}{path}", timeout=30)
        resp.raise_for_status()
        return resp.json()

    def list_blueprints(self) -> list[dict]:
        if self._blueprint_cache is None:
            self._blueprint_cache = self._get("/catalog/blueprints.json")
        return self._blueprint_cache

    def search_blueprints(self, keyword: str) -> list[dict]:
        keyword_lower = keyword.lower()
        return [
            bp
            for bp in self.list_blueprints()
            if keyword_lower in bp.get("title", "").lower()
        ]

    def get_print_providers(self, blueprint_id: int) -> list[dict]:
        return self._get(f"/catalog/blueprints/{blueprint_id}/print_providers.json")

    def get_variants(self, blueprint_id: int, print_provider_id: int) -> dict:
        return self._get(
            f"/catalog/blueprints/{blueprint_id}/print_providers/{print_provider_id}/variants.json"
        )

    def resolve_product(
        self, product_type: str, keyword_override: Optional[str] = None
    ) -> Optional[ResolvedProduct]:
        """Find the best-matching real Printify product for a product type.

        Tries `keyword_override` first (e.g. a specific blueprint title pulled
        from research), then falls back to DEFAULT_BLUEPRINT_PREFERENCES.
        """
        candidates = [keyword_override] if keyword_override else []
        candidates += DEFAULT_BLUEPRINT_PREFERENCES.get(product_type.lower(), [])

        for candidate in candidates:
            if not candidate:
                continue
            matches = self.search_blueprints(candidate)
            if not matches:
                continue
            blueprint = matches[0]
            providers = self.get_print_providers(blueprint["id"])
            if not providers:
                continue
            provider = providers[0]
            variants_resp = self.get_variants(blueprint["id"], provider["id"])
            variants = variants_resp.get("variants", [])
            if not variants:
                continue

            colors = sorted({v.get("options", {}).get("color", "") for v in variants} - {""})
            first = variants[0]
            sample = VariantCost(
                variant_id=first["id"],
                color=first.get("options", {}).get("color", ""),
                size=first.get("options", {}).get("size", ""),
                cost_cents=first.get("cost", 0),
            )
            return ResolvedProduct(
                product_type=product_type,
                blueprint_id=blueprint["id"],
                blueprint_title=blueprint["title"],
                print_provider_id=provider["id"],
                print_provider_title=provider.get("title", ""),
                sample_variant=sample,
                all_colors=colors,
            )
        return None

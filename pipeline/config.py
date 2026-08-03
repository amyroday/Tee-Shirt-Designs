"""Loads pipeline configuration from environment variables.

Works both locally (via a .env file, loaded through python-dotenv) and in
GitHub Actions (via repo secrets exported as env vars) -- no code changes
needed between the two.
"""

from __future__ import annotations

import os
from dataclasses import dataclass

from dotenv import load_dotenv

load_dotenv()


class MissingConfigError(RuntimeError):
    pass


def _require(name: str) -> str:
    value = os.environ.get(name, "").strip()
    if not value:
        raise MissingConfigError(
            f"Missing required environment variable: {name}. "
            f"See .env.example for setup instructions."
        )
    return value


def _optional(name: str, default: str = "") -> str:
    return os.environ.get(name, default).strip()


@dataclass(frozen=True)
class Config:
    printify_token: str
    printify_shop_id: str
    etsy_api_key: str
    etsy_shared_secret: str
    etsy_shop_id: str
    etsy_refresh_token: str
    anthropic_api_key: str
    gh_pat_for_secrets: str
    github_repository: str

    @classmethod
    def load(cls, require_all: bool = True) -> "Config":
        # Only the Anthropic key is truly required -- the orchestrator has its
        # own graceful skip-logic for Printify and Etsy when they're not
        # configured (e.g. Etsy isn't set up yet for a brand-new shop), so
        # Config must not preempt that by hard-failing on their absence.
        anthropic_getter = _require if require_all else _optional
        return cls(
            printify_token=_optional("PRINTIFY_TOKEN"),
            printify_shop_id=_optional("PRINTIFY_SHOP_ID"),
            etsy_api_key=_optional("ETSY_API_KEY"),
            etsy_shared_secret=_optional("ETSY_SHARED_SECRET"),
            etsy_shop_id=_optional("ETSY_SHOP_ID"),
            etsy_refresh_token=_optional("ETSY_REFRESH_TOKEN"),
            anthropic_api_key=anthropic_getter("ANTHROPIC_API_KEY"),
            gh_pat_for_secrets=_optional("GH_PAT_FOR_SECRETS"),
            github_repository=_optional("GITHUB_REPOSITORY", "amyroday/Tee-Shirt-Designs"),
        )

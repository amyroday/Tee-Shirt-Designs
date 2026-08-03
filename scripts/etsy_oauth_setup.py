"""One-time interactive helper to obtain an Etsy refresh token.

Run this locally: `python scripts/etsy_oauth_setup.py`

You will need ETSY_API_KEY and ETSY_SHARED_SECRET already in your .env
(from your app's page at https://www.etsy.com/developers/your-apps).

This script never sees your Etsy password -- it prints a URL, YOU log in
and approve access in your own browser, then paste the resulting URL back
here so the script can exchange the authorization code for tokens.
"""

from __future__ import annotations

import base64
import hashlib
import os
import secrets
import sys
from urllib.parse import parse_qs, urlencode, urlparse

import requests
from dotenv import load_dotenv

load_dotenv()

AUTH_URL = "https://www.etsy.com/oauth/connect"
TOKEN_URL = "https://api.etsy.com/v3/public/oauth/token"

# Must exactly match a redirect URI registered on your Etsy app. It does not
# need to actually be a live server -- we only read the `code` out of the
# address bar after Etsy redirects there, even if the page fails to load.
REDIRECT_URI = os.environ.get("ETSY_REDIRECT_URI", "https://localhost:3003/oauth/redirect")

SCOPES = "transactions_r listings_r shops_r"


def make_pkce_pair() -> tuple[str, str]:
    verifier = base64.urlsafe_b64encode(secrets.token_bytes(64)).rstrip(b"=").decode("ascii")
    challenge = (
        base64.urlsafe_b64encode(hashlib.sha256(verifier.encode("ascii")).digest())
        .rstrip(b"=")
        .decode("ascii")
    )
    return verifier, challenge


def main() -> None:
    client_id = os.environ.get("ETSY_API_KEY", "").strip()
    if not client_id:
        print("Set ETSY_API_KEY in your .env first (your app's Keystring).", file=sys.stderr)
        sys.exit(1)

    state = secrets.token_urlsafe(16)
    code_verifier, code_challenge = make_pkce_pair()

    params = {
        "response_type": "code",
        "client_id": client_id,
        "redirect_uri": REDIRECT_URI,
        "scope": SCOPES,
        "state": state,
        "code_challenge": code_challenge,
        "code_challenge_method": "S256",
    }
    auth_url = f"{AUTH_URL}?{urlencode(params)}"

    print("1. Open this URL in your browser and log in / approve access with YOUR Etsy account:\n")
    print(f"   {auth_url}\n")
    print("2. Etsy will redirect you to a URL starting with:")
    print(f"   {REDIRECT_URI}?code=...&state=...")
    print("   (the page itself may fail to load -- that's fine, just copy the full URL from the address bar)\n")

    redirected_url = input("3. Paste the full redirected URL here: ").strip()

    parsed = urlparse(redirected_url)
    qs = parse_qs(parsed.query)

    if qs.get("state", [None])[0] != state:
        print("State mismatch -- the pasted URL doesn't match this session. Aborting.", file=sys.stderr)
        sys.exit(1)

    code = qs.get("code", [None])[0]
    if not code:
        print("No `code` parameter found in that URL.", file=sys.stderr)
        sys.exit(1)

    resp = requests.post(
        TOKEN_URL,
        data={
            "grant_type": "authorization_code",
            "client_id": client_id,
            "redirect_uri": REDIRECT_URI,
            "code": code,
            "code_verifier": code_verifier,
        },
        timeout=30,
    )
    resp.raise_for_status()
    tokens = resp.json()

    print("\nSuccess. Store these as GitHub repo secrets (Settings -> Secrets and variables -> Actions):\n")
    print(f"  ETSY_REFRESH_TOKEN = {tokens['refresh_token']}")
    print("\n(Access token is short-lived and not needed -- the pipeline derives it from the refresh token each run.)")


if __name__ == "__main__":
    main()

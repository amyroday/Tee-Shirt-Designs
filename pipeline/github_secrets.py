"""Updates a GitHub Actions repo secret via the REST API.

Etsy rotates its refresh token on every use, so the pipeline needs to write
the new token back into the repo's secrets after each run or next week's
run will fail with an invalid refresh token. Requires a PAT with this repo's
"Secrets: write" permission (GH_PAT_FOR_SECRETS) -- separate from the
default GITHUB_TOKEN, which cannot manage secrets.
"""

from __future__ import annotations

import base64

import requests
from nacl import encoding, public


def update_secret(repo: str, secret_name: str, secret_value: str, pat: str) -> None:
    if not pat:
        return  # No PAT configured (e.g. local dry run) -- nothing to do.

    headers = {
        "Authorization": f"Bearer {pat}",
        "Accept": "application/vnd.github+json",
    }

    key_resp = requests.get(
        f"https://api.github.com/repos/{repo}/actions/secrets/public-key",
        headers=headers,
        timeout=30,
    )
    key_resp.raise_for_status()
    key_data = key_resp.json()

    public_key = public.PublicKey(key_data["key"].encode("utf-8"), encoding.Base64Encoder())
    sealed_box = public.SealedBox(public_key)
    encrypted = sealed_box.encrypt(secret_value.encode("utf-8"))
    encrypted_b64 = base64.b64encode(encrypted).decode("utf-8")

    put_resp = requests.put(
        f"https://api.github.com/repos/{repo}/actions/secrets/{secret_name}",
        headers=headers,
        json={"encrypted_value": encrypted_b64, "key_id": key_data["key_id"]},
        timeout=30,
    )
    put_resp.raise_for_status()

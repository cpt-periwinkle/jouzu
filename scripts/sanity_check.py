"""
Milestone 0 sanity check.

Verifies that both API keys are present in .env and functional.
Run once before starting Milestone 1:

    python scripts/sanity_check.py
"""

import os
import sys

import anthropic
from anthropic.types import TextBlock
import httpx
from dotenv import load_dotenv

load_dotenv()


def check_anthropic() -> None:
    """Confirm the Anthropic API key loads and can reach the API."""
    key = os.environ.get("ANTHROPIC_API_KEY")
    if not key:
        print("FAIL  ANTHROPIC_API_KEY not found in .env")
        sys.exit(1)

    client = anthropic.Anthropic(api_key=key)
    response = client.messages.create(
        model="claude-sonnet-4-6",
        max_tokens=16,
        messages=[{"role": "user", "content": "Reply with the word OK only."}],
    )
    block = response.content[0]
    reply = block.text.strip() if isinstance(block, TextBlock) else repr(block)
    print(f"PASS  Anthropic API key works. Model replied: {reply!r}")


def check_wanikani() -> None:
    """Confirm the WaniKani API token loads and can reach the API."""
    token = os.environ.get("WANIKANI_API_TOKEN")
    if not token:
        print("FAIL  WANIKANI_API_TOKEN not found in .env")
        sys.exit(1)

    response = httpx.get(
        "https://api.wanikani.com/v2/user",
        headers={
            "Authorization": f"Bearer {token}",
            "Wanikani-Revision": "20170710",
        },
    )
    response.raise_for_status()
    username = response.json()["data"]["username"]
    level = response.json()["data"]["level"]
    print(f"PASS  WaniKani token works. User: {username!r}, Level: {level}")


if __name__ == "__main__":
    print("Running Milestone 0 sanity checks...\n")
    check_anthropic()
    check_wanikani()
    print("\nAll checks passed. Milestone 0 complete.")

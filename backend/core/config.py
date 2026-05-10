"""
Application configuration.

Single source of truth for all external service URLs, credentials, and
version strings. Change a model, API version, or base URL here -- nowhere else.

Environment variables are loaded from .env on startup.
"""

import os

from dotenv import load_dotenv

load_dotenv()

# ---------------------------------------------------------------------------
# Credentials (from .env)
# ---------------------------------------------------------------------------

ANTHROPIC_API_KEY: str = os.environ.get("ANTHROPIC_API_KEY", "")
WANIKANI_API_TOKEN: str = os.environ.get("WANIKANI_API_TOKEN", "")

if not ANTHROPIC_API_KEY:
    raise RuntimeError("ANTHROPIC_API_KEY is not set. Check your .env file.")

# ---------------------------------------------------------------------------
# Anthropic
# ---------------------------------------------------------------------------

ANTHROPIC_MODEL: str = "claude-sonnet-4-6"

# ---------------------------------------------------------------------------
# WaniKani
# ---------------------------------------------------------------------------

WANIKANI_BASE_URL: str = "https://api.wanikani.com/v2"
WANIKANI_REVISION: str = "20170710"

# ---------------------------------------------------------------------------
# Queue
# ---------------------------------------------------------------------------

DEFAULT_QUEUE_MODE: str = "shuffle"
DEFAULT_BATCH_SIZE: int = 10

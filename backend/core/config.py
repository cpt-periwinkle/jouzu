"""
Application configuration.

Loads environment variables from .env once at startup.
All other modules import settings from here instead of calling os.environ directly.
"""

import os

from dotenv import load_dotenv

load_dotenv()

ANTHROPIC_API_KEY: str = os.environ.get("ANTHROPIC_API_KEY", "")
WANIKANI_API_TOKEN: str = os.environ.get("WANIKANI_API_TOKEN", "")

if not ANTHROPIC_API_KEY:
    raise RuntimeError("ANTHROPIC_API_KEY is not set. Check your .env file.")

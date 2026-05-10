"""
WaniKani API client.

Fetches vocabulary and kanji subjects for a user's current level and converts
them into QuizItems. Results are cached via CacheProvider so WaniKani is only
called once per token per server session -- not on every quiz round.

All functions that make network calls raise httpx.HTTPStatusError on
non-2xx responses. Callers are responsible for handling those errors.

FUTURE SCOPE: When write operations are added (submitting reviews, starting
assignments, managing the lesson queue), convert this file into a package:

    backend/services/wanikani/
        __init__.py
        subjects.py     -- fetch vocab and kanji (this file's current content)
        assignments.py  -- fetch review queue, start lessons
        reviews.py      -- submit review results back to WaniKani
        user.py         -- fetch user level and subscription info
"""

import re

import httpx

from backend.core.cache import CacheProvider, InMemoryCache
from backend.core.config import WANIKANI_BASE_URL, WANIKANI_REVISION
from backend.models.quiz import QuizItem


# Active cache implementation. To swap storage backends, write a class that
# satisfies CacheProvider and replace InMemoryCache here. Nothing else changes.
_subject_cache: CacheProvider[list[QuizItem]] = InMemoryCache()


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _strip_markup(text: str | None) -> str | None:
    """
    Strip WaniKani's custom markup tags from mnemonic text.

    WaniKani mnemonics contain tags like <radical>ground</radical>,
    <kanji>One</kanji>, <reading>itchy</reading> etc. These are rendered
    as colored highlights on wanikani.com but are meaningless as raw strings.
    This strips the tags and keeps only the inner text.
    """
    if text is None:
        return None
    return re.sub(r"<[^>]+>", "", text)


def _headers(token: str) -> dict[str, str]:
    """Build the auth and revision headers required by the WaniKani API."""
    return {
        "Authorization": f"Bearer {token}",
        "Wanikani-Revision": WANIKANI_REVISION,
    }


def _has_kanji(text: str) -> bool:
    """
    Return True if the string contains at least one CJK kanji character.

    Checks the main CJK Unified Ideographs block (U+4E00 to U+9FFF), which
    covers the vast majority of kanji used in WaniKani vocabulary.

    Kana-only vocabulary (e.g. おやつ) returns False and is excluded from
    the quiz -- guessing a hiragana reading for a kana-only word makes no sense.
    """
    return any("一" <= ch <= "鿿" for ch in text)


# ---------------------------------------------------------------------------
# WaniKani API calls
# ---------------------------------------------------------------------------

def get_user_level(token: str) -> int:
    """
    Fetch the user's current WaniKani level.

    Args:
        token: The user's WaniKani personal access token.

    Returns:
        The user's current level as an integer (1-60).

    Raises:
        httpx.HTTPStatusError: If the token is invalid or the request fails.
    """
    response = httpx.get(
        f"{WANIKANI_BASE_URL}/user", headers=_headers(token), timeout=10
    )
    response.raise_for_status()
    return response.json()["data"]["level"]


def _fetch_subjects(token: str, level: int) -> list[QuizItem]:
    """
    Fetch all vocabulary and kanji subjects at the given level from WaniKani.

    Follows pagination via pages.next_url until the full list is retrieved.
    Filters out hidden subjects and kana-only vocabulary (no kanji characters).

    Vocabulary subjects: uses the primary reading as the single accepted reading.
    Kanji subjects: collects all readings where accepted_answer is True, since
    WaniKani accepts multiple readings (e.g. both on'yomi and kun'yomi) for kanji.
    The primary reading is stored as the display reading shown in the result banner.

    Args:
        token: The user's WaniKani personal access token.
        level: The WaniKani level to fetch subjects for.

    Returns:
        A list of QuizItems built from the filtered subjects.
    """
    items: list[QuizItem] = []
    url: str | None = (
        f"{WANIKANI_BASE_URL}/subjects?types=vocabulary,kanji&levels={level}"
    )

    while url:
        response = httpx.get(url, headers=_headers(token), timeout=15)
        response.raise_for_status()
        payload = response.json()

        for subject in payload["data"]:
            subject_type: str = subject["object"]
            data = subject["data"]

            if data.get("hidden_at"):
                continue

            characters: str = data.get("characters", "")

            if not _has_kanji(characters):
                continue

            readings = data.get("readings", [])

            primary_reading = next(
                (r["reading"] for r in readings if r.get("primary")), None
            )
            if not primary_reading:
                continue

            accepted_readings = [
                r["reading"] for r in readings if r.get("accepted_answer")
            ]
            if not accepted_readings:
                accepted_readings = [primary_reading]

            meanings = data.get("meanings", [])
            primary_meaning = next(
                (m["meaning"] for m in meanings if m.get("primary")), None
            )
            if not primary_meaning:
                continue

            items.append(
                QuizItem(
                    characters=characters,
                    reading=primary_reading,
                    accepted_readings=accepted_readings,
                    meaning=primary_meaning,
                    subject_type=subject_type,
                    reading_mnemonic=_strip_markup(data.get("reading_mnemonic")),
                    meaning_mnemonic=_strip_markup(data.get("meaning_mnemonic")),
                )
            )

        url = payload["pages"].get("next_url")

    return items


# ---------------------------------------------------------------------------
# Public interface
# ---------------------------------------------------------------------------

def get_items_for_token(token: str) -> list[QuizItem]:
    """
    Return quiz items for the given WaniKani token, using the cache if available.

    On the first call for a token, fetches the user's level then fetches
    subjects for that level and caches the result. Returns an empty list if
    anything fails -- the caller should fall back to the hardcoded list.

    Args:
        token: The user's WaniKani personal access token.

    Returns:
        A list of QuizItems from WaniKani, or an empty list on failure.
    """
    if _subject_cache.contains(token):
        return _subject_cache.get(token) or []

    try:
        level = get_user_level(token)
        items = _fetch_subjects(token, level)
        _subject_cache.set(token, items)
    except Exception:
        _subject_cache.set(token, [])

    return _subject_cache.get(token) or []


def get_character_list(token: str) -> list[str]:
    """
    Return just the characters from the cached item list for a token.

    Used to pass a compact vocabulary list to Claude so it can suggest
    related compounds the student actually knows, without passing full
    QuizItem objects which would be too many tokens.

    Returns an empty list if the token hasn't been fetched yet or failed.
    """
    items = _subject_cache.get(token)
    return [item.characters for item in items] if items else []

"""
WaniKani API client.

Fetches vocabulary and kanji subjects for a user's current level and converts
them into QuizItems. Also fetches lifetime review statistics per subject so the
frontend can show WaniKani accuracy alongside session stats.

Results are cached via CacheProvider so WaniKani is only called once per token
per server session -- not on every quiz round.

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
from backend.models.quiz import QuizItem, ReviewStats


# Active cache implementations. To swap storage backends, write a class that
# satisfies CacheProvider and replace InMemoryCache here. Nothing else changes.
_subject_cache: CacheProvider[list[QuizItem]] = InMemoryCache()
_review_stats_cache: CacheProvider[dict[int, ReviewStats]] = InMemoryCache()


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
            subject_id: int = subject["id"]
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
                    subject_id=subject_id,
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


def _fetch_review_stats(
    token: str, subject_ids: list[int]
) -> dict[int, ReviewStats]:
    """
    Fetch lifetime review statistics for the given subject IDs from WaniKani.

    Only subjects the user has already reviewed will appear in the response --
    unreviewed subjects are simply absent from the returned dict.

    Args:
        token: The user's WaniKani personal access token.
        subject_ids: The WaniKani subject IDs to fetch stats for.

    Returns:
        A dict mapping subject_id to ReviewStats.
    """
    if not subject_ids:
        return {}

    stats: dict[int, ReviewStats] = {}
    ids_str = ",".join(str(i) for i in subject_ids)
    url: str | None = (
        f"{WANIKANI_BASE_URL}/review_statistics?subject_ids={ids_str}"
    )

    while url:
        response = httpx.get(url, headers=_headers(token), timeout=15)
        response.raise_for_status()
        payload = response.json()

        for entry in payload["data"]:
            data = entry["data"]
            stats[data["subject_id"]] = ReviewStats(
                meaning_correct=data["meaning_correct"],
                meaning_incorrect=data["meaning_incorrect"],
                reading_correct=data["reading_correct"],
                reading_incorrect=data["reading_incorrect"],
                percentage_correct=data["percentage_correct"],
                meaning_current_streak=data["meaning_current_streak"],
                reading_current_streak=data["reading_current_streak"],
            )

        url = payload["pages"].get("next_url")

    return stats


# ---------------------------------------------------------------------------
# Public interface
# ---------------------------------------------------------------------------

def get_items_for_token(token: str) -> list[QuizItem]:
    """
    Return quiz items for the given WaniKani token, using the cache if available.

    On the first call for a token:
      1. Fetches the user's current level
      2. Fetches subjects (vocabulary + kanji) for that level
      3. Fetches lifetime review stats for those subjects
      4. Embeds review stats into each QuizItem
      5. Caches the result

    Returns an empty list if anything fails -- the caller falls back to
    the hardcoded list.

    Args:
        token: The user's WaniKani personal access token.

    Returns:
        A list of QuizItems with review stats embedded, or empty on failure.
    """
    if _subject_cache.contains(token):
        return _subject_cache.get(token) or []

    try:
        level = get_user_level(token)
        items = _fetch_subjects(token, level)

        subject_ids = [
            item.subject_id for item in items if item.subject_id is not None
        ]
        review_stats = _fetch_review_stats(token, subject_ids)

        # Embed review stats into each item using model_copy so Pydantic
        # immutability is respected -- creates a new instance with the field updated.
        items = [
            item.model_copy(
                update={"review_stats": review_stats.get(item.subject_id)}
            )
            for item in items
        ]

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

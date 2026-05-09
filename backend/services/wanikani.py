"""
WaniKani API client.

Fetches vocabulary subjects for a user's current level and converts them
into QuizItems. Results are cached in memory by token so WaniKani is only
called once per token per server session -- not on every quiz round.

All functions that make network calls raise httpx.HTTPStatusError on
non-2xx responses. Callers are responsible for handling those errors.
"""

import httpx

from backend.core.config import WANIKANI_BASE_URL, WANIKANI_REVISION
from backend.models.quiz import QuizItem


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
    # Fetch both vocabulary and kanji -- radicals have no readings so they're excluded.
    url: str | None = (
        f"{WANIKANI_BASE_URL}/subjects?types=vocabulary,kanji&levels={level}"
    )

    while url:
        response = httpx.get(url, headers=_headers(token), timeout=15)
        response.raise_for_status()
        payload = response.json()

        for subject in payload["data"]:
            subject_type: str = subject["object"]  # "vocabulary" or "kanji"
            data = subject["data"]

            # Skip subjects hidden on WaniKani.
            if data.get("hidden_at"):
                continue

            characters: str = data.get("characters", "")

            # Skip kana-only items -- no kanji reading to guess.
            if not _has_kanji(characters):
                continue

            readings = data.get("readings", [])

            # Primary reading is displayed in the result banner after submission.
            primary_reading = next(
                (r["reading"] for r in readings if r.get("primary")), None
            )
            if not primary_reading:
                continue

            # Accepted readings are all readings WaniKani marks as correct.
            # Vocabulary typically has one; kanji can have several (on'yomi, kun'yomi).
            accepted_readings = [
                r["reading"] for r in readings if r.get("accepted_answer")
            ]
            if not accepted_readings:
                accepted_readings = [primary_reading]

            # Primary meaning is the main English definition.
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
                )
            )

        # Follow pagination until next_url is null.
        url = payload["pages"].get("next_url")

    return items


# In-memory cache keyed by token. Persists for the lifetime of the server
# process so WaniKani is not called on every quiz round.
# Cache is cleared on server restart and repopulated on first request.
_cache: dict[str, list[QuizItem]] = {}


def get_items_for_token(token: str) -> list[QuizItem]:
    """
    Return quiz items for the given WaniKani token, using the cache if available.

    On the first call for a token, fetches the user's level then fetches
    vocabulary subjects for that level. Caches the result. Returns an empty
    list if anything fails -- the caller should fall back to the hardcoded list.

    Args:
        token: The user's WaniKani personal access token.

    Returns:
        A list of QuizItems from WaniKani, or an empty list on failure.
    """
    if token in _cache:
        return _cache[token]

    try:
        level = get_user_level(token)
        items = _fetch_subjects(token, level)
        _cache[token] = items
    except Exception:
        # Any network or auth failure falls back silently to the hardcoded list.
        _cache[token] = []

    return _cache[token]

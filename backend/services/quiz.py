"""
Quiz service.

Routes item requests to the correct source (WaniKani current level, WaniKani
all reviewed, N4 fallback CSV, or custom uploaded CSV) and owns guess-evaluation
logic. The rest of the app calls get_quiz_items() without caring where the
data comes from.
"""

from pathlib import Path

import pykakasi

from backend.core.cache import CacheProvider, InMemoryCache
from backend.models.quiz import QuizItem
from backend.services.csv_loader import load_csv

# ---------------------------------------------------------------------------
# Fallback deck
#
# Loaded once on module import from the shipped CSV. Fails loudly if the file
# is missing -- this is a configuration error, not a runtime condition.
# ---------------------------------------------------------------------------

_FALLBACK_CSV = Path(__file__).parent.parent.parent / "data" / "n4_fallback.csv"

try:
    _FALLBACK_ITEMS: list[QuizItem] = load_csv(_FALLBACK_CSV)
except Exception as exc:
    raise RuntimeError(
        f"Failed to load N4 fallback CSV from {_FALLBACK_CSV}: {exc}"
    ) from exc


# ---------------------------------------------------------------------------
# Custom upload cache
#
# Keyed by session_id (UUID) returned to the frontend after upload.
# Uses the same CacheProvider abstraction as the WaniKani subject cache.
# ---------------------------------------------------------------------------

_custom_cache: CacheProvider[list[QuizItem]] = InMemoryCache()


def store_custom_items(session_id: str, items: list[QuizItem]) -> None:
    """Store a parsed custom deck under the given session ID."""
    _custom_cache.set(session_id, items)


def get_custom_items(session_id: str) -> list[QuizItem]:
    """Return the custom deck for the given session ID, or empty list if not found."""
    return _custom_cache.get(session_id) or []


# ---------------------------------------------------------------------------
# pykakasi (initialized once for reuse across all conversion calls)
# ---------------------------------------------------------------------------

_kakasi = pykakasi.kakasi()


# ---------------------------------------------------------------------------
# Public interface
# ---------------------------------------------------------------------------

def get_quiz_items(
    token: str | None = None,
    source: str = "fallback",
    session_id: str | None = None,
) -> list[QuizItem]:
    """
    Return the list of compounds for the current quiz session.

    Routes to the correct source based on the source parameter:
      current_level -- WaniKani vocabulary and kanji at the user's current level
      all_reviewed  -- all WaniKani subjects the user has passed to Guru or above
      fallback      -- shipped N4 fallback CSV, always available, no token needed
      custom        -- user-uploaded CSV, identified by session_id

    Falls back to the N4 fallback CSV if the requested source is unavailable
    (missing token, empty result, missing session_id, etc.).

    Args:
        token: WaniKani personal access token. Required for WaniKani sources.
        source: One of 'current_level', 'all_reviewed', 'fallback', 'custom'.
        session_id: UUID identifying a custom uploaded deck. Required for 'custom'.

    Returns:
        A list of QuizItems from the selected source, or the fallback list.
    """
    if source == "current_level" and token:
        from backend.services.wanikani import get_items_for_token
        items = get_items_for_token(token)
        return items if items else _FALLBACK_ITEMS

    if source == "all_reviewed" and token:
        from backend.services.wanikani import get_all_reviewed_subjects
        items = get_all_reviewed_subjects(token)
        return items if items else _FALLBACK_ITEMS

    if source == "custom" and session_id:
        items = get_custom_items(session_id)
        return items if items else _FALLBACK_ITEMS

    return _FALLBACK_ITEMS


# ---------------------------------------------------------------------------
# Guess evaluation
# ---------------------------------------------------------------------------

def _hiragana_to_romaji(text: str) -> str:
    """
    Convert a hiragana string to Hepburn romaji using pykakasi.

    _kakasi.convert("でんしゃ") returns a list of dicts, one per sound unit (mora).
    pykakasi keeps combined kana like しゃ together as one unit, so the output is:

        [{"orig": "で", "hepburn": "de"},
         {"orig": "ん", "hepburn": "n"},
         {"orig": "しゃ", "hepburn": "sha"}]

    "".join(...) loops through each dict, pulls the "hepburn" value, and concatenates
    with no separator: "de" + "n" + "sha" = "densha". .lower() normalizes case.
    """
    result = _kakasi.convert(text)
    return "".join(item["hepburn"] for item in result).lower()


def _contains_hiragana(text: str) -> bool:
    """
    Return True if the string contains at least one hiragana character.

    Unicode assigns every character a number. All hiragana sit in a consecutive
    block from ぁ (U+3041) to ゖ (U+3096). Checking "ぁ" <= ch <= "ゖ" asks
    whether the character's number falls inside that range -- the same way you'd
    check "a" <= ch <= "z" for lowercase English letters.

    any() returns True the moment it finds one matching character, without checking
    the rest of the string.
    """
    return any("ぁ" <= ch <= "ゖ" for ch in text)


def _edit_distance(a: str, b: str) -> int:
    """
    Compute the Levenshtein edit distance between two strings.

    Edit distance counts the minimum number of single-character insertions,
    deletions, or substitutions needed to turn string a into string b.
    Examples:
      "densha" vs "densa"  -> 1 (one deletion)
      "densha" vs "tokyo"  -> 5 (five substitutions/insertions)

    Uses a memory-efficient single-row dynamic programming approach.
    """
    m, n = len(a), len(b)
    dp = list(range(n + 1))
    for i in range(1, m + 1):
        prev = dp[0]
        dp[0] = i
        for j in range(1, n + 1):
            temp = dp[j]
            dp[j] = prev if a[i - 1] == b[j - 1] else 1 + min(prev, dp[j], dp[j - 1])
            prev = temp
    return dp[n]


def measure_closeness(guess: str, accepted_readings: list[str]) -> str:
    """
    Return how close the user's guess was to the best matching accepted reading.

    Checks against all accepted readings and uses the closest match.
    This matters for kanji subjects which have multiple accepted readings
    (e.g. 一 accepts いち and ひと).

    Both inputs are normalized to romaji before comparison so hiragana
    and romaji guesses are treated identically.

    Returns one of four levels based on edit distance:
      "correct"    -- exact match against any accepted reading
      "very_close" -- 1 character off from the closest reading
      "close"      -- 2-3 characters off
      "off"        -- more than 3 characters off

    Args:
        guess: What the user typed (hiragana or romaji).
        accepted_readings: All readings WaniKani accepts as correct.

    Returns:
        A closeness level string used by the prompt and frontend.
    """
    guess = guess.strip().lower()
    guess_romaji = _hiragana_to_romaji(guess) if _contains_hiragana(guess) else guess
    guess_romaji = guess_romaji.replace(" ", "")

    best_distance = min(
        _edit_distance(
            guess_romaji,
            _hiragana_to_romaji(r).replace(" ", "")
        )
        for r in accepted_readings
    )

    if best_distance == 0:
        return "correct"
    elif best_distance == 1:
        return "very_close"
    elif best_distance <= 3:
        return "close"
    else:
        return "off"


def check_guess(guess: str, accepted_readings: list[str]) -> bool:
    """
    Compare the user's guess against all accepted readings.

    Accepts both hiragana and romaji so users without a Japanese IME are not blocked.
    Returns True if the guess matches any accepted reading -- important for kanji
    subjects where multiple readings are correct (e.g. on'yomi and kun'yomi).

    .strip() removes accidental leading/trailing whitespace.
    .lower() normalizes case so "Densha" matches "densha".

    Args:
        guess: What the user typed (hiragana or romaji).
        accepted_readings: All readings WaniKani accepts as correct.

    Returns:
        True if the guess matches any accepted reading.
    """
    guess = guess.strip().lower()

    for reading in accepted_readings:
        if _contains_hiragana(guess):
            if guess == reading:
                return True
        else:
            correct_romaji = _hiragana_to_romaji(reading).replace(" ", "")
            if guess.replace(" ", "") == correct_romaji:
                return True

    return False

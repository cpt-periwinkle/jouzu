"""
Quiz service.

Owns the compound data and guess-evaluation logic.
The rest of the app calls get_quiz_items() without caring where the data
comes from -- this is the only file that changes when WaniKani is added.
"""

import pykakasi

# QuizItem is the Pydantic model from models/quiz.py that defines the shape
# each compound must match: characters (kanji), reading (hiragana), meaning (English).
from backend.models.quiz import QuizItem


# pykakasi is initialized once when Python first imports this file, not on every
# function call. Initialization is slow; calling .convert() on an existing instance
# is fast.
_kakasi = pykakasi.kakasi()


# 20 N4-level compounds covering the four main reading patterns:
#
#   on+on  : both kanji use on'yomi (Chinese-derived reading).
#            Most compound nouns follow this pattern, e.g. 電車 (でんしゃ).
#   kun+kun: both kanji use kun'yomi (native Japanese reading), e.g. 手紙 (てがみ).
#   on+kun : first kanji on'yomi, second kun'yomi. Called 湯桶読み (yutou-yomi).
#   kun+on : first kanji kun'yomi, second on'yomi. Called 重箱読み (juubako-yomi).
#   irreg  : irregular reading that does not follow any standard pattern.

_HARDCODED_ITEMS: list[QuizItem] = [
    # on + on
    QuizItem(characters="電車", reading="でんしゃ", meaning="train"),
    QuizItem(characters="学生", reading="がくせい", meaning="student"),
    QuizItem(characters="食堂", reading="しょくどう", meaning="cafeteria"),
    QuizItem(characters="旅行", reading="りょこう", meaning="travel"),
    QuizItem(characters="音楽", reading="おんがく", meaning="music"),
    QuizItem(characters="病院", reading="びょういん", meaning="hospital"),
    QuizItem(characters="図書館", reading="としょかん", meaning="library"),
    QuizItem(characters="電話", reading="でんわ", meaning="telephone"),
    # kun + kun
    QuizItem(characters="手紙", reading="てがみ", meaning="letter"),
    QuizItem(characters="花火", reading="はなび", meaning="fireworks"),
    QuizItem(characters="夕方", reading="ゆうがた", meaning="evening"),
    QuizItem(characters="山道", reading="やまみち", meaning="mountain path"),
    # on + kun  (yutou-yomi)
    QuizItem(characters="台所", reading="だいどころ", meaning="kitchen"),
    QuizItem(characters="気持ち", reading="きもち", meaning="feeling"),
    # kun + on  (juubako-yomi)
    QuizItem(characters="場所", reading="ばしょ", meaning="place"),
    QuizItem(characters="合図", reading="あいず", meaning="signal"),
    # irregular
    QuizItem(characters="今日", reading="きょう", meaning="today"),
    QuizItem(characters="昨日", reading="きのう", meaning="yesterday"),
    QuizItem(characters="大人", reading="おとな", meaning="adult"),
    QuizItem(characters="二人", reading="ふたり", meaning="two people"),
]


def get_quiz_items(token: str | None = None) -> list[QuizItem]:
    """
    Return the list of compounds available for the current quiz session.

    If a WaniKani token is provided, fetches the user's current level vocabulary
    from WaniKani and returns that. Falls back to the hardcoded N4 list if no
    token is given, the token is invalid, or the WaniKani call returns nothing.

    Args:
        token: Optional WaniKani personal access token.

    Returns:
        A list of QuizItems from WaniKani, or the hardcoded N4 fallback.
    """
    if token:
        from backend.services.wanikani import get_items_for_token
        items = get_items_for_token(token)
        if items:
            return items
    return _HARDCODED_ITEMS


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


def measure_closeness(guess: str, correct_reading: str) -> str:
    """
    Return how close the user's guess was to the correct reading.

    Both inputs are normalized to romaji before comparison so hiragana
    and romaji guesses are treated identically.

    Returns one of four levels based on edit distance:
      "correct"    -- exact match
      "very_close" -- 1 character off (e.g. typed 'densa' instead of 'densha')
      "close"      -- 2-3 characters off
      "off"        -- more than 3 characters off

    Args:
        guess: What the user typed (hiragana or romaji).
        correct_reading: The correct hiragana reading.

    Returns:
        A closeness level string used by the prompt and frontend.
    """
    guess = guess.strip().lower()
    guess_romaji = _hiragana_to_romaji(guess) if _contains_hiragana(guess) else guess
    correct_romaji = _hiragana_to_romaji(correct_reading)

    guess_romaji = guess_romaji.replace(" ", "")
    correct_romaji = correct_romaji.replace(" ", "")

    distance = _edit_distance(guess_romaji, correct_romaji)

    if distance == 0:
        return "correct"
    elif distance == 1:
        return "very_close"
    elif distance <= 3:
        return "close"
    else:
        return "off"


def check_guess(guess: str, correct_reading: str) -> bool:
    """
    Compare the user's guess against the correct hiragana reading.

    Accepts both hiragana and romaji so users without a Japanese IME are not blocked.

    .strip() removes accidental leading/trailing whitespace.
    .lower() normalizes case so "Densha" matches "densha".

    If the guess contains hiragana, compare it directly against the correct reading.

    If no hiragana is found (romaji input), convert the correct reading to romaji
    using _hiragana_to_romaji(), strip spaces from both sides, and compare.
    The .replace(" ", "") handles pykakasi occasionally inserting a space between morae.

    Args:
        guess: What the user typed (hiragana or romaji).
        correct_reading: The correct hiragana reading from the compound data.

    Returns:
        True if the guess matches the correct reading.
    """
    guess = guess.strip().lower()

    if _contains_hiragana(guess):
        return guess == correct_reading

    correct_romaji = _hiragana_to_romaji(correct_reading).replace(" ", "")
    return guess.replace(" ", "") == correct_romaji

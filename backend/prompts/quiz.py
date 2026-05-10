"""
LLM prompt builders for the quiz domain.

Each function assembles the dynamic sections of a prompt (conditional lines,
flavor messages, vocabulary lists) and injects them into the templates defined
in templates.py via .format(). The static structure lives there; the logic lives here.
"""

import random

from backend.prompts.templates import EXPLAIN_TEMPLATE, HINT_TEMPLATE

# Flavor lines passed to Claude as result context.
# Claude uses the tone of these to naturally vary its response.
_CORRECT_FLAVOR = [
    "正解! That's the one.",
    "そうそう! You read that perfectly.",
    "完璧. Exactly right.",
    "Yes -- 上手い! Pattern recognition is working.",
    "Nailed it. 正解!",
]

_VERY_CLOSE_FLAVOR = [
    "惜しい! One sound off -- you were basically there.",
    "So close it hurts. One mora away from perfect.",
    "ほぼ正解! Just one slip between you and it.",
    "One character off. You had the right shape of it.",
]

_CLOSE_FLAVOR = [
    "Getting warmer. You had the right instinct but lost it partway.",
    "Not far off -- the pattern is there, the execution slipped.",
    "Almost. Worth reading the breakdown carefully.",
    "You're in the right ballpark. The details are below.",
]

_OFF_FLAVOR = [
    "That one needs some work. Let's look at the pattern.",
    "Not quite -- but the explanation below is the important part.",
    "Hmm. That reading doesn't match. Worth understanding why.",
    "That one got away. The breakdown below will help.",
]


def _pick_flavor(closeness: str, reading: str) -> str:
    """
    Select a flavor line based on closeness level.

    For incorrect answers, appends the correct reading so Claude always
    has it in context when writing the explanation.
    """
    if closeness == "correct":
        return random.choice(_CORRECT_FLAVOR)

    if closeness == "very_close":
        flavor = random.choice(_VERY_CLOSE_FLAVOR)
    elif closeness == "close":
        flavor = random.choice(_CLOSE_FLAVOR)
    else:
        flavor = random.choice(_OFF_FLAVOR)

    return f"{flavor} The correct reading is {reading}."


def build_explain_prompt(
    characters: str,
    reading: str,
    accepted_readings: list[str],
    guess: str,
    closeness: str,
    subject_type: str,
    reading_mnemonic: str | None = None,
    known_vocabulary: list[str] | None = None,
) -> str:
    """
    Build the explanation prompt by assembling dynamic sections and injecting
    them into EXPLAIN_TEMPLATE.

    Args:
        characters: The kanji compound shown to the user, e.g. '電車'.
        reading: The primary hiragana reading, e.g. 'でんしゃ'.
        accepted_readings: All readings WaniKani accepts as correct.
        guess: What the user typed (hiragana or romaji).
        closeness: One of 'correct', 'very_close', 'close', or 'off'.
        subject_type: 'vocabulary' or 'kanji'.
        reading_mnemonic: WaniKani's reading mnemonic, if available.
        known_vocabulary: List of kanji compounds the student knows, used to
            suggest relevant related compounds.

    Returns:
        A fully formatted prompt string ready to send to Claude.
    """
    result_line = _pick_flavor(closeness, reading)

    readings_line = (
        f"Accepted readings: {', '.join(accepted_readings)}"
        if len(accepted_readings) > 1
        else f"Correct reading: {reading}"
    )

    type_context = (
        "This is a kanji subject. WaniKani may accept multiple readings (on'yomi and/or kun'yomi). "
        "Reference the component radicals in your explanation where relevant -- "
        "they are part of WaniKani's mnemonic system and help the student remember the reading."
        if subject_type == "kanji"
        else "This is a vocabulary subject. It has one expected reading in context."
    )

    mnemonic_section = (
        f"\nWaniKani's reading mnemonic for this subject: {reading_mnemonic}"
        if reading_mnemonic
        else ""
    )

    # Pass up to 50 known compounds to keep token count reasonable.
    vocab_section = (
        f"\nThe student's known vocabulary includes: {', '.join(known_vocabulary[:50])}. "
        "When suggesting related compounds in section 3, prefer ones from this list "
        "over ones the student may not know yet."
        if known_vocabulary
        else ""
    )

    return EXPLAIN_TEMPLATE.format(
        characters=characters,
        readings_line=readings_line,
        guess=guess,
        result_line=result_line,
        type_context=type_context,
        mnemonic_section=mnemonic_section,
        vocab_section=vocab_section,
    )


def build_hint_prompt(
    characters: str,
    meaning: str,
    subject_type: str,
    reading_mnemonic: str | None = None,
) -> str:
    """
    Build a hint prompt by injecting dynamic sections into HINT_TEMPLATE.

    Args:
        characters: The kanji compound being quizzed.
        meaning: The English meaning.
        subject_type: 'vocabulary' or 'kanji'.
        reading_mnemonic: WaniKani's reading mnemonic. Claude can allude
            to it without quoting it directly.

    Returns:
        A fully formatted prompt string ready to send to Claude.
    """
    mnemonic_section = (
        f"\nWaniKani's reading mnemonic for this subject: {reading_mnemonic}"
        "\nYou may allude to the mnemonic to guide the student, but don't quote it directly."
        if reading_mnemonic
        else ""
    )

    return HINT_TEMPLATE.format(
        characters=characters,
        meaning=meaning,
        subject_type=subject_type,
        mnemonic_section=mnemonic_section,
    )

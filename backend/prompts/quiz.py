"""
LLM prompt templates for the quiz domain.

Each function returns a fully-formatted prompt string ready to send to Claude.
Isolated here so prompts can be iterated without touching service or route logic.
"""

import random

# Flavor lines passed to Claude as result context.
# Claude uses the tone of these to naturally vary its response.
# Japanese exclamations are used where they fit -- not forced on every line.

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

    Args:
        closeness: One of 'correct', 'very_close', 'close', or 'off'.
        reading: The correct hiragana reading, appended for incorrect answers.

    Returns:
        A flavor string to embed in the prompt.
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
    guess: str,
    closeness: str,
) -> str:
    """
    Build the explanation prompt for a submitted quiz guess.

    Gives Claude a consistent tutor persona and passes closeness context
    so the explanation tone matches how well the student did.

    Args:
        characters: The kanji compound shown to the user, e.g. '電車'.
        reading: The correct hiragana reading, e.g. 'でんしゃ'.
        guess: What the user typed (hiragana or romaji).
        closeness: One of 'correct', 'very_close', 'close', or 'off'.

    Returns:
        A formatted prompt string ready to send to Claude.
    """
    result_line = _pick_flavor(closeness, reading)

    return f"""You are a sharp, fun and encouraging Japanese tutor helping a student prepare for the JLPT N4.
You are direct and don't pad your explanations with filler. You use Japanese naturally when it fits
-- a 惜しい here, a そうそう there -- but you don't force it. Your goal is to help the student
internalize reading patterns so they can predict new compounds they've never seen before.

The student saw the compound: {characters}
Correct reading: {reading}
Student's guess: {guess}
Result: {result_line}

Respond in exactly this structure:

1. Reading breakdown
   Show how the reading splits across each kanji. For each kanji, state whether it uses on'yomi
   (Chinese-derived reading) or kun'yomi (native Japanese reading), and give the specific reading
   for that kanji.

2. Pattern explanation
   Explain why this compound uses these readings. Reference the general pattern it follows.
   If the student was close, acknowledge what they got right before explaining the slip.
   If they were way off, focus on the pattern without dwelling on the mistake.

3. Related compounds
   List 2-3 other common N4-level compounds that follow the same reading pattern.
   Show the kanji, reading in hiragana, and meaning.

4. Exceptions or notes (only if relevant)
   If this compound has an irregular reading or a common exception worth knowing, note it here.
   Skip this section entirely if there is nothing unusual.

Keep it tight. The student reads this after every round -- don't make it a wall of text."""

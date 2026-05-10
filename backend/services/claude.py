"""
Claude service.

The only file in the app that talks to the Anthropic SDK directly.
Everything else that needs an explanation or hint calls the functions here.
If the model changes or the API changes, this is the only file to update.
"""

import anthropic

from backend.core.config import ANTHROPIC_API_KEY, ANTHROPIC_MODEL
from backend.models.quiz import ExplainResponse, HintResponse
from backend.prompts.quiz import build_explain_prompt, build_hint_prompt
from backend.services.quiz import measure_closeness

# The Anthropic client is initialized once at module load with the API key.
# Creating it once and reusing it is more efficient than creating a new
# client on every request.
_client = anthropic.Anthropic(api_key=ANTHROPIC_API_KEY)


def _call_claude(prompt: str, max_tokens: int = 1024) -> str:
    """Send a prompt to Claude and return the text response."""
    message = _client.messages.create(
        model=ANTHROPIC_MODEL,
        max_tokens=max_tokens,
        messages=[{"role": "user", "content": prompt}],
    )
    block = message.content[0]
    return block.text if isinstance(block, anthropic.types.TextBlock) else ""


def get_explanation(
    characters: str,
    reading: str,
    accepted_readings: list[str],
    guess: str,
    subject_type: str,
    reading_mnemonic: str | None = None,
    wanikani_token: str | None = None,
) -> ExplainResponse:
    """
    Evaluate the user's guess and return a Claude-generated explanation.

    Pulls the user's known vocabulary list from the WaniKani cache (if a token
    is provided) so Claude can suggest related compounds the student actually knows.

    Args:
        characters: The kanji compound shown to the user, e.g. '電車'.
        reading: The primary hiragana reading shown in the result banner.
        accepted_readings: All readings WaniKani accepts as correct.
        guess: What the user typed (hiragana or romaji).
        subject_type: 'vocabulary' or 'kanji' -- shapes Claude's explanation.
        reading_mnemonic: WaniKani's reading mnemonic, passed to Claude for reference.
        wanikani_token: Optional token to pull the student's known vocabulary list.

    Returns:
        ExplainResponse with is_correct flag and Claude's explanation.
    """
    closeness = measure_closeness(guess, accepted_readings)
    is_correct = closeness == "correct"

    known_vocabulary: list[str] | None = None
    if wanikani_token:
        from backend.services.wanikani import get_character_list
        known_vocabulary = get_character_list(wanikani_token) or None

    prompt = build_explain_prompt(
        characters=characters,
        reading=reading,
        accepted_readings=accepted_readings,
        guess=guess,
        closeness=closeness,
        subject_type=subject_type,
        reading_mnemonic=reading_mnemonic,
        known_vocabulary=known_vocabulary,
    )

    explanation = _call_claude(prompt, max_tokens=1200)
    return ExplainResponse(is_correct=is_correct, closeness=closeness, explanation=explanation)


def get_hint(
    characters: str,
    meaning: str,
    subject_type: str,
    reading_mnemonic: str | None = None,
) -> HintResponse:
    """
    Generate a hint that nudges the student toward the reading without revealing it.

    Args:
        characters: The kanji compound being quizzed.
        meaning: The English meaning.
        subject_type: 'vocabulary' or 'kanji'.
        reading_mnemonic: WaniKani's reading mnemonic, used to guide the hint.

    Returns:
        HintResponse with a short nudge toward the correct reading pattern.
    """
    prompt = build_hint_prompt(
        characters=characters,
        meaning=meaning,
        subject_type=subject_type,
        reading_mnemonic=reading_mnemonic,
    )
    hint = _call_claude(prompt, max_tokens=150)
    return HintResponse(hint=hint)

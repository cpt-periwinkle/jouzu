"""
Pydantic models for the quiz domain.

These define the data contract between frontend and backend.
Any client (Streamlit today, React later) must conform to these shapes.
"""

from pydantic import BaseModel


class ReviewStats(BaseModel):
    """Lifetime review statistics for a subject, sourced from WaniKani."""

    meaning_correct: int
    """Total correct meaning answers across all reviews."""

    meaning_incorrect: int
    """Total incorrect meaning answers across all reviews."""

    reading_correct: int
    """Total correct reading answers across all reviews."""

    reading_incorrect: int
    """Total incorrect reading answers across all reviews."""

    percentage_correct: int
    """Overall correct answer rate (meaning + reading combined)."""

    meaning_current_streak: int
    """Current uninterrupted streak of correct meaning answers."""

    reading_current_streak: int
    """Current uninterrupted streak of correct reading answers."""


class QuizItem(BaseModel):
    """A single kanji compound presented to the user for reading practice."""

    subject_id: int | None = None
    """WaniKani subject ID. None for hardcoded fallback items."""

    characters: str
    """The kanji compound, e.g. '電車'."""

    reading: str
    """Correct hiragana reading, e.g. 'でんしゃ'."""

    accepted_readings: list[str]
    """All readings WaniKani accepts as correct. Kanji subjects have several;
    vocabulary subjects typically have one. Closeness is checked against all of them."""

    meaning: str
    """English meaning, e.g. 'train'."""

    subject_type: str
    """WaniKani subject type: 'vocabulary' or 'kanji'."""

    reading_mnemonic: str | None = None
    """WaniKani's mnemonic for remembering the reading. May contain markup tags."""

    meaning_mnemonic: str | None = None
    """WaniKani's mnemonic for remembering the meaning. May contain markup tags."""

    review_stats: ReviewStats | None = None
    """Lifetime WaniKani review statistics for this subject. None for hardcoded items
    or subjects the user hasn't reviewed yet."""


class ExplainRequest(BaseModel):
    """Payload sent by the frontend when the user submits a guess."""

    characters: str
    """The kanji compound that was shown."""

    reading: str
    """The primary hiragana reading shown in the result banner."""

    accepted_readings: list[str]
    """All readings WaniKani accepts as correct for this subject."""

    guess: str
    """What the user typed -- hiragana or romaji."""

    subject_type: str
    """WaniKani subject type: 'vocabulary' or 'kanji'."""

    reading_mnemonic: str | None = None
    """WaniKani's reading mnemonic, passed to Claude for reference."""

    wanikani_token: str | None = None
    """Optional token used to pull the user's vocabulary list for personalised
    related compound suggestions."""


class ExplainResponse(BaseModel):
    """Response returned after evaluating a guess and calling Claude."""

    is_correct: bool
    """Whether the user's guess matched the correct reading."""

    closeness: str
    """How close the guess was: 'correct', 'very_close', 'close', or 'off'."""

    explanation: str
    """Claude's pattern explanation for this compound."""

    pattern: str | None = None
    """Reading pattern classification extracted from Claude's response.
    One of: on+on, kun+kun, on+kun, kun+on, irregular, single, mixed."""


class HintRequest(BaseModel):
    """Payload sent by the frontend when the user requests a hint."""

    characters: str
    """The kanji compound being quizzed."""

    meaning: str
    """The English meaning -- Claude can reference this without spoiling the reading."""

    subject_type: str
    """WaniKani subject type: 'vocabulary' or 'kanji'."""

    reading_mnemonic: str | None = None
    """WaniKani's reading mnemonic. Claude can nudge toward it without quoting it."""


class HintResponse(BaseModel):
    """A nudge toward the correct reading without revealing it."""

    hint: str
    """Claude's hint -- guides the student toward the pattern, not the answer."""

"""
Pydantic models for the quiz domain.

These define the data contract between frontend and backend.
Any client (Streamlit today, React later) must conform to these shapes.
"""

from pydantic import BaseModel


class QuizItem(BaseModel):
    """A single kanji compound presented to the user for reading practice."""

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


class ExplainResponse(BaseModel):
    """Response returned after evaluating a guess and calling Claude."""

    is_correct: bool
    """Whether the user's guess matched the correct reading."""

    closeness: str
    """How close the guess was: 'correct', 'very_close', 'close', or 'off'."""

    explanation: str
    """Claude's pattern explanation for this compound."""

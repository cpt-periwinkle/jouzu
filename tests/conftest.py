"""
Shared pytest fixtures for Jouzu tests.

Fixtures defined here are available to all test files without importing.
Add fixtures here when they are needed across multiple test modules.
"""

import pytest

from backend.models.quiz import QuizItem


def make_item(
    characters: str = "電車",
    reading: str = "でんしゃ",
    accepted_readings: list[str] | None = None,
    meaning: str = "train",
    subject_type: str = "vocabulary",
) -> QuizItem:
    """
    Build a minimal QuizItem for use in tests.

    Defaults to 電車 / でんしゃ. Override any field as needed.
    accepted_readings defaults to [reading] if not provided.
    """
    return QuizItem(
        characters=characters,
        reading=reading,
        accepted_readings=accepted_readings or [reading],
        meaning=meaning,
        subject_type=subject_type,
    )


@pytest.fixture
def sample_items() -> list[QuizItem]:
    """A small list of QuizItems covering different reading patterns."""
    return [
        make_item("電車", "でんしゃ", meaning="train"),
        make_item("学生", "がくせい", meaning="student"),
        make_item("手紙", "てがみ", meaning="letter"),
        make_item("今日", "きょう", meaning="today"),
        make_item("大人", "おとな", meaning="adult"),
    ]


@pytest.fixture
def kanji_item() -> QuizItem:
    """A kanji subject with multiple accepted readings."""
    return make_item(
        characters="一",
        reading="いち",
        accepted_readings=["いち", "ひと"],
        meaning="one",
        subject_type="kanji",
    )

"""
CSV loader for quiz items.

Parses compound lists from CSV files into QuizItems. Used for both the
shipped N4 fallback deck and user-uploaded custom decks.

Expected CSV format (header row required):
    characters,reading,meaning
    電車,でんしゃ,train
    学生,がくせい,student

WaniKani-specific fields (subject_id, mnemonics, review_stats) are not
included in the CSV format -- they are WaniKani-only data. Claude fills
in the pattern explanation and context sentences regardless of source.
"""

import csv
import io
from pathlib import Path

from backend.models.quiz import QuizItem

REQUIRED_COLUMNS = {"characters", "reading", "meaning"}


def _row_to_quiz_item(row: dict[str, str]) -> QuizItem | None:
    """
    Convert a single CSV row into a QuizItem.

    Returns None if any required field is missing or empty so malformed
    rows are skipped silently rather than crashing the loader.

    accepted_readings defaults to [reading] since CSV decks have one reading
    per compound. subject_type defaults to 'vocabulary' since CSV decks
    don't carry WaniKani type information.
    """
    characters = row.get("characters", "").strip()
    reading = row.get("reading", "").strip()
    meaning = row.get("meaning", "").strip()

    if not characters or not reading or not meaning:
        return None

    return QuizItem(
        characters=characters,
        reading=reading,
        accepted_readings=[reading],
        meaning=meaning,
        subject_type="vocabulary",
    )


def _parse_content(content: str) -> list[QuizItem]:
    """
    Parse CSV string content into a list of QuizItems.

    Raises ValueError if required columns are missing from the header.
    Skips malformed rows without raising.
    """
    reader = csv.DictReader(io.StringIO(content))

    if not reader.fieldnames:
        raise ValueError("CSV file is empty or has no header row.")

    missing = REQUIRED_COLUMNS - set(reader.fieldnames)
    if missing:
        raise ValueError(
            f"CSV is missing required columns: {', '.join(sorted(missing))}. "
            f"Expected: characters, reading, meaning."
        )

    items = []
    for row in reader:
        item = _row_to_quiz_item(row)
        if item:
            items.append(item)

    return items


def load_csv(path: Path) -> list[QuizItem]:
    """
    Load a CSV file from a file path and return a list of QuizItems.

    Used to load the shipped N4 fallback deck on server startup.

    Args:
        path: Absolute path to the CSV file.

    Returns:
        A list of QuizItems parsed from the file.

    Raises:
        FileNotFoundError: If the file does not exist.
        ValueError: If the CSV is missing required columns.
    """
    with open(path, encoding="utf-8") as f:
        return _parse_content(f.read())


def parse_csv(content: bytes) -> list[QuizItem]:
    """
    Parse CSV content from uploaded bytes and return a list of QuizItems.

    Used when a user uploads a custom deck via the frontend.

    Args:
        content: Raw bytes of the uploaded CSV file.

    Returns:
        A list of QuizItems parsed from the upload.

    Raises:
        ValueError: If the CSV is missing required columns or is empty.
    """
    return _parse_content(content.decode("utf-8"))

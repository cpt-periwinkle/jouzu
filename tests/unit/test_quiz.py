"""
Unit tests for backend/services/quiz.py.

Tests check_guess, measure_closeness, and _edit_distance in isolation.
No HTTP calls, no external APIs, no Claude -- pure logic.
"""

import pytest

from backend.services.quiz import (
    _edit_distance,
    _contains_hiragana,
    _hiragana_to_romaji,
    check_guess,
    measure_closeness,
)


# ---------------------------------------------------------------------------
# _edit_distance
# ---------------------------------------------------------------------------

class TestEditDistance:
    def test_identical_strings_return_zero(self):
        assert _edit_distance("densha", "densha") == 0

    def test_single_deletion(self):
        assert _edit_distance("densa", "densha") == 1

    def test_single_insertion(self):
        assert _edit_distance("denssha", "densha") == 1

    def test_single_substitution(self):
        assert _edit_distance("densha", "fensha") == 1

    def test_empty_string_vs_word(self):
        assert _edit_distance("", "densha") == 6

    def test_completely_different_strings(self):
        assert _edit_distance("tokyo", "densha") > 3

    def test_symmetric(self):
        assert _edit_distance("abc", "xyz") == _edit_distance("xyz", "abc")


# ---------------------------------------------------------------------------
# _contains_hiragana
# ---------------------------------------------------------------------------

class TestContainsHiragana:
    def test_pure_hiragana(self):
        assert _contains_hiragana("でんしゃ") is True

    def test_mixed_hiragana_and_kanji(self):
        assert _contains_hiragana("気持ち") is True

    def test_romaji_only(self):
        assert _contains_hiragana("densha") is False

    def test_empty_string(self):
        assert _contains_hiragana("") is False

    def test_katakana_is_not_hiragana(self):
        assert _contains_hiragana("デンシャ") is False

    def test_kanji_only(self):
        assert _contains_hiragana("電車") is False


# ---------------------------------------------------------------------------
# _hiragana_to_romaji
# ---------------------------------------------------------------------------

class TestHiraganaToRomaji:
    def test_basic_conversion(self):
        assert _hiragana_to_romaji("でんしゃ") == "densha"

    def test_combined_kana(self):
        # しゃ is a single mora, should produce "sha" not "shiya"
        assert _hiragana_to_romaji("しゃ") == "sha"

    def test_long_word(self):
        assert _hiragana_to_romaji("としょかん") == "toshokan"

    def test_output_is_lowercase(self):
        result = _hiragana_to_romaji("でんしゃ")
        assert result == result.lower()


# ---------------------------------------------------------------------------
# check_guess
# ---------------------------------------------------------------------------

class TestCheckGuess:
    def test_correct_hiragana_guess(self):
        assert check_guess("でんしゃ", ["でんしゃ"]) is True

    def test_incorrect_hiragana_guess(self):
        assert check_guess("がくせい", ["でんしゃ"]) is False

    def test_correct_romaji_guess(self):
        assert check_guess("densha", ["でんしゃ"]) is True

    def test_incorrect_romaji_guess(self):
        assert check_guess("gakusei", ["でんしゃ"]) is False

    def test_romaji_is_case_insensitive(self):
        assert check_guess("DENSHA", ["でんしゃ"]) is True
        assert check_guess("Densha", ["でんしゃ"]) is True

    def test_leading_trailing_whitespace_stripped(self):
        assert check_guess("  densha  ", ["でんしゃ"]) is True
        assert check_guess("  でんしゃ  ", ["でんしゃ"]) is True

    def test_multiple_accepted_readings_first_matches(self):
        assert check_guess("いち", ["いち", "ひと"]) is True

    def test_multiple_accepted_readings_second_matches(self):
        assert check_guess("ひと", ["いち", "ひと"]) is True

    def test_multiple_accepted_readings_none_match(self):
        assert check_guess("に", ["いち", "ひと"]) is False

    def test_romaji_with_spaces_stripped(self):
        assert check_guess("den sha", ["でんしゃ"]) is True


# ---------------------------------------------------------------------------
# measure_closeness
# ---------------------------------------------------------------------------

class TestMeasureCloseness:
    def test_exact_hiragana_match_is_correct(self):
        assert measure_closeness("でんしゃ", ["でんしゃ"]) == "correct"

    def test_exact_romaji_match_is_correct(self):
        assert measure_closeness("densha", ["でんしゃ"]) == "correct"

    def test_one_character_off_is_very_close(self):
        # "densa" vs "densha" -- edit distance 1
        assert measure_closeness("densa", ["でんしゃ"]) == "very_close"

    def test_two_characters_off_is_close(self):
        # "dena" vs "densha" -- edit distance 2
        assert measure_closeness("dena", ["でんしゃ"]) == "close"

    def test_completely_wrong_is_off(self):
        assert measure_closeness("tokyo", ["でんしゃ"]) == "off"

    def test_uses_best_match_across_accepted_readings(self):
        # "いち" exactly matches first accepted reading
        assert measure_closeness("いち", ["いち", "ひと"]) == "correct"

    def test_close_to_second_accepted_reading(self):
        # "ito" is close to "ひと" romanized as "hito" -- 1 char off
        assert measure_closeness("ito", ["いち", "ひと"]) == "very_close"

    def test_empty_guess_is_off(self):
        assert measure_closeness("", ["でんしゃ"]) == "off"

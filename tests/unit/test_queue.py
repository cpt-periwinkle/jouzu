"""
Unit tests for backend/services/queue.py.

Tests each queue mode's behavior, weight updates, streak logic,
and configure/reset functionality. No HTTP calls, no external APIs.
"""

import pytest

from backend.services.queue import QuizQueue
from tests.conftest import make_item


@pytest.fixture
def items():
    """Five distinct items for queue testing."""
    return [
        make_item("電車", "でんしゃ"),
        make_item("学生", "がくせい"),
        make_item("手紙", "てがみ"),
        make_item("今日", "きょう"),
        make_item("大人", "おとな"),
    ]


@pytest.fixture
def single_item():
    """A list with one item -- useful for testing loops."""
    return [make_item("電車", "でんしゃ")]


# ---------------------------------------------------------------------------
# Random mode
# ---------------------------------------------------------------------------

class TestRandomMode:
    def test_returns_valid_item(self, items):
        queue = QuizQueue(mode="random")
        result = queue.next_item(items)
        assert result in items

    def test_raises_on_empty_list(self):
        queue = QuizQueue(mode="random")
        with pytest.raises(ValueError):
            queue.next_item([])


# ---------------------------------------------------------------------------
# Shuffle mode
# ---------------------------------------------------------------------------

class TestShuffleMode:
    def test_all_items_seen_before_repeat(self, items):
        queue = QuizQueue(mode="shuffle")
        seen = set()
        for _ in range(len(items)):
            item = queue.next_item(items)
            seen.add(item.characters)
        assert len(seen) == len(items)

    def test_reshuffles_after_exhaustion(self, items):
        queue = QuizQueue(mode="shuffle")
        # Exhaust the deck once
        first_cycle = [queue.next_item(items).characters for _ in range(len(items))]
        # Second cycle should also cover all items
        second_cycle = [queue.next_item(items).characters for _ in range(len(items))]
        assert set(first_cycle) == set(items[i].characters for i in range(len(items)))
        assert set(second_cycle) == set(items[i].characters for i in range(len(items)))

    def test_single_item_loops_indefinitely(self, single_item):
        queue = QuizQueue(mode="shuffle")
        for _ in range(5):
            result = queue.next_item(single_item)
            assert result.characters == "電車"


# ---------------------------------------------------------------------------
# Sequential mode
# ---------------------------------------------------------------------------

class TestSequentialMode:
    def test_items_returned_in_order(self, items):
        queue = QuizQueue(mode="sequential")
        for i in range(len(items)):
            result = queue.next_item(items)
            assert result.characters == items[i].characters

    def test_wraps_back_to_start(self, items):
        queue = QuizQueue(mode="sequential")
        # Go through the full list
        for _ in range(len(items)):
            queue.next_item(items)
        # Next item should be the first again
        result = queue.next_item(items)
        assert result.characters == items[0].characters

    def test_single_item_loops(self, single_item):
        queue = QuizQueue(mode="sequential")
        for _ in range(5):
            result = queue.next_item(single_item)
            assert result.characters == "電車"


# ---------------------------------------------------------------------------
# Mini-batch mode
# ---------------------------------------------------------------------------

class TestMiniBatchMode:
    def test_batch_size_respected(self, items):
        queue = QuizQueue(mode="mini-batch", batch_size=2)
        # First batch should have 2 unique items
        batch = {queue.next_item(items).characters for _ in range(2)}
        assert len(batch) == 2

    def test_all_items_seen_across_batches(self, items):
        queue = QuizQueue(mode="mini-batch", batch_size=2)
        seen = set()
        # 5 items with batch_size=2 means 3 batches (2+2+1)
        for _ in range(len(items)):
            seen.add(queue.next_item(items).characters)
        assert len(seen) == len(items)

    def test_batch_size_larger_than_deck_uses_full_deck(self, items):
        queue = QuizQueue(mode="mini-batch", batch_size=100)
        seen = set()
        for _ in range(len(items)):
            seen.add(queue.next_item(items).characters)
        assert len(seen) == len(items)

    def test_reshuffles_after_all_batches_exhausted(self, items):
        queue = QuizQueue(mode="mini-batch", batch_size=2)
        first_run = {queue.next_item(items).characters for _ in range(len(items))}
        second_run = {queue.next_item(items).characters for _ in range(len(items))}
        assert first_run == second_run == {item.characters for item in items}


# ---------------------------------------------------------------------------
# Weighted mode
# ---------------------------------------------------------------------------

class TestWeightedMode:
    def test_returns_valid_item(self, items):
        queue = QuizQueue(mode="weighted")
        result = queue.next_item(items)
        assert result in items

    def test_incorrect_increases_weight(self, items):
        queue = QuizQueue(mode="weighted")
        chars = items[0].characters
        queue.record_result(chars, correct=False)
        assert queue._weights[chars] == 2.0

    def test_correct_decreases_weight(self, items):
        queue = QuizQueue(mode="weighted")
        chars = items[0].characters
        # Miss first to raise weight above 1.0
        queue.record_result(chars, correct=False)
        queue.record_result(chars, correct=True)
        assert queue._weights[chars] == 1.5

    def test_weight_capped_at_three(self, items):
        queue = QuizQueue(mode="weighted")
        chars = items[0].characters
        # Miss many times -- weight should not exceed 3.0
        for _ in range(10):
            queue.record_result(chars, correct=False)
        assert queue._weights[chars] == 3.0

    def test_weight_floor_is_one(self, items):
        queue = QuizQueue(mode="weighted")
        chars = items[0].characters
        # Get it right many times from baseline -- weight should not go below 1.0
        for _ in range(10):
            queue.record_result(chars, correct=True)
        assert queue._weights[chars] == 1.0

    def test_record_result_no_op_in_non_weighted_mode(self, items):
        queue = QuizQueue(mode="shuffle")
        queue.record_result(items[0].characters, correct=False)
        assert queue._weights == {}


# ---------------------------------------------------------------------------
# Configure and reset
# ---------------------------------------------------------------------------

class TestConfigureAndReset:
    def test_configure_changes_mode(self, items):
        queue = QuizQueue(mode="random")
        queue.configure("sequential", batch_size=10)
        assert queue.mode == "sequential"

    def test_configure_resets_state(self, items):
        queue = QuizQueue(mode="shuffle")
        # Partially exhaust the queue
        queue.next_item(items)
        queue.next_item(items)
        queue.configure("sequential", batch_size=10)
        # Indices should be cleared
        assert queue._indices == []
        assert queue._position == 0

    def test_configure_clears_weights(self, items):
        queue = QuizQueue(mode="weighted")
        queue.record_result(items[0].characters, correct=False)
        queue.configure("shuffle", batch_size=10)
        assert queue._weights == {}

    def test_reset_clears_state_without_changing_mode(self, items):
        queue = QuizQueue(mode="shuffle")
        queue.next_item(items)
        queue.reset()
        assert queue.mode == "shuffle"
        assert queue._indices == []

    def test_reset_clears_weights(self, items):
        queue = QuizQueue(mode="weighted")
        queue.record_result(items[0].characters, correct=False)
        queue.reset()
        assert queue._weights == {}

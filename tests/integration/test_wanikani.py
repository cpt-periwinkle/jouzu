"""
Integration tests for backend/services/wanikani.py.

TODO: Write these when WaniKani write operations are added (assignments, reviews).
Mock httpx calls using pytest-mock so no real WaniKani API is hit.

What to test:
- get_user_level returns an integer from mocked /user response
- _fetch_subjects filters out hidden subjects
- _fetch_subjects filters out kana-only vocabulary
- _fetch_subjects handles pagination (follows next_url)
- _fetch_review_stats returns dict keyed by subject_id
- get_items_for_token uses cache on second call (no second HTTP call)
- get_all_reviewed_subjects filters by SRS stage 5+
- Invalid token raises httpx.HTTPStatusError
"""

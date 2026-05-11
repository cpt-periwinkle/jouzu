# Architecture

This document explains the design decisions behind Jouzu -- why things are structured the way they are, what's intentional, and what the growth path looks like.

---

## Core principle: FastAPI is a real API

The most important decision in this project is that Streamlit is a thin HTTP client, not a Python frontend. It calls FastAPI over HTTP (`requests.get(...)`) and renders what comes back. It never imports backend modules directly.

This was a deliberate choice made early so the frontend is swappable. When the React frontend is built, it calls the same endpoints. The backend doesn't change at all.

---

## Folder structure

```
backend/
    main.py              # App setup and router registration only
    core/
        config.py        # All external service URLs, credentials, and defaults
        cache.py         # CacheProvider protocol + InMemoryCache implementation
    api/
        routes/
            quiz.py      # HTTP layer -- thin, no business logic
    services/
        wanikani.py      # WaniKani API client
        claude.py        # Anthropic API client
        quiz.py          # Item source routing and guess evaluation
        queue.py         # Queue mode logic (shuffle, weighted, etc.)
        csv_loader.py    # CSV parsing for fallback and custom uploads
    models/
        quiz.py          # Pydantic request/response contracts
    prompts/
        quiz.py          # Prompt builders -- dynamic section assembly
        templates.py     # Static prompt template strings
data/
    n4_fallback.csv      # Shipped fallback deck
frontend/
    app.py               # Streamlit UI -- HTTP calls only, no business logic
```

### Why this structure

Each layer has exactly one job. Routes handle HTTP. Services handle logic. Models define contracts. Prompts define LLM instructions. Config defines external dependencies.

Adding a new feature domain (grammar drills, reading practice) means adding files in each layer for that domain -- not modifying existing files. The existing quiz files don't change.

---

## Key decisions

### `core/config.py` as the single source of truth

Every external service URL, API version string, model name, and default value lives here. If Anthropic releases a new model or WaniKani updates their API revision, one file changes.

```python
ANTHROPIC_MODEL = "claude-sonnet-4-6"
WANIKANI_BASE_URL = "https://api.wanikani.com/v2"
WANIKANI_REVISION = "20170710"
```

### `CacheProvider` protocol in `core/cache.py`

The WaniKani subject cache and the quiz queue cache both depend on a `CacheProvider` protocol, not on a concrete dict. `InMemoryCache` is the current implementation.

```python
class CacheProvider(Protocol, Generic[T]):
    def get(self, key: str) -> T | None: ...
    def set(self, key: str, value: T) -> None: ...
    def contains(self, key: str) -> bool: ...
```

When moving to a multi-user deployment, replace `InMemoryCache()` with a Redis implementation that satisfies the same protocol. Nothing else changes.

### Prompts separated into templates and builders

`prompts/templates.py` holds the raw template strings with `{placeholder}` syntax. `prompts/quiz.py` computes the dynamic sections (flavor messages, mnemonic lines, vocabulary lists) and calls `.format()`.

This means the template structure is readable without wading through conditional logic, and a missing placeholder raises a `KeyError` immediately rather than silently producing a broken prompt.

### Queue system design

The queue system went through deliberate design before implementation. The goal was to support multiple study strategies without the backend knowing anything about how the frontend is using them, and without duplicating item data.

**Why a queue at all?**

The naive approach -- `random.choice(items)` on every round -- is statistically broken for small decks. With 10 items, you can see the same word three times before seeing half the others. For a study tool where repetition is the point, that's frustrating. The queue system gives the user control over repetition strategy.

**The five modes and why each exists:**

- **Random** -- pure `random.choice()`, no state, kept intentionally. Some people prefer unpredictable exposure. It's also the simplest fallback.

- **Shuffle** -- no repeats until the entire deck is seen, then reshuffle. Standard flashcard behavior. The default mode because it balances coverage and unpredictability.

- **Sequential** -- items in order, wrapping at the end. Useful for structured decks (Genki chapter vocabulary, level-ordered WaniKani items) where you want to move through material deliberately rather than randomly.

- **Mini-batch** -- drill N items at a time before moving to the next batch. The batch size is configurable from 5 to 100. This addresses a specific study pattern: when you have a large deck (100+ items from WaniKani all reviewed), pure shuffle can feel scattered. Mini-batch lets you focus on a small group until you've seen all of them, then move on. The batch size is capped at the actual deck size so you can't set it larger than what's available.

- **Weighted** -- items you miss get higher probability of appearing again, using `random.choices()` with per-item float weights. Miss increments weight by 1.0 (max 3.0). Correct decrements by 0.5 (min 1.0). The 3x cap is intentional -- without it, repeatedly missing 10 items in a 200-item deck would bury the other 190 items almost completely. The cap keeps missed items prominent without making the session about only those items.

**Mode availability by source:**

Not every mode makes sense for every source. Sequential on "all reviewed" (potentially 1000+ items across 10+ levels) would order by WaniKani subject ID -- meaningless for pattern drilling. Weighted on "all reviewed" was considered but the bias loop risk is real at that scale even with the cap. The restrictions are enforced in both the frontend (dropdown filters) and the backend (configure endpoint validates mode against source).

| Mode | Current level | All reviewed | N4 fallback | Custom upload |
|---|---|---|---|---|
| Random | ✓ | ✓ | ✓ | ✓ |
| Shuffle | ✓ | ✓ | ✓ | ✓ |
| Sequential | ✓ | ✗ | ✓ | ✓ |
| Mini-batch | ✓ | ✓ | ✗ | ✓ |
| Weighted | ✓ | ✗ | ✗ | ✓ |

N4 fallback is excluded from mini-batch (20 items makes batching pointless) and weighted (too few items for weights to be meaningful).

**Queue state vs item data:**

`QuizQueue` holds only indices into the item list and a weights dict keyed by characters string. It never stores `QuizItem` objects. Items live in the WaniKani subject cache. The queue points into that cache.

This matters for scale. A 1000-item deck produces a queue with 1000 integers (~8KB) and optionally 1000 floats (~8KB more). The `QuizItem` objects themselves (with mnemonics, review stats, accepted readings) are already in memory from the WaniKani fetch -- the queue adds negligible overhead on top of them.

**Queue session ID:**

The queue is keyed by a UUID generated by the frontend on first page load, not by the WaniKani token. This keeps queue state independent of the data source. If the user switches from WaniKani current level to N4 fallback mid-session, the queue resets but the session ID stays the same. The queue is a study session concept, not a data concept.

**Drill my misses:**

This is a session-layer feature built entirely on the frontend, not the queue backend. When the user enters drill mode, the frontend filters the `seen_items` cache (every item shown during the session) to only the ones in `missed_compounds`. It tracks a correct streak per item (reset to 0 on miss, incremented on correct) and graduates items out of the drill at streak ≥ 2. When all items are cleared, the session exits drill mode automatically.

The "correct twice in a row" threshold was chosen deliberately -- one correct answer after multiple misses could be luck. Two in a row is enough signal that the pattern has landed without making the drill feel punishing.

This is an intentional exception to the light-frontend principle. Drill mode is purely ephemeral -- it has no value outside the current browser tab and session. The item data is already on the frontend from previous rounds. Sending this logic to the backend would be a round trip to do arithmetic the frontend can do locally with data it already has.

This changes when persistence is added. Once missed compounds are stored in a database across sessions, drill mode logic moves to the backend -- it would need to query history, update streaks, and persist results. At that point `seen_items` and `drill_streaks` become backend state. That migration is the trigger, not an arbitrary refactor.

### `get_quiz_items()` as the single routing function

All item sources funnel through one function:

```python
def get_quiz_items(token, source, session_id) -> list[QuizItem]:
```

The rest of the app doesn't know or care whether items came from WaniKani, a CSV, or the fallback deck. Adding a new source means adding a branch here and a fetch function in the appropriate service.

### Session state and the stateless backend

The backend is fully stateless with respect to the user's study session. It holds two things in memory: cached WaniKani subject lists (keyed by token) and queue state (keyed by session ID). Both are implementation details of serving requests efficiently -- neither represents "a user's session" in any meaningful sense. The backend doesn't know who you are, what you've attempted, or how you've been doing. It just serves items and evaluates guesses.

Everything that constitutes a study session lives in Streamlit's `st.session_state` on the frontend:

- `session_stats` -- attempted count, correct count, pattern hits and misses, missed compounds list
- `seen_items` -- every item shown this session, cached locally for drill mode
- `drill_mode`, `drill_queue`, `drill_streaks` -- drill state
- `current_item`, `result`, `hint` -- the current round state
- `wanikani_token`, `source`, `queue_mode`, `batch_size` -- user preferences

All of this resets when the browser tab is closed. There is no persistence between sessions.

**Why the session resets on source or token change:**

Session stats are only meaningful in context. If you switch from WaniKani current level to N4 fallback mid-session, the accuracy numbers and pattern breakdown would be mixing data from two different item pools -- that's misleading. A 70% accuracy rate means something different when you're drilling your current WaniKani level versus a fixed 20-word fallback deck.

The same logic applies to token changes. A different token means a different WaniKani account and a different vocabulary list. Carrying over the missed compounds list from one account's session into another account's drill makes no sense.

Mode changes also reset the session for a softer reason: if you've been drilling in shuffle mode and switch to weighted, the weight values should start fresh rather than inheriting whatever patterns emerged from a different strategy.

The reset is deliberate and aggressive by design. A clean slate is better than misleading continuity.

**What this means for the future:**

When persistence is added (SQLite or a proper database), the session concept moves to the backend. Stats accumulate across sessions, history is queryable, drill state survives a page refresh. At that point the frontend becomes even thinner -- it stops holding stats entirely and just renders what the backend tells it. The backend gains a user identity layer (auth) and the concept of a session tied to a person rather than a browser tab.

The current architecture doesn't block this. The stats shape (`session_stats` dict) maps directly to a database row. The migration is additive -- you're not rewriting the logic, you're moving where it lives and persisting the output.

### WaniKani token is user-provided at runtime

The WaniKani API token is not stored server-side. It arrives as a query parameter on each request, is used to authenticate against WaniKani, and is cached server-side only as a cache key for the subject list.

This keeps the backend stateless with respect to user identity. When proper auth is added, the token moves from a query parameter to a server-side lookup after login. The WaniKani service functions don't change.

---

## What changes when the React frontend arrives

Nothing in the backend. React calls the same endpoints Streamlit calls:

- `GET /quiz/item?source=...&queue_session_id=...&wanikani_token=...`
- `POST /quiz/explain`
- `POST /quiz/hint`
- `POST /quiz/upload`
- `POST /quiz/queue/configure`
- `POST /quiz/queue/result`
- `POST /quiz/queue/reset`

React holds the `queue_session_id` in component state (or localStorage for persistence across refreshes) and attaches it to every request. The WaniKani token comes from a text input in the UI, same as Streamlit.

The one Streamlit-specific workaround that disappears: the file upload deduplication guard (`last_uploaded_key`) exists because Streamlit reruns the entire script on every interaction. React fires upload events once, so that guard is unnecessary.

**Keyboard shortcuts** are also a React-first feature. Clicking Submit, Hint, and Skip with a mouse in a flashcard app is genuinely bad UX -- you want to stay on the keyboard while studying. Streamlit has no native support for custom key bindings on buttons. The React frontend should bind Submit to Enter (or Space), Hint to H, and Skip to S or the arrow keys. This is one of the concrete UX improvements that motivated the React rebuild decision, not just a nice-to-have.

**Streamlit visual bugs:** Dropdowns occasionally flicker, widgets sometimes re-render unexpectedly, and the rerun model means UI state can feel laggy or inconsistent in ways that are simply not fixable without rewriting Streamlit internals. This isn't a code quality issue -- it's an inherent limitation of Streamlit's architecture. Every interaction reruns the entire script, which means the UI is rebuilt from scratch on every click. For a simple data dashboard this is fine. For an interactive flashcard app where smoothness and responsiveness matter, it's frustrating and there's no clean workaround. This is the strongest practical argument for the React rebuild -- not just aesthetics, but basic usability.

---

## Future scope

### `wanikani.py` → `wanikani/` package

When write operations are added (submit reviews, start assignments), `wanikani.py` becomes a package:

```
backend/services/wanikani/
    __init__.py
    subjects.py      # fetch vocab, kanji (current content)
    assignments.py   # fetch review queue, start lessons
    reviews.py       # submit review results
    user.py          # fetch user level, subscription
```

### Persistent storage

Session state currently lives in Streamlit session state (frontend) and `InMemoryCache` (backend). Both reset on server restart or tab close.

When persistence is added:
- Replace `InMemoryCache` with a SQLite or Redis-backed implementation of `CacheProvider`
- Add a user identity layer (auth) so history can be attributed to a person
- `SessionStats` dataclass maps directly to a database row -- the shape doesn't change, just where it's stored

### Rate limiting

Before public deployment, add `slowapi` to the explain and hint endpoints. These are the only endpoints that incur Anthropic API costs. A simple per-IP rate limit (e.g. 30 requests per minute) bounds the worst-case cost exposure.

### WaniKani SRS queue mode

The assignments endpoint returns `available_at` timestamps -- items due for review. A future queue mode would fetch assignments where `available_at` is in the past, order by due date, and drill those. Submitting results back via `POST /reviews` would close the loop with WaniKani's SRS. This requires the write integration in `assignments.py` and `reviews.py`.

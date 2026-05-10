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

### Queue state vs item data

`QuizQueue` in `services/queue.py` holds only indices and weights -- it never stores `QuizItem` objects. Items live in the WaniKani subject cache. The queue points into that cache via integer indices.

This means a 1000-item deck has a queue with 1000 integers (~8KB), not 1000 duplicated objects. The queue session ID (a UUID from the frontend) is the cache key.

### `get_quiz_items()` as the single routing function

All item sources funnel through one function:

```python
def get_quiz_items(token, source, session_id) -> list[QuizItem]:
```

The rest of the app doesn't know or care whether items came from WaniKani, a CSV, or the fallback deck. Adding a new source means adding a branch here and a fetch function in the appropriate service.

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

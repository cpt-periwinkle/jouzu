"""
Integration tests for backend API routes.

TODO: Write these when the API stabilizes and before the React frontend is built.
Use FastAPI's TestClient so no server needs to be running.
Mock Claude and WaniKani calls so tests don't cost money or require network.

What to test:
- GET /quiz/item returns a valid QuizItem (fallback source)
- GET /quiz/item with unknown source falls back to fallback
- POST /quiz/explain returns ExplainResponse with all required fields
- POST /quiz/upload accepts valid CSV, returns session_id and item_count
- POST /quiz/upload rejects CSV with missing columns (422)
- POST /quiz/queue/configure rejects invalid mode for source (422)
- POST /quiz/queue/configure accepts valid mode for source (200)
- GET /health returns {"status": "ok"}

Example setup:
    from fastapi.testclient import TestClient
    from backend.main import app
    client = TestClient(app)
"""

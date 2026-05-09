"""
Jouzu FastAPI application.

Handles app setup, middleware, and router registration only.
Business logic lives in services/, routes live in api/routes/.

Run with:
    uvicorn backend.main:app --reload
"""

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from backend.api.routes import quiz

app = FastAPI(title="Jouzu API", version="0.1.0")

# Streamlit makes server-to-server requests so it doesn't need CORS, but the
# React frontend that replaces it will -- browsers enforce same-origin policy
# and block requests across ports without this middleware in place.
app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:8501", "http://localhost:3000"],
    allow_methods=["*"],
    allow_headers=["*"],
)

# Each feature domain gets its own router in api/routes/.
# Adding grammar, reading, or any other feature is one include_router() line here.
app.include_router(quiz.router)


@app.get("/health", tags=["meta"])
def health() -> dict[str, str]:
    """Liveness check -- belongs to no feature domain so it lives here directly."""
    return {"status": "ok"}

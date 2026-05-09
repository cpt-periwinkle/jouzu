"""
Quiz routes.

Registered on the FastAPI app in main.py under the /quiz prefix.
All endpoints here are available at /quiz/<path>.

This file is intentionally thin -- it handles HTTP concerns only (request
parsing, response shaping, error codes). All business logic lives in services/.
"""

import random

from fastapi import APIRouter, HTTPException

from backend.models.quiz import ExplainRequest, ExplainResponse, QuizItem
from backend.services.claude import get_explanation
from backend.services.quiz import get_quiz_items

# prefix="/quiz" means every route defined on this router is mounted at /quiz/<path>.
# tags=["quiz"] groups these endpoints together in the auto-generated API docs at /docs.
router = APIRouter(prefix="/quiz", tags=["quiz"])


@router.get("/item", response_model=QuizItem)
def get_quiz_item(wanikani_token: str | None = None) -> QuizItem:
    """
    Return a random compound from the active quiz item list.

    Accepts an optional wanikani_token query parameter. When provided, the
    item is drawn from the user's WaniKani current-level vocabulary. Without
    a token, falls back to the hardcoded N4 list.

    In Milestone 5, the source (current level / all reviewed / hardcoded)
    will be selectable via a separate query parameter.

    Returns 404 if the item list is empty, which should not happen in normal
    operation but guards against a misconfigured WaniKani token returning nothing.
    """
    items = get_quiz_items(token=wanikani_token)
    if not items:
        raise HTTPException(status_code=404, detail="No quiz items available.")
    return random.choice(items)


@router.post("/explain", response_model=ExplainResponse)
def explain(request: ExplainRequest) -> ExplainResponse:
    """
    Evaluate the user's guess and return a Claude-generated explanation.

    Delegates entirely to services/claude.py which handles closeness detection,
    prompt construction, and the Anthropic API call. This route just unpacks
    the request and passes the fields through.
    """
    return get_explanation(
        characters=request.characters,
        reading=request.reading,
        accepted_readings=request.accepted_readings,
        guess=request.guess,
        subject_type=request.subject_type,
    )

"""
Quiz routes.

Registered on the FastAPI app in main.py under the /quiz prefix.
All endpoints here are available at /quiz/<path>.

This file is intentionally thin -- it handles HTTP concerns only (request
parsing, response shaping, error codes). All business logic lives in services/.
"""

import random
import uuid

from fastapi import APIRouter, File, HTTPException, UploadFile

from backend.models.quiz import (
    ExplainRequest,
    ExplainResponse,
    HintRequest,
    HintResponse,
    QueueConfigRequest,
    QuizItem,
    RecordResultRequest,
    ResetQueueRequest,
)
from backend.services.claude import get_explanation, get_hint
from backend.services.csv_loader import parse_csv
from backend.services.queue import (
    configure_queue,
    get_or_create_queue,
    record_queue_result,
    reset_queue,
)
from backend.services.quiz import get_quiz_items, store_custom_items

router = APIRouter(prefix="/quiz", tags=["quiz"])

# Modes not available for certain sources.
# Enforced at configure time so the frontend and backend agree.
_RESTRICTED_MODES: dict[str, set[str]] = {
    "all_reviewed": {"sequential", "weighted"},
    "fallback":     {"mini-batch", "weighted"},
}


@router.get("/item", response_model=QuizItem)
def get_quiz_item(
    wanikani_token: str | None = None,
    source: str = "fallback",
    upload_session_id: str | None = None,
    queue_session_id: str | None = None,
) -> QuizItem:
    """
    Return the next compound based on the active queue mode.

    If queue_session_id is provided, the queue service selects the item
    based on the configured mode (shuffle, sequential, mini-batch, weighted).
    Without a queue_session_id, falls back to pure random selection.

    source options:
      current_level -- WaniKani vocabulary and kanji at the user's current level
      all_reviewed  -- all WaniKani subjects passed to Guru or above
      fallback      -- shipped N4 fallback CSV, always available
      custom        -- user-uploaded CSV, identified by upload_session_id
    """
    items = get_quiz_items(
        token=wanikani_token,
        source=source,
        session_id=upload_session_id,
    )
    if not items:
        raise HTTPException(status_code=404, detail="No quiz items available.")

    if queue_session_id:
        queue = get_or_create_queue(queue_session_id)
        return queue.next_item(items)

    return random.choice(items)


@router.post("/queue/configure")
def queue_configure(request: QueueConfigRequest) -> dict[str, str]:
    """
    Configure the queue mode and batch size for a session.

    Validates that the requested mode is available for the given source.
    Resets queue state so the new mode starts from a clean slate.
    """
    restricted = _RESTRICTED_MODES.get(request.source, set())
    if request.mode in restricted:
        raise HTTPException(
            status_code=422,
            detail=f"Mode '{request.mode}' is not available for source '{request.source}'.",
        )
    configure_queue(request.session_id, request.mode, request.batch_size)
    return {"status": "ok"}


@router.post("/queue/result")
def queue_result(request: RecordResultRequest) -> dict[str, str]:
    """
    Record a guess result for weighted queue adjustment.

    No-op if the queue is not in weighted mode.
    """
    record_queue_result(request.session_id, request.characters, request.correct)
    return {"status": "ok"}


@router.post("/queue/reset")
def queue_reset(request: ResetQueueRequest) -> dict[str, str]:
    """Reset queue state for a session without changing mode or batch size."""
    reset_queue(request.session_id)
    return {"status": "ok"}


@router.post("/upload")
async def upload_csv(file: UploadFile = File(...)) -> dict[str, str | int]:
    """
    Accept a CSV file upload, parse it into QuizItems, cache it, and return
    a session_id the frontend uses to reference this deck on subsequent requests.

    Expected CSV format:
        characters,reading,meaning
        電車,でんしゃ,train
    """
    content = await file.read()

    try:
        items = parse_csv(content)
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc))

    if not items:
        raise HTTPException(
            status_code=422,
            detail="No valid items found in CSV. Check that rows have characters, reading, and meaning.",
        )

    session_id = str(uuid.uuid4())
    store_custom_items(session_id, items)

    return {"session_id": session_id, "item_count": len(items)}


@router.post("/explain", response_model=ExplainResponse)
def explain(request: ExplainRequest) -> ExplainResponse:
    """
    Evaluate the user's guess and return a Claude-generated explanation.

    Delegates entirely to services/claude.py which handles closeness detection,
    prompt construction, and the Anthropic API call.
    """
    return get_explanation(
        characters=request.characters,
        reading=request.reading,
        accepted_readings=request.accepted_readings,
        guess=request.guess,
        subject_type=request.subject_type,
        reading_mnemonic=request.reading_mnemonic,
        wanikani_token=request.wanikani_token,
    )


@router.post("/hint", response_model=HintResponse)
def hint(request: HintRequest) -> HintResponse:
    """
    Return a hint that nudges the student toward the reading without revealing it.

    The reading is intentionally not included in HintRequest -- Claude cannot
    reveal what it doesn't receive.
    """
    return get_hint(
        characters=request.characters,
        meaning=request.meaning,
        subject_type=request.subject_type,
        reading_mnemonic=request.reading_mnemonic,
    )

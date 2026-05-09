"""
Claude service.

The only file in the app that talks to the Anthropic SDK directly.
Everything else that needs an explanation calls get_explanation() here.
If the model changes or the API changes, this is the only file to update.
"""

import anthropic

# ANTHROPIC_API_KEY is loaded from .env in core/config.py.
# Importing it here instead of calling os.environ directly keeps all
# environment variable handling in one place.
from backend.core.config import ANTHROPIC_API_KEY, ANTHROPIC_MODEL

# ExplainResponse is the Pydantic model that defines what this service returns:
# an is_correct flag and the explanation text from Claude.
from backend.models.quiz import ExplainResponse

# build_explain_prompt formats the compound, reading, guess, and result into
# the full prompt string that gets sent to Claude.
from backend.prompts.quiz import build_explain_prompt

# measure_closeness returns 'correct', 'very_close', 'close', or 'off' based on
# edit distance between the guess and correct reading. Lives in quiz.py because
# it belongs to quiz logic, not LLM logic.
from backend.services.quiz import measure_closeness

# The Anthropic client is initialized once at module load with the API key.
# Like pykakasi in quiz.py, creating it once and reusing it is more efficient
# than creating a new client on every request.
_client = anthropic.Anthropic(api_key=ANTHROPIC_API_KEY)


def get_explanation(characters: str, reading: str, guess: str) -> ExplainResponse:
    """
    Evaluate the user's guess and return a Claude-generated explanation.

    Steps:
      1. check_guess() compares the guess against the correct reading and
         returns True or False.
      2. build_explain_prompt() slots the compound, reading, guess, and
         correct/incorrect result into the prompt template.
      3. _client.messages.create() sends the prompt to Claude and waits
         for the response. max_tokens=1024 caps the response length.
      4. message.content is a list because Claude can return multiple content
         blocks (e.g. text + tool use). We always expect a TextBlock here.
         The isinstance() check satisfies Pylance's type checker, which correctly
         points out that content[0] could also be a ToolUseBlock (no .text attribute).
      5. ExplainResponse packages is_correct and the explanation text together
         for the route to return to the frontend.

    Args:
        characters: The kanji compound shown to the user, e.g. '電車'.
        reading: The correct hiragana reading, e.g. 'でんしゃ'.
        guess: What the user typed (hiragana or romaji).

    Returns:
        ExplainResponse with is_correct flag and Claude's explanation.
    """
    closeness = measure_closeness(guess, reading)
    is_correct = closeness == "correct"

    prompt = build_explain_prompt(
        characters=characters,
        reading=reading,
        guess=guess,
        closeness=closeness,
    )

    message = _client.messages.create(
        model=ANTHROPIC_MODEL,
        max_tokens=1024,
        messages=[{"role": "user", "content": prompt}],
    )

    block = message.content[0]
    explanation = block.text if isinstance(block, anthropic.types.TextBlock) else ""

    return ExplainResponse(is_correct=is_correct, closeness=closeness, explanation=explanation)

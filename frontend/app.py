"""
Jouzu Streamlit frontend.

Thin HTTP client over the FastAPI backend. Contains no business logic --
all quiz logic, guess evaluation, and LLM calls live in the backend.

HOW STREAMLIT WORKS -- read this before editing the UI:

  Streamlit reruns the entire script from top to bottom on every user
  interaction (button click, text input, etc.). There is no event loop or
  callback system like you'd find in React. Every rerun is a fresh execution.

  This means you cannot store state in regular Python variables -- they reset
  on every rerun. Instead, Streamlit provides st.session_state, a dictionary
  that persists across reruns for the lifetime of the browser session.

  The pattern throughout this file is:
    1. Read from st.session_state at the top of main()
    2. Render UI based on that state
    3. When the user does something, update st.session_state and call st.rerun()
       to trigger a fresh render with the new state

Run with:
    streamlit run frontend/app.py
"""

import os

import requests
import streamlit as st

# API_BASE_URL defaults to localhost for local development.
# In Milestone 6 (deployment), this is overridden by an environment variable
# so the frontend knows where the deployed backend lives.
API_BASE_URL = os.environ.get("API_BASE_URL", "http://localhost:8000")


# ---------------------------------------------------------------------------
# Session state helpers
# ---------------------------------------------------------------------------

def _init_state() -> None:
    """
    Initialise session state keys on first load.

    Because Streamlit reruns the whole script on every interaction, we
    cannot use 'if key not in st.session_state' inside main() directly --
    it would reset on every run. This function uses 'not in' checks so
    keys are only set once (on the very first run) and preserved after that.

    current_item: the compound currently shown to the user (dict from the API).
    result:       the API response after a guess is submitted (dict), or None
                  if the user hasn't submitted yet for this compound.
    """
    if "current_item" not in st.session_state:
        st.session_state.current_item = None
    if "result" not in st.session_state:
        st.session_state.result = None


def _load_new_item() -> None:
    """
    Fetch a random quiz item from the backend and reset result state.

    Stores the item in st.session_state so it survives the next rerun.
    Resets result to None so the UI goes back to the input state.

    raise_for_status() turns any non-2xx HTTP response into an exception.
    ConnectionError means the backend isn't running -- we show a helpful
    message and call st.stop() to halt the current rerun immediately.
    """
    try:
        response = requests.get(f"{API_BASE_URL}/quiz/item", timeout=5)
        response.raise_for_status()
        st.session_state.current_item = response.json()
        st.session_state.result = None
    except requests.exceptions.ConnectionError:
        st.error("Cannot reach the backend. Is `uvicorn backend.main:app --reload` running?")
        st.stop()


def _submit_guess(guess: str) -> None:
    """
    Send the user's guess to the backend and store the explanation result.

    Posts to /quiz/explain with the compound, correct reading, and guess.
    The backend handles closeness detection and the Claude call -- this
    function just fires the request and saves what comes back.

    timeout=30 gives Claude enough time to respond without hanging forever.
    The result dict has three keys: is_correct, closeness, explanation.
    """
    item = st.session_state.current_item
    try:
        response = requests.post(
            f"{API_BASE_URL}/quiz/explain",
            json={
                "characters": item["characters"],
                "reading": item["reading"],
                "guess": guess,
            },
            timeout=30,
        )
        response.raise_for_status()
        st.session_state.result = response.json()
    except requests.exceptions.ConnectionError:
        st.error("Cannot reach the backend. Is `uvicorn backend.main:app --reload` running?")
        st.stop()


# ---------------------------------------------------------------------------
# UI
# ---------------------------------------------------------------------------

def main() -> None:
    """
    Main UI function. Streamlit calls this on every rerun.

    The UI has two states controlled by whether st.session_state.result is None:

      State 1 (result is None): show the compound, text input, Submit + Skip buttons.
      State 2 (result is set):  show the closeness feedback, Claude's explanation,
                                and a Next button that loads a new compound.

    st.rerun() is called after any state change so the UI immediately reflects
    the new state instead of waiting for the next user interaction.
    """
    st.set_page_config(page_title="Jouzu", page_icon="上", layout="centered")
    _init_state()

    st.title("Jouzu 上手")
    st.caption("Kanji reading drill -- learn the patterns, not just the answers.")

    # Load the first compound on initial page load.
    if st.session_state.current_item is None:
        _load_new_item()

    item = st.session_state.current_item
    result = st.session_state.result

    # --- Compound display ---
    # unsafe_allow_html is needed for inline CSS styling.
    # Streamlit's native text elements don't support font-size control.
    st.markdown(
        f"<h1 style='text-align:center; font-size:4rem;'>{item['characters']}</h1>",
        unsafe_allow_html=True,
    )

    # Before submission: hide the meaning behind an expander so the user
    # can check if stuck without it being a spoiler. After submission: show
    # it plainly since the round is over.
    if result:
        st.markdown(
            f"<p style='text-align:center; color:gray;'>{item['meaning']}</p>",
            unsafe_allow_html=True,
        )
    else:
        with st.expander("Show meaning"):
            st.write(item["meaning"])

    # --- State 1: input area ---
    if result is None:
        guess = st.text_input(
            "Your reading (hiragana or romaji):",
            placeholder="e.g. でんしゃ or densha",
            key="guess_input",
            # key= is required when the same widget type appears multiple times
            # in a script, or when you need Streamlit to track its value across reruns.
        )

        # st.columns splits the row into equal-width sections.
        # [1, 1] means two columns of equal width.
        col1, col2 = st.columns([1, 1])
        with col1:
            if st.button("Submit", use_container_width=True, type="primary"):
                if guess.strip():
                    _submit_guess(guess.strip())
                    st.rerun()
                else:
                    st.warning("Type a reading before submitting.")
        with col2:
            if st.button("Skip", use_container_width=True):
                _load_new_item()
                st.rerun()

    # --- State 2: result area ---
    else:
        # closeness comes from the backend's measure_closeness() in services/quiz.py.
        # It drives both the color of the feedback banner and the tone of Claude's explanation.
        closeness = result.get("closeness", "off")
        reading = item["reading"]

        if closeness == "correct":
            st.success(f"正解! The reading is {reading}")
        elif closeness == "very_close":
            st.warning(f"惜しい! So close -- the reading is {reading}")
        elif closeness == "close":
            st.warning(f"Almost there. The reading is {reading}")
        else:
            st.error(f"Not quite. The correct reading is {reading}")

        st.divider()
        # Claude's explanation is plain markdown text -- st.markdown renders
        # headers, bold, bullet lists, etc. automatically.
        st.markdown(result["explanation"])
        st.divider()

        if st.button("Next compound", use_container_width=True, type="primary"):
            _load_new_item()
            st.rerun()


if __name__ == "__main__":
    main()

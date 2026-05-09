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

# Overridden by an environment variable in deployment (Milestone 6)
# so the frontend knows where the deployed backend lives.
API_BASE_URL = os.environ.get("API_BASE_URL", "http://localhost:8000")


# ---------------------------------------------------------------------------
# Session state helpers
# ---------------------------------------------------------------------------

def _init_state() -> None:
    """Set session state keys on first load only. Safe to call on every rerun."""
    if "current_item" not in st.session_state:
        st.session_state.current_item = None
    if "result" not in st.session_state:
        st.session_state.result = None
    if "wanikani_token" not in st.session_state:
        st.session_state.wanikani_token = ""


def _load_new_item() -> None:
    """
    Fetch a random quiz item from the backend and reset result state.

    Passes the WaniKani token as a query parameter if one is set.
    The backend uses it to draw from WaniKani vocabulary; without it,
    falls back to the hardcoded N4 list.

    The first call with a new token will be slow (~2-5s) while the backend
    fetches and caches the WaniKani subjects. Subsequent calls are fast.
    """
    token = st.session_state.wanikani_token
    params = {"wanikani_token": token} if token else {}

    try:
        response = requests.get(
            f"{API_BASE_URL}/quiz/item",
            params=params,
            timeout=20,  # extra time for first WaniKani fetch
        )
        response.raise_for_status()
        st.session_state.current_item = response.json()
        st.session_state.result = None
    except requests.exceptions.ConnectionError:
        st.error("Cannot reach the backend. Is `uvicorn backend.main:app --reload` running?")
        st.stop()


def _submit_guess(guess: str) -> None:
    """POST the guess to /quiz/explain and store the result in session state."""
    item = st.session_state.current_item
    try:
        response = requests.post(
            f"{API_BASE_URL}/quiz/explain",
            json={
                "characters": item["characters"],
                "reading": item["reading"],
                "accepted_readings": item["accepted_readings"],
                "guess": guess,
                "subject_type": item.get("subject_type", "vocabulary"),
            },
            timeout=30,  # Claude needs time to respond
        )
        response.raise_for_status()
        st.session_state.result = response.json()
    except requests.exceptions.ConnectionError:
        st.error("Cannot reach the backend. Is `uvicorn backend.main:app --reload` running?")
        st.stop()


def _render_sidebar() -> None:
    """
    Render the WaniKani token input in the sidebar.

    type="password" masks the token so it's not visible on screen.
    When the token changes, current_item is cleared to force a fresh
    fetch from WaniKani with the new token on the next round.
    """
    with st.sidebar:
        st.header("WaniKani")
        st.caption(
            "Paste a read-only API token from "
            "[wanikani.com/settings/personal_access_tokens]"
            "(https://www.wanikani.com/settings/personal_access_tokens) "
            "to drill your current level's vocabulary."
        )

        token = st.text_input(
            "API Token",
            type="password",
            placeholder="Paste your token here",
            key="token_input",
        )

        # If the token has changed, clear the current item so the next
        # load picks from the new source (WaniKani or hardcoded fallback).
        if token != st.session_state.wanikani_token:
            st.session_state.wanikani_token = token
            st.session_state.current_item = None
            st.session_state.result = None

        st.divider()

        if st.session_state.wanikani_token:
            st.success("Using your WaniKani vocabulary")
        else:
            st.info("Using hardcoded N4 fallback")


# ---------------------------------------------------------------------------
# UI
# ---------------------------------------------------------------------------

def main() -> None:
    """
    Main UI function, called on every rerun.

    Two states driven by st.session_state.result:
      None     -- show compound, input field, Submit + Skip
      not None -- show closeness feedback, Claude's explanation, Next button
    """
    st.set_page_config(page_title="Jouzu", page_icon="上", layout="centered")
    _init_state()
    _render_sidebar()

    st.title("Jouzu 上手")
    st.caption("Kanji reading drill -- learn the patterns, not just the answers.")

    if st.session_state.current_item is None:
        with st.spinner("Fetching vocabulary..."):
            _load_new_item()

    item = st.session_state.current_item
    result = st.session_state.result

    # Color matches WaniKani: pink for kanji, purple for vocabulary.
    subject_type = item.get("subject_type", "vocabulary")
    color = "#f02049" if subject_type == "kanji" else "#9820f0"

    st.markdown(
        f"<h1 style='text-align:center; font-size:4rem; color:{color};'>"
        f"{item['characters']}</h1>",
        unsafe_allow_html=True,
    )
    st.markdown(
        f"<p style='text-align:center; color:gray; font-size:0.85rem;'>"
        f"{subject_type}</p>",
        unsafe_allow_html=True,
    )

    # Hide meaning behind expander before submission; show it plainly after.
    if result:
        st.markdown(
            f"<p style='text-align:center; color:gray;'>{item['meaning']}</p>",
            unsafe_allow_html=True,
        )
    else:
        with st.expander("Show meaning"):
            st.write(item["meaning"])

    # --- State 1: input ---
    if result is None:
        guess = st.text_input(
            "Your reading (hiragana or romaji):",
            placeholder="e.g. でんしゃ or densha",
            key="guess_input",
        )

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

    # --- State 2: result ---
    else:
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
        st.markdown(result["explanation"])
        st.divider()

        if st.button("Next compound", use_container_width=True, type="primary"):
            _load_new_item()
            st.rerun()


if __name__ == "__main__":
    main()

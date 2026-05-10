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

# Source options shown in the dropdown.
# Keys match the source parameter the backend expects.
SOURCE_OPTIONS = {
    "current_level": "WaniKani current level",
    "all_reviewed":  "WaniKani all reviewed",
    "fallback":      "N4 fallback",
    "custom":        "Upload your own",
}

# Human-readable labels for pattern codes returned by Claude.
PATTERN_LABELS: dict[str, str] = {
    "on+on":     "On+On (both on'yomi)",
    "kun+kun":   "Kun+Kun (both kun'yomi)",
    "on+kun":    "On+Kun (yutou-yomi)",
    "kun+on":    "Kun+On (juubako-yomi)",
    "irregular": "Irregular",
    "single":    "Single kanji",
    "mixed":     "Mixed (3+ kanji)",
}


# ---------------------------------------------------------------------------
# Session state helpers
# ---------------------------------------------------------------------------

def _fresh_session_stats() -> dict:
    """Return a clean session stats dict for a new session."""
    return {
        "attempted": 0,
        "correct": 0,
        "pattern_hits": {},
        "pattern_misses": {},
        "missed_compounds": [],
        "stats_updated": False,
    }


def _init_state() -> None:
    """Set session state keys on first load only. Safe to call on every rerun."""
    if "current_item" not in st.session_state:
        st.session_state.current_item = None
    if "result" not in st.session_state:
        st.session_state.result = None
    if "wanikani_token" not in st.session_state:
        st.session_state.wanikani_token = ""
    if "hint" not in st.session_state:
        st.session_state.hint = None
    if "session_stats" not in st.session_state:
        st.session_state.session_stats = _fresh_session_stats()
    if "source" not in st.session_state:
        st.session_state.source = "fallback"
    if "session_id" not in st.session_state:
        st.session_state.session_id = None


def _reset_session() -> None:
    """
    Reset all quiz and stats state. Called when token or source changes.

    A token change means a different WaniKani account. A source change means
    a different item pool. Either way, mixing old session stats with new items
    would be misleading.
    """
    st.session_state.current_item = None
    st.session_state.result = None
    st.session_state.hint = None
    st.session_state.session_stats = _fresh_session_stats()


def _load_new_item() -> None:
    """
    Fetch a random quiz item from the backend and reset result and hint state.

    Passes wanikani_token, source, and session_id as query parameters.
    The backend routes to the correct source and returns a random item.
    The first call with a new WaniKani token will be slow while the backend
    fetches and caches subjects and review stats.
    """
    params: dict = {"source": st.session_state.source}

    if st.session_state.wanikani_token:
        params["wanikani_token"] = st.session_state.wanikani_token

    if st.session_state.session_id:
        params["session_id"] = st.session_state.session_id

    try:
        response = requests.get(
            f"{API_BASE_URL}/quiz/item",
            params=params,
            timeout=20,
        )
        response.raise_for_status()
        st.session_state.current_item = response.json()
        st.session_state.result = None
        st.session_state.hint = None
        st.session_state.session_stats["stats_updated"] = False
    except requests.exceptions.ConnectionError:
        st.error("Cannot reach the backend. Is `uvicorn backend.main:app --reload` running?")
        st.stop()


def _submit_guess(guess: str) -> None:
    """POST the guess to /quiz/explain and store the result in session state."""
    item = st.session_state.current_item
    token = st.session_state.wanikani_token
    try:
        response = requests.post(
            f"{API_BASE_URL}/quiz/explain",
            json={
                "characters": item["characters"],
                "reading": item["reading"],
                "accepted_readings": item["accepted_readings"],
                "guess": guess,
                "subject_type": item.get("subject_type", "vocabulary"),
                "reading_mnemonic": item.get("reading_mnemonic"),
                "wanikani_token": token if token else None,
            },
            timeout=30,
        )
        response.raise_for_status()
        st.session_state.result = response.json()
    except requests.exceptions.ConnectionError:
        st.error("Cannot reach the backend. Is `uvicorn backend.main:app --reload` running?")
        st.stop()


def _fetch_hint() -> None:
    """POST to /quiz/hint and store the hint text in session state."""
    item = st.session_state.current_item
    try:
        response = requests.post(
            f"{API_BASE_URL}/quiz/hint",
            json={
                "characters": item["characters"],
                "meaning": item["meaning"],
                "subject_type": item.get("subject_type", "vocabulary"),
                "reading_mnemonic": item.get("reading_mnemonic"),
            },
            timeout=15,
        )
        response.raise_for_status()
        st.session_state.hint = response.json()["hint"]
    except requests.exceptions.ConnectionError:
        st.error("Cannot reach the backend. Is `uvicorn backend.main:app --reload` running?")
        st.stop()


def _upload_csv(file) -> None:
    """
    POST an uploaded CSV file to /quiz/upload and store the returned session_id.

    The session_id is then passed on every GET /quiz/item call so the backend
    knows which custom deck to draw from.
    """
    try:
        response = requests.post(
            f"{API_BASE_URL}/quiz/upload",
            files={"file": (file.name, file.getvalue(), "text/csv")},
            timeout=10,
        )
        response.raise_for_status()
        data = response.json()
        st.session_state.session_id = data["session_id"]
        st.success(f"Uploaded {data['item_count']} compounds.")
        _reset_session()
    except requests.exceptions.HTTPError as exc:
        st.error(f"Upload failed: {exc.response.json().get('detail', 'Unknown error')}")
    except requests.exceptions.ConnectionError:
        st.error("Cannot reach the backend. Is `uvicorn backend.main:app --reload` running?")


def _update_session_stats(item: dict, result: dict) -> None:
    """
    Update session stats after a submission. Called once per round via the
    stats_updated guard to prevent double-counting on Streamlit reruns.
    """
    if st.session_state.session_stats["stats_updated"]:
        return

    stats = st.session_state.session_stats
    pattern = result.get("pattern")

    stats["attempted"] += 1

    if result["is_correct"]:
        stats["correct"] += 1
        if pattern:
            stats["pattern_hits"][pattern] = stats["pattern_hits"].get(pattern, 0) + 1
    else:
        if pattern:
            stats["pattern_misses"][pattern] = stats["pattern_misses"].get(pattern, 0) + 1
        stats["missed_compounds"].append(item["characters"])

    stats["stats_updated"] = True


# ---------------------------------------------------------------------------
# Sidebar
# ---------------------------------------------------------------------------

def _render_sidebar() -> None:
    """
    Render the sidebar: WaniKani settings, source selection, and session stats.

    WaniKani settings collapse once a token is set. Source dropdown sits below.
    File uploader appears only when 'custom' source is selected.
    """
    with st.sidebar:

        # WaniKani Settings -- collapses once token is set.
        with st.expander(
            "WaniKani Settings",
            expanded=not bool(st.session_state.wanikani_token),
        ):
            st.caption(
                "Paste a read-only API token from "
                "[wanikani.com/settings/personal_access_tokens]"
                "(https://www.wanikani.com/settings/personal_access_tokens)."
            )
            token = st.text_input(
                "API Token",
                type="password",
                placeholder="Paste your token here",
                key="token_input",
            )
            if token != st.session_state.wanikani_token:
                st.session_state.wanikani_token = token
                # Reset to fallback if WaniKani token is removed.
                if not token and st.session_state.source in ("current_level", "all_reviewed"):
                    st.session_state.source = "fallback"
                _reset_session()

        if st.session_state.wanikani_token:
            st.success("Connected to WaniKani")
        else:
            st.info("No WaniKani token -- WaniKani sources unavailable")

        st.divider()

        # Source selection dropdown.
        # WaniKani sources are disabled (shown but won't work) without a token.
        has_token = bool(st.session_state.wanikani_token)
        available_sources = {
            k: v + (" ⚠ token required" if k in ("current_level", "all_reviewed") and not has_token else "")
            for k, v in SOURCE_OPTIONS.items()
        }

        selected_label = st.selectbox(
            "Quiz source",
            options=list(available_sources.values()),
            index=list(available_sources.keys()).index(st.session_state.source),
        )
        selected_source = [k for k, v in available_sources.items() if v == selected_label][0]

        if selected_source != st.session_state.source:
            st.session_state.source = selected_source
            st.session_state.session_id = None
            _reset_session()

        # File uploader -- only shown when custom source is selected.
        if st.session_state.source == "custom":
            st.caption(
                "Upload a CSV with columns: `characters`, `reading`, `meaning`. "
                "Save the file as UTF-8 encoding. "
                "Bogus readings, non-Japanese characters, or wrong meanings will produce "
                "inaccurate Claude explanations -- garbage in, garbage out."
            )
            uploaded = st.file_uploader("Choose a CSV file", type="csv")
            # Only upload when a new file arrives. Streamlit reruns the script
            # on every interaction -- comparing name and size guards against
            # re-uploading the same file on each rerun. React won't need this
            # guard since it only fires the upload event once naturally.
            if uploaded:
                file_key = f"{uploaded.name}:{uploaded.size}"
                if st.session_state.get("last_uploaded_key") != file_key:
                    st.session_state.last_uploaded_key = file_key
                    _upload_csv(uploaded)

        st.divider()

        # Session stats -- shown once the user has attempted something.
        stats = st.session_state.session_stats
        if stats["attempted"] > 0:
            st.subheader("This Session")

            accuracy = stats["correct"] / stats["attempted"] * 100
            col1, col2 = st.columns(2)
            col1.metric("Attempted", stats["attempted"])
            col2.metric("Accuracy", f"{accuracy:.0f}%")

            all_patterns = set(
                list(stats["pattern_hits"].keys()) +
                list(stats["pattern_misses"].keys())
            )
            if all_patterns:
                st.markdown("**Patterns**")
                for pattern in sorted(all_patterns):
                    hits = stats["pattern_hits"].get(pattern, 0)
                    misses = stats["pattern_misses"].get(pattern, 0)
                    total = hits + misses
                    label = PATTERN_LABELS.get(pattern, pattern)
                    accuracy_pct = int(hits / total * 100) if total else 0
                    icon = "✓" if misses == 0 else ("⚠" if hits > 0 else "✗")
                    st.markdown(f"{icon} **{label}** {hits}/{total} ({accuracy_pct}%)")

            if stats["missed_compounds"]:
                st.markdown("**Missed this session**")
                st.markdown("、".join(stats["missed_compounds"]))


# ---------------------------------------------------------------------------
# UI
# ---------------------------------------------------------------------------

def main() -> None:
    """
    Main UI function, called on every rerun.

    Two states driven by st.session_state.result:
      None     -- show compound, input field, Hint + Submit + Skip
      not None -- show closeness feedback, Claude's explanation,
                  WaniKani stats, mnemonics, Next button
    """
    st.set_page_config(page_title="Jouzu", page_icon="上", layout="centered")
    _init_state()
    _render_sidebar()

    st.title("Jouzu 上手")
    st.caption("Kanji reading drill -- learn the patterns, not just the answers.")
    st.caption("⚠ Powered by Claude (Anthropic). Explanations may occasionally be inaccurate -- treat them as a study aid, not a dictionary.")

    # Warn if a WaniKani source is selected without a token.
    if st.session_state.source in ("current_level", "all_reviewed") and not st.session_state.wanikani_token:
        st.warning("A WaniKani token is required for this source. Add one in the sidebar or switch to N4 fallback.")
        st.stop()

    # Warn if custom source is selected but no file has been uploaded yet.
    if st.session_state.source == "custom" and not st.session_state.session_id:
        st.info("Upload a CSV file in the sidebar to start drilling your own deck.")
        st.stop()

    if st.session_state.current_item is None:
        with st.spinner("Fetching vocabulary..."):
            _load_new_item()

    item = st.session_state.current_item
    result = st.session_state.result

    if result is not None:
        _update_session_stats(item, result)

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
        st.caption("Type in hiragana or romaji. If using a Japanese IME, press Enter to confirm hiragana before it converts to kanji.")

        col1, col2, col3 = st.columns([2, 1, 1])
        with col1:
            if st.button("Submit", use_container_width=True, type="primary"):
                if guess.strip():
                    _submit_guess(guess.strip())
                    st.rerun()
                else:
                    st.warning("Type a reading before submitting.")
        with col2:
            if st.button("Hint", use_container_width=True):
                with st.spinner("Thinking..."):
                    _fetch_hint()
                st.rerun()
        with col3:
            if st.button("Skip", use_container_width=True):
                _load_new_item()
                st.rerun()

        if st.session_state.hint:
            st.info(st.session_state.hint)

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

        review_stats = item.get("review_stats")
        if review_stats:
            col1, col2, col3 = st.columns(3)
            col1.metric("WaniKani Accuracy", f"{review_stats['percentage_correct']}%")
            col2.metric("Reading Correct", review_stats["reading_correct"])
            col3.metric("Reading Wrong", review_stats["reading_incorrect"])

        st.divider()
        st.markdown(result["explanation"])

        if item.get("reading_mnemonic"):
            with st.expander("WaniKani reading mnemonic"):
                st.write(item["reading_mnemonic"])

        if item.get("meaning_mnemonic"):
            with st.expander("WaniKani meaning mnemonic"):
                st.write(item["meaning_mnemonic"])

        st.divider()

        if st.button("Next compound", use_container_width=True, type="primary"):
            _load_new_item()
            st.rerun()


if __name__ == "__main__":
    main()

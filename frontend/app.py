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
import uuid

import requests
import streamlit as st

API_BASE_URL = os.environ.get("API_BASE_URL", "http://localhost:8000")

# Available queue modes per source.
# Keeps the frontend and backend restriction logic in sync.
MODES_BY_SOURCE: dict[str, list[str]] = {
    "current_level": ["Random", "Shuffle", "Sequential", "Mini-batch", "Weighted"],
    "all_reviewed":  ["Random", "Shuffle", "Mini-batch"],
    "fallback":      ["Random", "Shuffle", "Sequential"],
    "custom":        ["Random", "Shuffle", "Sequential", "Mini-batch", "Weighted"],
}

# Maps display labels to backend mode keys.
MODE_KEYS: dict[str, str] = {
    "Random":     "random",
    "Shuffle":    "shuffle",
    "Sequential": "sequential",
    "Mini-batch": "mini-batch",
    "Weighted":   "weighted",
}

SOURCE_OPTIONS: dict[str, str] = {
    "current_level": "WaniKani current level",
    "all_reviewed":  "WaniKani all reviewed",
    "fallback":      "N4 fallback",
    "custom":        "Upload your own",
}

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
    if "queue_session_id" not in st.session_state:
        # UUID generated once per browser session. Identifies this user's queue
        # and persists across reruns until the tab is closed.
        st.session_state.queue_session_id = str(uuid.uuid4())
    if "upload_session_id" not in st.session_state:
        st.session_state.upload_session_id = None
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
    if "queue_mode" not in st.session_state:
        st.session_state.queue_mode = "Shuffle"
    if "batch_size" not in st.session_state:
        st.session_state.batch_size = 10


def _reset_session() -> None:
    """Reset quiz and stats state. Called on token, source, or mode change."""
    st.session_state.current_item = None
    st.session_state.result = None
    st.session_state.hint = None
    st.session_state.session_stats = _fresh_session_stats()


# ---------------------------------------------------------------------------
# Backend calls
# ---------------------------------------------------------------------------

def _load_new_item() -> None:
    """Fetch the next quiz item from the backend using the active queue."""
    params: dict = {
        "source": st.session_state.source,
        "queue_session_id": st.session_state.queue_session_id,
    }
    if st.session_state.wanikani_token:
        params["wanikani_token"] = st.session_state.wanikani_token
    if st.session_state.upload_session_id:
        params["upload_session_id"] = st.session_state.upload_session_id

    try:
        response = requests.get(
            f"{API_BASE_URL}/quiz/item", params=params, timeout=20
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
    """POST the guess to /quiz/explain and store the result."""
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
    """POST to /quiz/hint and store the hint text."""
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


def _configure_queue(mode_label: str, batch_size: int) -> None:
    """Tell the backend to configure the queue mode and batch size."""
    try:
        requests.post(
            f"{API_BASE_URL}/quiz/queue/configure",
            json={
                "session_id": st.session_state.queue_session_id,
                "mode": MODE_KEYS[mode_label],
                "batch_size": batch_size,
                "source": st.session_state.source,
            },
            timeout=5,
        )
    except requests.exceptions.ConnectionError:
        pass  # Non-critical -- queue will use default mode


def _reset_queue() -> None:
    """Tell the backend to reset queue state for this session."""
    try:
        requests.post(
            f"{API_BASE_URL}/quiz/queue/reset",
            json={"session_id": st.session_state.queue_session_id},
            timeout=5,
        )
    except requests.exceptions.ConnectionError:
        pass


def _record_result(characters: str, correct: bool) -> None:
    """
    Fire-and-forget result recording for weighted mode adjustment.

    Failures are silently ignored -- this is a best-effort call that
    only matters in weighted mode and is non-critical if it fails.
    """
    try:
        requests.post(
            f"{API_BASE_URL}/quiz/queue/result",
            json={
                "session_id": st.session_state.queue_session_id,
                "characters": characters,
                "correct": correct,
            },
            timeout=5,
        )
    except requests.exceptions.ConnectionError:
        pass


def _upload_csv(file) -> None:
    """POST an uploaded CSV file and store the returned upload_session_id."""
    try:
        response = requests.post(
            f"{API_BASE_URL}/quiz/upload",
            files={"file": (file.name, file.getvalue(), "text/csv")},
            timeout=10,
        )
        response.raise_for_status()
        data = response.json()
        st.session_state.upload_session_id = data["session_id"]
        st.success(f"Uploaded {data['item_count']} compounds.")
        _reset_session()
        _reset_queue()
    except requests.exceptions.HTTPError as exc:
        st.error(f"Upload failed: {exc.response.json().get('detail', 'Unknown error')}")
    except requests.exceptions.ConnectionError:
        st.error("Cannot reach the backend. Is `uvicorn backend.main:app --reload` running?")


def _update_session_stats(item: dict, result: dict) -> None:
    """Update session stats once per round using the stats_updated guard."""
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
    _record_result(item["characters"], result["is_correct"])


# ---------------------------------------------------------------------------
# Sidebar
# ---------------------------------------------------------------------------

def _render_sidebar() -> None:
    with st.sidebar:

        # Active source indicator -- always visible, always accurate.
        source_label = SOURCE_OPTIONS.get(st.session_state.source, st.session_state.source)
        st.markdown(f"**Active source:** {source_label}")
        if (
            st.session_state.wanikani_token
            and st.session_state.source not in ("current_level", "all_reviewed")
        ):
            st.caption("WaniKani token set but not used for this source.")

        st.divider()

        # Source Settings expander -- WaniKani token + source dropdown + file upload.
        with st.expander("Source Settings", expanded=False):
            st.caption(
                "WaniKani token from "
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
                if not token and st.session_state.source in ("current_level", "all_reviewed"):
                    st.session_state.source = "fallback"
                _reset_session()
                _reset_queue()

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
                st.session_state.upload_session_id = None
                if st.session_state.queue_mode not in MODES_BY_SOURCE[selected_source]:
                    st.session_state.queue_mode = "Shuffle"
                _reset_session()
                _reset_queue()

            if st.session_state.source == "custom":
                st.caption(
                    "CSV columns: `characters`, `reading`, `meaning`. "
                    "UTF-8 encoding required. Bogus data produces bad explanations."
                )
                uploaded = st.file_uploader("Choose a CSV file", type="csv")
                if uploaded:
                    file_key = f"{uploaded.name}:{uploaded.size}"
                    if st.session_state.get("last_uploaded_key") != file_key:
                        st.session_state.last_uploaded_key = file_key
                        _upload_csv(uploaded)

        # Queue Settings expander -- mode, batch size, reset.
        with st.expander("Queue Settings", expanded=False):
            available_modes = MODES_BY_SOURCE[st.session_state.source]
            if st.session_state.queue_mode not in available_modes:
                st.session_state.queue_mode = "Shuffle"

            selected_mode = st.selectbox(
                "Mode",
                options=available_modes,
                index=available_modes.index(st.session_state.queue_mode),
            )

            batch_size = st.session_state.batch_size
            if selected_mode == "Mini-batch":
                batch_size = st.number_input(
                    "Batch size",
                    min_value=5,
                    max_value=100,
                    value=st.session_state.batch_size,
                    step=1,
                )

            mode_changed = selected_mode != st.session_state.queue_mode
            batch_changed = batch_size != st.session_state.batch_size

            if mode_changed or batch_changed:
                st.session_state.queue_mode = selected_mode
                st.session_state.batch_size = int(batch_size)
                _configure_queue(selected_mode, int(batch_size))
                _reset_session()
                st.session_state.current_item = None

            if st.button("Reset queue", use_container_width=True):
                _reset_queue()
                _reset_session()
                st.session_state.current_item = None
                st.rerun()

        # Session stats
        stats = st.session_state.session_stats
        if stats["attempted"] > 0:
            st.divider()
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
    st.set_page_config(page_title="Jouzu", page_icon="上", layout="centered")
    _init_state()
    _render_sidebar()

    st.title("Jouzu 上手")
    st.caption("Kanji reading drill -- learn the patterns, not just the answers.")
    st.caption("⚠ Powered by Claude (Anthropic). Explanations may occasionally be inaccurate -- treat them as a study aid, not a dictionary.")

    if st.session_state.source in ("current_level", "all_reviewed") and not st.session_state.wanikani_token:
        st.warning("A WaniKani token is required for this source. Add one in the sidebar or switch to N4 fallback.")
        st.stop()

    if st.session_state.source == "custom" and not st.session_state.upload_session_id:
        st.info("Upload a CSV file in the sidebar to start drilling your own deck.")
        st.stop()

    if st.session_state.current_item is None:
        with st.spinner("Fetching vocabulary..."):
            _load_new_item()

    item = st.session_state.current_item
    result = st.session_state.result

    if result is not None:
        _update_session_stats(item, result)

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

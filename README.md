# Jouzu 上手

A personal Japanese study tool I'm building for myself -- and maybe eventually for anyone else who wants it.

I'm studying Japanese seriously. I use WaniKani daily, I'm working through Genki, and I want to actually get good at this language, not just collect SRS streaks. Jouzu started as a kanji reading drill and is slowly becoming the study tool I wish existed. Right now it's focused on reading patterns because that's what I'm personally struggling with, but the plan is to make it a proper one-stop shop for Japanese study.

It's a work in progress. A real one. Not a polished side project -- an evolving tool I actually use and intend to keep building.

---

## What it does right now

You see a kanji compound. You guess the reading (hiragana or romaji). Claude explains why the compound reads the way it does, not just the answer, but the pattern behind it. On'yomi, kun'yomi, irregular readings, related compounds from your own vocabulary list, example sentences, WaniKani mnemonics. The goal is to build intuition, not just memorize.

**Quiz sources:**
- **WaniKani current level** -- drills your active level's vocabulary and kanji
- **WaniKani all reviewed** -- everything you've passed to Guru or above across all levels
- **N4 fallback** -- a built-in deck of 20 N4 compounds, no account needed
- **Upload your own** -- bring a CSV and drill whatever you want

**Queue modes:**
- **Shuffle** -- no repeats until every item is seen, then reshuffles
- **Sequential** -- items in order, loops back to the start
- **Mini-batch** -- drills N items at a time before moving to the next group (configurable, 5-100)
- **Weighted** -- items you miss appear more often, capped at 3x frequency
- **Random** -- pure random, anything goes

**WaniKani integration:**
- Color-coded by subject type (purple for vocabulary, pink for kanji, matching WaniKani)
- WaniKani mnemonics surfaced after each guess
- Lifetime accuracy stats from your WaniKani review history
- Multiple accepted readings for kanji subjects

**Session tracking:**
- Accuracy, pattern breakdown (on+on, kun+kun, mixed etc.), missed compounds

---

## Why WaniKani?

I use WaniKani personally, so it was the natural integration point. But I didn't want this to be a tool that only works if you pay for WaniKani. That's why there's a fallback deck and custom CSV upload- bring your own material and Claude still does the heavy lifting on explanations.

The WaniKani integration is read-only for now. Eventually I want to close the loop: submit reviews back to WaniKani, manage the lesson queue, make Jouzu a full WaniKani client with Claude layered on top. That's on the roadmap.

---

## What's coming

This is genuinely a work in progress. Things I'm planning:

- **React frontend** -- the current Streamlit UI is functional but rough and largely AI-generated. I want to rebuild the frontend in React as a way to actually learn React. Consider the current UI a placeholder.
- **WaniKani write integration** -- submit reviews, start assignments, manage the queue from inside Jouzu
- **Genki integration** -- I'm working through Genki I and want to drill vocabulary and grammar by chapter
- **Persistent history** -- SQLite to track patterns across sessions, not just within one
- **Better CSV tooling** -- import from Anki decks, textbook word lists, etc.
- **Smaller LLMs** -- experimenting with running lighter models locally for offline use or cost reduction

---

## Running locally

**Prerequisites:**
- Python 3.10+
- An Anthropic API key (console.anthropic.com -- separate from claude.ai, requires billing)
- A WaniKani API token (optional, wanikani.com/settings/personal_access_tokens -- read-only is fine (FOR NOW))

**Setup:**

```bash
git clone https://github.com/yourusername/jouzu.git
cd jouzu
python -m venv .venv
source .venv/bin/activate  # Windows: .venv\Scripts\activate
pip install -r requirements.txt
```

Create a `.env` file in the project root:

```
ANTHROPIC_API_KEY=enter-anthropic-key
```

The WaniKani token is not stored server-side -- you paste it in the app sidebar at runtime.

**Run:**

You need two terminals.

Terminal 1 -- backend:
```bash
uvicorn backend.main:app --reload
```

Terminal 2 -- frontend:
```bash
streamlit run frontend/app.py
```

Open `http://localhost:8501` in your browser.

**Sanity check** (optional, confirms your keys work):
```bash
python scripts/sanity_check.py
```

---

## Custom CSV format

Upload your own deck via the sidebar. Three columns required, UTF-8 encoding:

```csv
characters,reading,meaning
天気,てんき,weather
家族,かぞく,family
映画,えいが,movie
```

Claude generates the full explanation from the characters and reading -- meanings are used as hints only.
__Bad readings or non-Japanese characters will produce confused explanations. Garbage in, garbage out.__

---

## Architecture

Interested in the design decisions -- why the backend is stateless, how the queue system works, what the growth path looks like? Read [ARCHITECTURE.md](ARCHITECTURE.md).

---

## Tech stack

- **Backend:** Python, FastAPI
- **Frontend:** Streamlit (temporary -- React rebuild planned)
- **LLM:** Anthropic Claude (`claude-sonnet-4-6`)
- **Data:** WaniKani API v2

---

## Known limitations

- Streamlit UI has some rough edges -- dropdowns can feel slightly buggy due to how Streamlit handles state. This goes away when the React frontend is built.
- No persistence across sessions -- stats and queue state reset when you close the tab
- Doesn't work offline -- depends on Anthropic API and WaniKani API
- No rate limiting on API endpoints -- not recommended to expose publicly without adding that first
- Uploading CSVs with bad data will cause faulty readings and either break the program or make Claude hallucinate. Guards for bad data and adjusting the prompt might be required to counter this
- The app takes 2 - 5 seconds to respond after a guess due to real-time LLM responses, and that's probably here to stay for a while.

---

## On Claude Code and how this was built

This project was built extensively with Claude Code, and I want to be honest about that.

AI is abundant. Choosing not to use it to prove you can write code manually is, in my opinion, missing the point entirely. We're not here to demonstrate we can remember syntax -- we're here to write good software with good architecture. The skill that matters is understanding *why* something is done a certain way. Design, structure, the decisions about what to build and what to leave out -- that's the engineering. The code is the output of that thinking, not the thinking itself. I feel the same way about Japanese: use the tools available, learn through use, get better faster.

This was not AI slop. I had a real problem and a real idea. Every design decision came from me -- the architecture, the queue system, the stateless backend, what goes in v0 and what doesn't. I questioned things, pushed back, and made sure I understood everything that went in. Claude Code generated code. I directed it. That's a valid way to build software in 2026, and I'd rather be honest about it than pretend otherwise.

I also chose Claude specifically for the explanations because I'm not a Japanese expert (yet) -- and Claude turns out to be a genuinely good language teacher. That's not a coincidence, it's the whole point of the tool.

One honest caveat: the app is slow. Claude takes 2-5 seconds to respond after each guess. That's the cost of real-time LLM responses and it's not going away soon. Worth it for the explanation quality, but don't expect instant feedback.

---

## Notes

Powered by Claude (Anthropic). Explanations are generated by an LLM and may occasionally be inaccurate -- treat them as a study aid, not a dictionary.

This project is for personal use and learning. Good luck out there. 頑張って。

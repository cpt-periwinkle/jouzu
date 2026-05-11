#!/bin/bash
# Jouzu launcher script.
# Sets up the environment and starts both the backend and frontend.
# Usage: bash run.sh

set -e

echo ""
echo "  Jouzu 上手 -- Japanese Study Tool"
echo "  =================================="
echo ""

# ---------------------------------------------------------------------------
# Check Python
# ---------------------------------------------------------------------------

if ! command -v python &> /dev/null; then
    echo "ERROR: Python not found. Install Python 3.10+ and try again."
    exit 1
fi

PYTHON_VERSION=$(python -c "import sys; print(sys.version_info.minor)")
if [ "$PYTHON_VERSION" -lt 10 ]; then
    echo "ERROR: Python 3.10+ required. Found Python 3.${PYTHON_VERSION}."
    exit 1
fi

# ---------------------------------------------------------------------------
# Set up .env
# ---------------------------------------------------------------------------

if [ ! -f ".env" ]; then
    echo "No .env file found. Let's set up your API key."
    echo ""
    echo "You need an Anthropic API key to run Jouzu."
    echo "Get one at: https://console.anthropic.com"
    echo ""
    read -rp "Paste your Anthropic API key: " ANTHROPIC_KEY

    if [ -z "$ANTHROPIC_KEY" ]; then
        echo "ERROR: Anthropic API key is required. Exiting."
        exit 1
    fi

    echo "ANTHROPIC_API_KEY=${ANTHROPIC_KEY}" > .env
    echo ""
    echo ".env created."
else
    echo "Found existing .env file."
fi

# ---------------------------------------------------------------------------
# Install dependencies
# ---------------------------------------------------------------------------

echo ""
echo "Checking dependencies..."

if ! python -c "import fastapi" &> /dev/null; then
    echo "Installing dependencies..."
    pip install -r requirements.txt --quiet
    echo "Dependencies installed."
else
    echo "Dependencies already installed."
fi

# ---------------------------------------------------------------------------
# Start backend
# ---------------------------------------------------------------------------

echo ""
echo "Starting backend on http://localhost:8000 ..."
uvicorn backend.main:app --host 0.0.0.0 --port 8000 &
BACKEND_PID=$!

# Give the backend a moment to start before launching the frontend.
sleep 2

# Verify backend started successfully.
if ! kill -0 $BACKEND_PID 2>/dev/null; then
    echo "ERROR: Backend failed to start. Check the output above."
    exit 1
fi

echo "Backend running (PID ${BACKEND_PID})."

# ---------------------------------------------------------------------------
# Cleanup on exit
# ---------------------------------------------------------------------------

# When the user presses Ctrl+C, kill the background backend process.
cleanup() {
    echo ""
    echo "Shutting down..."
    kill $BACKEND_PID 2>/dev/null
    echo "Done. またね!"
    exit 0
}
trap cleanup SIGINT SIGTERM

# ---------------------------------------------------------------------------
# Start frontend
# ---------------------------------------------------------------------------

echo ""
echo "Starting frontend..."
echo "Open http://localhost:8501 in your browser."
echo ""
echo "WaniKani token (optional): paste it in the sidebar after the app loads."
echo "It improves Jouzu significantly -- get one at wanikani.com/settings/personal_access_tokens"
echo ""
echo "Press Ctrl+C to stop."
echo ""

streamlit run frontend/app.py --server.headless true

# If streamlit exits normally, also kill the backend.
cleanup

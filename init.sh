#!/usr/bin/env bash
# Create the venv (if missing), install requirements, and activate it.
# Must be SOURCED, not executed, so activation persists in your shell:
#     source init.sh
#   or
#     . init.sh

VENV_DIR="venv"

if [ ! -d "$VENV_DIR" ]; then
    echo "Creating virtual environment in $VENV_DIR..."
    python3 -m venv "$VENV_DIR"
else
    echo "Virtual environment $VENV_DIR already exists."
fi

# shellcheck disable=SC1091
source "$VENV_DIR/bin/activate"

if [ -f requirements.txt ]; then
    echo "Installing dependencies from requirements.txt..."
    pip install --upgrade pip
    pip install -r requirements.txt
fi

echo "Done. Virtual environment is active. Run 'deactivate' to exit."

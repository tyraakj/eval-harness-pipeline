#!/bin/bash
# LangGraph Evaluation Harness - One-Line Installer for macOS/Linux
# Usage: curl -LsSf https://raw.githubusercontent.com/tyraakj/eval-harness-pipeline/main/install.sh | bash

set -e

INSTALL_PATH="${HOME}/personal-evaluation-harness"

echo "Installing Glyph..."

# Check if uv is installed
if ! command -v uv &> /dev/null; then
    echo "Installing uv (Python package manager)..."
    curl -LsSf https://astral.sh/uv/install.sh | sh
    export PATH="$HOME/.local/bin:$PATH"
fi

# Clone or update the repository
if [ -d "$INSTALL_PATH" ]; then
    echo "Updating existing installation..."
    cd "$INSTALL_PATH"
    git pull
else
    echo "Cloning repository to $INSTALL_PATH..."
    git clone https://github.com/tyraakj/eval-harness-pipeline.git "$INSTALL_PATH"
    cd "$INSTALL_PATH"
fi

# Install dependencies
echo "Installing dependencies..."
uv sync --all-extras

# Create the user-level glyph launcher. uv's tool bin is normally added by the
# uv installer; print the exact directory when a shell restart is needed.
uv tool install --editable "$INSTALL_PATH" --force
TOOL_BIN="$(uv tool dir --bin)"

echo "Installation complete!"
echo "Open a new terminal, then run:"
echo "   glyph guide"
echo "   glyph run --factory examples.simple_graph:create_evaluation --dataset datasets/example.jsonl --output artifacts/example.jsonl"
echo "If glyph is not found, add this directory to PATH: $TOOL_BIN"

#!/bin/bash
# LangGraph Evaluation Harness - One-Line Installer for macOS/Linux
# Usage: curl -LsSf https://raw.githubusercontent.com/tyraakj/eval-harness-pipeline/main/install.sh | bash

set -e

INSTALL_PATH="${HOME}/personal-evaluation-harness"

echo "🚀 Installing LangGraph Evaluation Harness..."

# Check if uv is installed
if ! command -v uv &> /dev/null; then
    echo "📦 Installing uv (Python package manager)..."
    curl -LsSf https://astral.sh/uv/install.sh | sh
    export PATH="$HOME/.local/bin:$PATH"
fi

# Clone or update the repository
if [ -d "$INSTALL_PATH" ]; then
    echo "📁 Updating existing installation..."
    cd "$INSTALL_PATH"
    git pull
else
    echo "📁 Cloning repository to $INSTALL_PATH..."
    git clone https://github.com/tyraakj/eval-harness-pipeline.git "$INSTALL_PATH"
    cd "$INSTALL_PATH"
fi

# Install dependencies
echo "🔧 Installing dependencies..."
uv sync --all-extras
uv lock

echo "✅ Installation complete!"
echo "🎯 You can now run the evaluation with:"
echo "   cd $INSTALL_PATH"
echo "   uv run lg-eval run --factory examples.simple_graph:create_evaluation --dataset datasets/example.jsonl --output artifacts/example.jsonl --minimum-pass-rate 1.0"

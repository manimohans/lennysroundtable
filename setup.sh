#!/bin/bash
set -e

echo "🎙️ Setting up Lenny's Roundtable..."

# Check for uv
if ! command -v uv &> /dev/null; then
    echo "📦 Installing uv..."
    curl -LsSf https://astral.sh/uv/install.sh | sh
    export PATH="$HOME/.cargo/bin:$PATH"
fi

# Check for ollama
if ! command -v ollama &> /dev/null; then
    echo "❌ Ollama not found. Please install from https://ollama.ai/"
    echo "   Then run this script again."
    exit 1
fi

# Install Python dependencies
echo "📦 Installing Python dependencies..."
uv sync

# Pull Ollama models
echo "🤖 Pulling Ollama models (this may take a while)..."
ollama pull nomic-embed-text
ollama pull llama3.2

# Check for transcripts
if [ ! -d "transcripts" ] || [ -z "$(ls -A transcripts/*.txt 2>/dev/null)" ]; then
    echo "⚠️  No transcripts found in transcripts/ directory"
    echo "   Add your .txt transcript files and run:"
    echo "   uv run python -m roundtable.ingest"
else
    echo "📄 Found transcripts. Indexing..."
    uv run python -m roundtable.ingest
fi

echo ""
echo "✅ Setup complete!"
echo ""
echo "To start the app, run:"
echo "  uv run streamlit run roundtable/app.py"

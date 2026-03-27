#!/bin/bash
set -e

echo "🎙️ Setting up Lenny's Roundtable..."

# Detect embedding provider (default: ollama)
EMBEDDING_PROVIDER="${EMBEDDING_PROVIDER:-ollama}"

# Check for uv
if ! command -v uv &> /dev/null; then
    echo "📦 Installing uv..."
    curl -LsSf https://astral.sh/uv/install.sh | sh
    export PATH="$HOME/.cargo/bin:$PATH"
fi

if [ "$EMBEDDING_PROVIDER" = "openai" ]; then
    if [ -z "$OPENAI_API_KEY" ]; then
        echo "❌ OPENAI_API_KEY is required when EMBEDDING_PROVIDER=openai"
        exit 1
    fi
    echo "✅ Using OpenAI embeddings (text-embedding-3-small)"
else
    # Check for ollama
    if ! command -v ollama &> /dev/null; then
        echo "❌ Ollama not found. Please install from https://ollama.ai/"
        echo "   Alternatively, set EMBEDDING_PROVIDER=openai and OPENAI_API_KEY to skip Ollama."
        exit 1
    fi
fi

# Install Python dependencies
echo "📦 Installing Python dependencies..."
uv sync

if [ "$EMBEDDING_PROVIDER" != "openai" ]; then
    # Pull Ollama models
    echo "🤖 Pulling Ollama models (this may take a while)..."
    ollama pull nomic-embed-text
    ollama pull llama3.2
fi

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

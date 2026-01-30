# Lenny's Roundtable

A RAG-powered app where podcast guests answer your questions based on what they actually said on Lenny's Podcast, then discuss with each other.

## What You Get

- **300+ transcripts** from Lenny's Podcast, pre-embedded and ready to query
- **292 unique speakers** including product leaders from Stripe, Netflix, Airbnb, and more
- **Multi-round discussions** where experts build on each other's perspectives

## Quick Start (5 minutes)

The repo includes pre-embedded transcripts using `embeddinggemma`. Just configure your LLM and go.

### Step 1: Clone and install

```bash
git clone https://github.com/yourusername/lennys-roundtable.git
cd lennys-roundtable
uv sync
```

### Step 2: Configure your LLM

Copy the example config:

```bash
cp .env.example .env
```

Edit `.env` with your provider:

<details>
<summary><b>Option A: Ollama (Local, Free)</b></summary>

1. Install [Ollama](https://ollama.ai/)
2. Pull a model: `ollama pull gemma3:4b` (or any model you prefer)
3. Set in `.env`:
   ```
   LLM_BASE_URL=http://localhost:11434/v1
   LLM_MODEL=gemma3:4b
   LLM_API_KEY=not-needed
   ```
</details>

<details>
<summary><b>Option B: LM Studio (Local, Free)</b></summary>

1. Install [LM Studio](https://lmstudio.ai/)
2. Download a model and start the local server
3. Set in `.env`:
   ```
   LLM_BASE_URL=http://localhost:1234/v1
   LLM_MODEL=your-loaded-model-name
   LLM_API_KEY=not-needed
   ```
</details>

<details>
<summary><b>Option C: OpenAI (Cloud, Paid)</b></summary>

1. Get an API key from [OpenAI](https://platform.openai.com/api-keys)
2. Set in `.env`:
   ```
   LLM_BASE_URL=https://api.openai.com/v1
   LLM_MODEL=gpt-4o-mini
   LLM_API_KEY=sk-your-api-key-here
   ```
</details>

### Step 3: Run the app

```bash
uv run streamlit run roundtable/app.py
```

Open http://localhost:8501

---

## How to Use the App

### 1. Enter your details

- **Your Name**: How speakers will address you (default: "PM")
- **Your Question**: Ask anything about product, startups, leadership, etc.

### 2. Adjust settings (sidebar)

| Setting | Description |
|---------|-------------|
| Discussion Rounds | How many rounds of back-and-forth (1-5) |
| Number of Experts | How many speakers to include (3-7) |
| Response Length | 1=brief, 5=detailed |

### 3. Generate and read

Click **Generate Discussion** and watch:
1. **Initial Thoughts** - Each expert shares their perspective
2. **Round 2+** - Experts respond to each other, agree/disagree, add nuance

### 4. Save your discussion

Click **Save as Markdown** to download the full conversation.

---

## Advanced: Sync Latest Transcripts

Want to update with the newest podcast episodes? You'll need to re-embed after syncing.

### Step 1: Get Dropbox access

1. Go to https://www.dropbox.com/developers/apps
2. Create an app with "scoped access" and "full Dropbox"
3. In Permissions tab, enable: `sharing.read`, `files.content.read`
4. Generate an access token
5. Add to `.env`:
   ```
   DROPBOX_ACCESS_TOKEN=your_token_here
   ```

### Step 2: Sync transcripts

```bash
uv run python sync_transcripts.py
```

### Step 3: Re-embed (required after sync)

```bash
# Make sure Ollama is running with embeddinggemma
ollama pull embeddinggemma

# Re-run ingestion
uv run python -m roundtable.ingest --reset
```

This takes ~50 minutes for 300 transcripts on CPU.

---

## Architecture

### RAG Pipeline

```
User Question
     │
     ▼
┌─────────────────────────────────────┐
│  Embed query (embeddinggemma)       │
│  Search child chunks (512 chars)    │
│  Return parent chunks (2048 chars)  │
│  Rank speakers by relevance         │
└─────────────────────────────────────┘
     │
     ▼
┌─────────────────────────────────────┐
│  Generate responses (your LLM)      │
│  Stream to UI                       │
│  Build on previous responses        │
└─────────────────────────────────────┘
```

### Parent-Child Retrieval

We use a two-tier chunking strategy:
- **Child chunks (512 chars)**: Small pieces for precise semantic matching
- **Parent chunks (2048 chars)**: Larger coherent chunks returned to the LLM

This gives you accurate retrieval AND rich context.

### Embeddings

The included `chroma_db/` was embedded using **`embeddinggemma`** via Ollama. If you re-embed, use the same model for consistency:

```bash
ollama pull embeddinggemma
```

---

## Project Structure

```
lennys-roundtable/
├── roundtable/
│   ├── app.py           # Streamlit UI
│   ├── generator.py     # LLM response generation
│   ├── retriever.py     # Semantic search & ranking
│   ├── ingest.py        # Embedding pipeline
│   └── parser.py        # Transcript parsing
├── transcripts/         # 300+ podcast transcripts
├── chroma_db/           # Pre-embedded vectors (ready to use)
├── .env.example         # Configuration template
└── sync_transcripts.py  # Fetch new episodes
```

---

## Configuration Reference

### LLM Settings (`.env`)

| Variable | Description | Example |
|----------|-------------|---------|
| `LLM_BASE_URL` | API endpoint | `http://localhost:11434/v1` |
| `LLM_MODEL` | Model name | `gemma3:4b` |
| `LLM_API_KEY` | API key (if needed) | `not-needed` or `sk-...` |

### Embedding Settings (`roundtable/ingest.py`)

| Variable | Default | Description |
|----------|---------|-------------|
| `EMBEDDING_MODEL` | `embeddinggemma` | Ollama embedding model |
| `CHILD_CHUNK_SIZE` | 512 | Smaller = more precise matching |
| `PARENT_CHUNK_SIZE` | 2048 | Larger = more context for LLM |

---

## Troubleshooting

**"No relevant speakers found"**
- The `chroma_db/` folder may be missing or corrupted
- Re-run: `uv run python -m roundtable.ingest --reset`

**"Connection refused" errors**
- Make sure your LLM provider is running (Ollama/LM Studio)
- Check the `LLM_BASE_URL` in `.env`

**Responses are generic or hallucinated**
- Try a larger/better model
- The included embeddings work best with `embeddinggemma`

**Slow generation**
- Local models depend on your hardware
- Try a smaller model like `gemma3:1b` or use OpenAI

---

## Tech Stack

- **RAG Framework**: [LlamaIndex](https://www.llamaindex.ai/)
- **Vector Store**: [ChromaDB](https://www.trychroma.com/)
- **Embeddings**: `embeddinggemma` via Ollama
- **LLM**: Any OpenAI-compatible API
- **UI**: [Streamlit](https://streamlit.io/)
- **Package Manager**: [uv](https://docs.astral.sh/uv/)

---

## License

MIT

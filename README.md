# Lenny's Roundtable

A RAG-powered app where podcast guests answer your questions based on what they actually said on Lenny's Podcast, then discuss with each other.

## What You Get

- **300+ transcripts** from Lenny's Podcast included
- **292 unique speakers** including product leaders from Stripe, Netflix, Airbnb, and more
- **Multi-round discussions** where experts build on each other's perspectives

## Quick Start

### Step 1: Clone and install

```bash
git clone https://github.com/manimohans/lennysroundtable.git
cd lennysroundtable
uv sync
```

### Step 2: Configure your LLM

Copy the example config:

```bash
cp .env.example .env
```

Edit `.env` with your provider:

<details>
<summary><b>Option A: Ollama (Local, Free) - Tested ✓</b></summary>

1. Install [Ollama](https://ollama.ai/)
2. Pull models:
   ```bash
   ollama pull embeddinggemma   # For embeddings
   ollama pull gemma3:4b        # For generation (or any model you prefer)
   ```
3. Set in `.env`:
   ```
   LLM_BASE_URL=http://localhost:11434/v1
   LLM_MODEL=gemma3:4b
   LLM_API_KEY=not-needed
   ```
</details>

<details>
<summary><b>Option B: LM Studio (Local, Free) - Tested ✓</b></summary>

1. Install [LM Studio](https://lmstudio.ai/)
2. Download a model and start the local server
3. **You still need Ollama for embeddings:**
   ```bash
   ollama pull embeddinggemma
   ```
4. Set in `.env`:
   ```
   LLM_BASE_URL=http://localhost:1234/v1
   LLM_MODEL=your-loaded-model-name
   LLM_API_KEY=not-needed
   ```
</details>

<details>
<summary><b>Option C: OpenAI (Cloud, Paid)</b></summary>

1. Get an API key from [OpenAI](https://platform.openai.com/api-keys)
2. **You still need Ollama for embeddings:**
   ```bash
   ollama pull embeddinggemma
   ```
3. Set in `.env`:
   ```
   LLM_BASE_URL=https://api.openai.com/v1
   LLM_MODEL=gpt-4o-mini
   LLM_API_KEY=sk-your-api-key-here
   ```
</details>

### Step 3: Generate embeddings (one-time setup)

> **Why isn't this included?** The vector database (`chroma_db/`) is ~600MB, which exceeds GitHub's file size limits. You need to generate it locally once. This takes about 50 minutes on CPU.

Make sure Ollama is running, then:

```bash
ollama pull embeddinggemma    # If you haven't already
uv run python -m roundtable.ingest
```

You'll see progress like:
```
Found 301 transcript files
[301/301] Parsing: Zoelle Egner.txt

Created 17482 parent documents
Unique speakers: 292

Storing parent documents...
Creating child chunks for vector indexing...
Embedding and indexing child chunks (this may take a while)...
Generating embeddings: 100%|████████| 2048/2048 [04:08<00:00]
...

Ingestion complete!
Parent chunks: 17482
Child chunks: 22435
```

### Step 4: Run the app

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

## Sync Latest Transcripts (Optional)

Want to update with the newest podcast episodes?

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

### Step 3: Re-embed

```bash
uv run python -m roundtable.ingest --reset
```

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

### Speaker Scoring

Speakers are ranked by relevance to your question:

1. **Cosine similarity**: Each child chunk gets a similarity score (0-1, higher = more relevant)
2. **Aggregation**: Sum all similarity scores for a speaker's matching chunks
3. **Normalization**: Divide by √(num_chunks) to balance speakers with many vs. few appearances

```
score = sum(similarities) / sqrt(num_chunks)
```

Typical scores range from ~0.5 (weakly relevant) to ~2.0 (highly relevant). The top 5 speakers are selected for the discussion.

### Embedding Model

The default embedding model is `embeddinggemma` via Ollama:
- Free and runs locally
- Good quality embeddings for this use case
- Consistent results across setups

To use a different model, set `EMBEDDING_MODEL` in your `.env` file before running ingestion.

---

## Project Structure

```
lennysroundtable/
├── roundtable/
│   ├── app.py           # Streamlit UI
│   ├── generator.py     # LLM response generation
│   ├── retriever.py     # Semantic search & ranking
│   ├── ingest.py        # Embedding pipeline
│   └── parser.py        # Transcript parsing
├── transcripts/         # 300+ podcast transcripts
├── chroma_db/           # Generated locally (not in repo)
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

### Embedding Settings (`.env`)

| Variable | Default | Description |
|----------|---------|-------------|
| `EMBEDDING_MODEL` | `embeddinggemma` | Ollama embedding model |

### Chunk Settings (`roundtable/ingest.py`)

| Variable | Default | Description |
|----------|---------|-------------|
| `CHILD_CHUNK_SIZE` | 512 | Smaller = more precise matching |
| `PARENT_CHUNK_SIZE` | 2048 | Larger = more context for LLM |

---

## Troubleshooting

**"No relevant speakers found"**
- You need to run the embedding step first: `uv run python -m roundtable.ingest`
- Make sure Ollama is running with `embeddinggemma`

**"Connection refused" errors**
- Make sure your LLM provider is running (Ollama/LM Studio)
- Check the `LLM_BASE_URL` in `.env`

**Embedding step fails**
- Ensure Ollama is running: `ollama serve`
- Pull the embedding model: `ollama pull embeddinggemma`

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

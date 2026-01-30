"""Ingest transcripts into ChromaDB using LlamaIndex."""

import sys
from pathlib import Path

import chromadb
from llama_index.core import Document, StorageContext, VectorStoreIndex
from llama_index.core.node_parser import SentenceSplitter
from llama_index.embeddings.ollama import OllamaEmbedding
from llama_index.vector_stores.chroma import ChromaVectorStore

from .parser import parse_transcript, chunk_turn


# ChromaDB settings
CHROMA_PATH = Path("chroma_db")
COLLECTION_NAME = "transcripts"
PARENT_COLLECTION_NAME = "transcripts_parents"
EMBEDDING_MODEL = "embeddinggemma"

# Chunk sizes for parent-child retrieval pattern
# Small chunks for precise matching, large chunks for coherent context
CHILD_CHUNK_SIZE = 512
CHILD_CHUNK_OVERLAP = 50
PARENT_CHUNK_SIZE = 2048  # Returned to LLM for context


def get_chroma_client() -> chromadb.PersistentClient:
    """Get or create ChromaDB persistent client."""
    return chromadb.PersistentClient(path=str(CHROMA_PATH))


def get_embedding_model() -> OllamaEmbedding:
    """Get the Ollama embedding model."""
    return OllamaEmbedding(
        model_name=EMBEDDING_MODEL,
        base_url="http://localhost:11434",
    )


def create_parent_documents(transcripts_dir: Path) -> tuple[list[Document], dict[str, str]]:
    """
    Create parent documents from transcripts.

    Returns:
        - List of parent Document objects (large chunks)
        - Dict mapping parent_id -> parent text (for retrieval)
    """
    transcript_files = sorted(transcripts_dir.glob("*.txt"))
    print(f"Found {len(transcript_files)} transcript files")

    parent_documents = []
    parent_store = {}  # parent_id -> full parent text
    speakers_seen = set()
    global_chunk_counter = 0  # Global counter for unique IDs

    for i, file_path in enumerate(transcript_files):
        print(f"\r[{i+1}/{len(transcript_files)}] Parsing: {file_path.name[:50]:<50}", end="")

        try:
            turns = parse_transcript(file_path)
        except Exception as e:
            print(f"\n  Error parsing {file_path.name}: {e}")
            continue

        if not turns:
            continue

        # Create parent chunks (larger, for context)
        for turn in turns:
            chunks = chunk_turn(turn, max_chars=PARENT_CHUNK_SIZE, overlap=200)

            for chunk in chunks:
                speakers_seen.add(chunk['speaker'])

                # Build parent document text
                doc_text = chunk['text']
                if chunk['preceding_question']:
                    doc_text = f"Question: {chunk['preceding_question']}\n\nAnswer: {chunk['text']}"

                # Create unique parent ID using global counter
                parent_id = f"doc_{global_chunk_counter:06d}_{chunk['speaker']}_{chunk['timestamp']}"
                parent_id = parent_id.replace(" ", "_").replace(":", "-")
                global_chunk_counter += 1

                # Store parent text for later retrieval
                parent_store[parent_id] = doc_text

                # Create LlamaIndex document
                doc = Document(
                    text=doc_text,
                    metadata={
                        'speaker': chunk['speaker'],
                        'source_file': chunk['source_file'],
                        'timestamp': chunk['timestamp'],
                        'preceding_question': chunk['preceding_question'][:500] if chunk['preceding_question'] else "",
                        'parent_id': parent_id,
                    },
                    id_=parent_id,
                )
                parent_documents.append(doc)

    print(f"\n\nCreated {len(parent_documents)} parent documents")
    print(f"Unique speakers: {len(speakers_seen)}")
    print(f"Sample speakers: {list(speakers_seen)[:10]}")

    return parent_documents, parent_store


def ingest_transcripts(transcripts_dir: Path, reset: bool = False):
    """
    Ingest all transcripts using LlamaIndex with parent-child retrieval.

    The pattern:
    - Create large "parent" chunks (2048 chars) for coherent context
    - Split into small "child" chunks (512 chars) for precise matching
    - Store child chunks in vector index with reference to parent
    - On retrieval: match child chunks, return parent chunks
    """
    client = get_chroma_client()

    if reset:
        try:
            client.delete_collection(COLLECTION_NAME)
            print("Deleted existing child collection")
        except Exception:
            pass
        try:
            client.delete_collection(PARENT_COLLECTION_NAME)
            print("Deleted existing parent collection")
        except Exception:
            pass

    # Check existing data
    try:
        existing = client.get_collection(COLLECTION_NAME)
        existing_count = existing.count()
        if existing_count > 0 and not reset:
            print(f"Collection already has {existing_count} chunks")
            response = input("Reset and re-ingest? (y/N): ")
            if response.lower() != 'y':
                print("Aborting. Use --reset flag to force re-ingestion.")
                return
            client.delete_collection(COLLECTION_NAME)
            try:
                client.delete_collection(PARENT_COLLECTION_NAME)
            except Exception:
                pass
    except Exception:
        pass  # Collection doesn't exist

    # Create collections
    child_collection = client.get_or_create_collection(
        name=COLLECTION_NAME,
        metadata={"hnsw:space": "cosine"}
    )
    parent_collection = client.get_or_create_collection(
        name=PARENT_COLLECTION_NAME,
        metadata={"hnsw:space": "cosine"}
    )

    # Create vector store and storage context
    vector_store = ChromaVectorStore(chroma_collection=child_collection)
    storage_context = StorageContext.from_defaults(vector_store=vector_store)

    # Get embedding model
    embed_model = get_embedding_model()

    # Create parent documents
    parent_docs, parent_store = create_parent_documents(transcripts_dir)

    if not parent_docs:
        print("No documents to ingest!")
        return

    # Store parent documents in parent collection (for retrieval)
    print("\nStoring parent documents...")
    parent_ids = []
    parent_texts = []
    parent_metadatas = []

    for doc in parent_docs:
        parent_ids.append(doc.id_)
        parent_texts.append(doc.text)
        parent_metadatas.append(dict(doc.metadata))

    # Add parents in batches
    batch_size = 100
    for i in range(0, len(parent_ids), batch_size):
        batch_ids = parent_ids[i:i + batch_size]
        batch_texts = parent_texts[i:i + batch_size]
        batch_metas = parent_metadatas[i:i + batch_size]

        parent_collection.add(
            ids=batch_ids,
            documents=batch_texts,
            metadatas=batch_metas,
        )
        print(f"\r  Stored {min(i + batch_size, len(parent_ids))}/{len(parent_ids)} parents", end="")

    print()

    # Create child chunks using LlamaIndex's sentence splitter
    print("\nCreating child chunks for vector indexing...")
    node_parser = SentenceSplitter(
        chunk_size=CHILD_CHUNK_SIZE,
        chunk_overlap=CHILD_CHUNK_OVERLAP,
    )

    # Parse parent docs into child nodes
    child_nodes = node_parser.get_nodes_from_documents(parent_docs, show_progress=True)

    # Ensure each child node has parent_id in metadata
    for node in child_nodes:
        if 'parent_id' not in node.metadata:
            # Get from source doc
            node.metadata['parent_id'] = node.ref_doc_id

    print(f"Created {len(child_nodes)} child chunks from {len(parent_docs)} parents")

    # Create vector index with child nodes
    print("\nEmbedding and indexing child chunks (this may take a while)...")
    index = VectorStoreIndex(
        nodes=child_nodes,
        storage_context=storage_context,
        embed_model=embed_model,
        show_progress=True,
    )

    print(f"\n\nIngestion complete!")
    print(f"Parent chunks: {len(parent_docs)}")
    print(f"Child chunks: {len(child_nodes)}")
    print(f"Avg children per parent: {len(child_nodes) / len(parent_docs):.1f}")


def main():
    """Main entry point for ingestion."""
    import argparse

    parser = argparse.ArgumentParser(description="Ingest transcripts into ChromaDB")
    parser.add_argument(
        "--transcripts-dir",
        type=Path,
        default=Path("transcripts"),
        help="Directory containing transcript files"
    )
    parser.add_argument(
        "--reset",
        action="store_true",
        help="Reset collection and re-ingest all files"
    )
    args = parser.parse_args()

    if not args.transcripts_dir.exists():
        print(f"Transcripts directory not found: {args.transcripts_dir}")
        sys.exit(1)

    ingest_transcripts(args.transcripts_dir, reset=args.reset)


if __name__ == "__main__":
    main()

"""Retrieve relevant chunks from ChromaDB and rank speakers."""

import math
from dataclasses import dataclass

import chromadb
from llama_index.embeddings.ollama import OllamaEmbedding

from .ingest import CHROMA_PATH, COLLECTION_NAME, PARENT_COLLECTION_NAME, EMBEDDING_MODEL


@dataclass
class SpeakerContext:
    """Context for a speaker with their relevant chunks."""
    speaker: str
    score: float
    chunks: list[dict]

    def get_context_text(self, max_chunks: int = 3) -> str:
        """Get formatted context text from chunks."""
        texts = []
        for chunk in self.chunks[:max_chunks]:
            text = chunk['text']
            source = chunk['metadata'].get('source_file', 'Unknown')
            timestamp = chunk['metadata'].get('timestamp', '')
            texts.append(f'[From {source} at {timestamp}]\n"{text}"')
        return '\n\n'.join(texts)


class Retriever:
    """Retrieve relevant chunks and rank speakers by relevance."""

    def __init__(self):
        self.client = chromadb.PersistentClient(path=str(CHROMA_PATH))
        self.child_collection = self.client.get_collection(COLLECTION_NAME)
        self.parent_collection = self.client.get_collection(PARENT_COLLECTION_NAME)
        self.embed_model = OllamaEmbedding(
            model_name=EMBEDDING_MODEL,
            base_url="http://localhost:11434",
        )

    def embed_query(self, query: str) -> list[float]:
        """Generate embedding for a query."""
        return self.embed_model.get_query_embedding(query)

    def search_children(self, query: str, n_results: int = 50) -> dict:
        """Search child chunks for precise matching."""
        query_embedding = self.embed_query(query)

        results = self.child_collection.query(
            query_embeddings=[query_embedding],
            n_results=n_results,
            include=['documents', 'metadatas', 'distances']
        )

        return results

    def get_parent_chunks(self, parent_ids: list[str]) -> dict[str, dict]:
        """Fetch parent chunks by their IDs."""
        if not parent_ids:
            return {}

        # Deduplicate
        unique_ids = list(set(parent_ids))

        results = self.parent_collection.get(
            ids=unique_ids,
            include=['documents', 'metadatas']
        )

        parent_map = {}
        for i, pid in enumerate(results['ids']):
            parent_map[pid] = {
                'text': results['documents'][i],
                'metadata': results['metadatas'][i],
            }

        return parent_map

    def rank_speakers(self, query: str, top_k: int = 5, min_chunks: int = 2) -> list[SpeakerContext]:
        """
        Rank speakers by relevance to the query using parent-child retrieval.

        Algorithm:
        1. Search child chunks for precise matching
        2. Fetch corresponding parent chunks for context
        3. Group by speaker, deduplicate parents
        4. Score = sum(similarity_scores) / sqrt(num_unique_parents)
        5. Return top k speakers with their parent chunks

        Args:
            query: The user's question
            top_k: Number of speakers to return
            min_chunks: Minimum chunks a speaker needs to be considered

        Returns:
            List of SpeakerContext objects for top speakers
        """
        # Search child chunks
        child_results = self.search_children(query, n_results=100)

        if not child_results['ids'][0]:
            return []

        # Collect parent IDs and scores from child matches
        parent_scores: dict[str, list[float]] = {}  # parent_id -> list of child similarities
        parent_ids = []

        for i, doc_id in enumerate(child_results['ids'][0]):
            metadata = child_results['metadatas'][0][i]
            parent_id = metadata.get('parent_id')

            if not parent_id:
                continue

            distance = child_results['distances'][0][i]
            similarity = 1 - distance

            if parent_id not in parent_scores:
                parent_scores[parent_id] = []
                parent_ids.append(parent_id)

            parent_scores[parent_id].append(similarity)

        # Fetch parent chunks
        parent_map = self.get_parent_chunks(parent_ids)

        # Group parents by speaker
        speaker_parents: dict[str, list[dict]] = {}

        for parent_id, scores in parent_scores.items():
            if parent_id not in parent_map:
                continue

            parent_data = parent_map[parent_id]
            speaker = parent_data['metadata'].get('speaker', 'Unknown')

            # Use best child match score for this parent
            best_score = max(scores)

            chunk_data = {
                'id': parent_id,
                'text': parent_data['text'],
                'metadata': parent_data['metadata'],
                'similarity': best_score,
                'num_child_matches': len(scores),
            }

            if speaker not in speaker_parents:
                speaker_parents[speaker] = []
            speaker_parents[speaker].append(chunk_data)

        # Score speakers
        speaker_scores = []
        for speaker, chunks in speaker_parents.items():
            if len(chunks) < min_chunks:
                continue

            # Sum similarity scores, normalize by sqrt(num_chunks)
            total_similarity = sum(c['similarity'] for c in chunks)
            score = total_similarity / math.sqrt(len(chunks))

            # Sort chunks by similarity (highest first)
            chunks.sort(key=lambda x: x['similarity'], reverse=True)

            speaker_scores.append(SpeakerContext(
                speaker=speaker,
                score=score,
                chunks=chunks,
            ))

        # Sort by score (highest first)
        speaker_scores.sort(key=lambda x: x.score, reverse=True)

        # Handle case where we don't have enough speakers with min_chunks
        if len(speaker_scores) < top_k:
            for speaker, chunks in speaker_parents.items():
                if any(sc.speaker == speaker for sc in speaker_scores):
                    continue
                if len(speaker_scores) >= top_k:
                    break

                total_similarity = sum(c['similarity'] for c in chunks)
                score = total_similarity / math.sqrt(len(chunks))
                chunks.sort(key=lambda x: x['similarity'], reverse=True)

                speaker_scores.append(SpeakerContext(
                    speaker=speaker,
                    score=score,
                    chunks=chunks,
                ))

            speaker_scores.sort(key=lambda x: x.score, reverse=True)

        return speaker_scores[:top_k]

    def get_all_speakers(self) -> list[str]:
        """Get list of all unique speakers in the collection."""
        results = self.parent_collection.get(limit=10000, include=['metadatas'])
        speakers = set()
        for metadata in results['metadatas']:
            speakers.add(metadata['speaker'])
        return sorted(speakers)


if __name__ == "__main__":
    # Test retrieval
    retriever = Retriever()

    print("All speakers:")
    speakers = retriever.get_all_speakers()
    print(f"Found {len(speakers)} speakers")

    query = "How should I prioritize features as a PM?"
    print(f"\nQuery: {query}")
    print("-" * 50)

    top_speakers = retriever.rank_speakers(query)
    for i, ctx in enumerate(top_speakers, 1):
        print(f"\n{i}. {ctx.speaker} (score: {ctx.score:.3f})")
        print(f"   Parent chunks: {len(ctx.chunks)}")
        print(f"   Top chunk preview: {ctx.chunks[0]['text'][:300]}...")

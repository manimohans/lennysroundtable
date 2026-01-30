"""Generate responses using OpenAI-compatible APIs (Ollama, LM Studio, vLLM, OpenAI, etc.)."""

import os
import random
from dataclasses import dataclass
from pathlib import Path

from openai import OpenAI

# Load .env file
try:
    from dotenv import load_dotenv
    load_dotenv(Path(__file__).parent.parent / ".env")
except ImportError:
    pass  # dotenv not installed, use environment variables directly

from .retriever import SpeakerContext


# LLM Configuration (all providers use OpenAI-compatible API)
# Ollama: http://localhost:11434/v1
# LM Studio: http://localhost:1234/v1
# OpenAI: https://api.openai.com/v1
LLM_BASE_URL = os.getenv("LLM_BASE_URL", "http://localhost:11434/v1")
LLM_MODEL = os.getenv("LLM_MODEL", "qwen3:4b")
LLM_API_KEY = os.getenv("LLM_API_KEY", "not-needed")  # Required for OpenAI, ignored by local


@dataclass
class Response:
    """A speaker's response in the discussion."""
    speaker: str
    text: str
    round_num: int


SYSTEM_PROMPT = """You are {speaker}. Answer based ONLY on the quotes provided - do not invent information.

STRICT RULES:
1. First word must NOT be: Okay, Well, So, Look, Honestly, I think, I agree, That's, You
2. NO stage directions like (smiling), (adjusting mic), etc.
3. NO quotation marks around your response
4. NEVER repeat or paraphrase what others said - use YOUR OWN words
5. Reference SPECIFIC examples from your quotes
6. Keep to {length}"""


INITIAL_PROMPT = """Question: "{question}"

YOUR ACTUAL QUOTES FROM THE PODCAST:
---
{context}
---

Share YOUR unique perspective using a specific example from your quotes. Start with a concrete insight."""


DISCUSSION_PROMPT = """Question: "{question}"

WHAT OTHERS SAID:
{previous_responses}

YOUR ACTUAL QUOTES FROM THE PODCAST:
---
{context}
---

IMPORTANT: Do NOT echo or restate what others said. Start with YOUR OWN fresh angle.

Either:
- DISAGREE with a specific point and explain why
- ADD a different example that challenges the consensus
- SHARE a contrarian take from your experience

Be specific and concrete. No generic agreement."""


# Brevity level to length description
BREVITY_MAP = {
    1: "1-2 sentences",
    2: "2-3 sentences",
    3: "3-5 sentences",
    4: "1-2 paragraphs",
    5: "2-3 paragraphs",
}


class Generator:
    """Generate responses for the roundtable discussion."""

    def __init__(self, model: str = LLM_MODEL, base_url: str = LLM_BASE_URL, api_key: str = LLM_API_KEY):
        self.model = model
        self.client = OpenAI(base_url=base_url, api_key=api_key)

    def generate_response(
        self,
        speaker_context: SpeakerContext,
        question: str,
        previous_responses: list[Response] | None = None,
        round_num: int = 1,
        user_name: str = "PM",
        brevity: int = 2,
    ) -> Response:
        """
        Generate a response from a speaker.

        Args:
            speaker_context: The speaker's context with relevant chunks
            question: The user's question
            previous_responses: Previous responses in the discussion (for rounds 2+)
            round_num: Current discussion round
            user_name: Name to address the user as
            brevity: Response length (1=very brief, 5=detailed)

        Returns:
            Response object with the generated text
        """
        context = speaker_context.get_context_text(max_chunks=3)
        length = BREVITY_MAP.get(brevity, "2-3 sentences")

        system = SYSTEM_PROMPT.format(
            speaker=speaker_context.speaker,
            length=length,
        )

        if not previous_responses:
            # First speaker - no prior context
            prompt = INITIAL_PROMPT.format(
                question=question,
                context=context,
            )
        else:
            # Has context from previous speakers (exclude self)
            other_responses = [r for r in previous_responses if r.speaker != speaker_context.speaker]
            prev_text = "\n\n".join([
                f"[{r.speaker}]: {r.text}"
                for r in other_responses
            ]) if other_responses else "No other responses yet."

            prompt = DISCUSSION_PROMPT.format(
                question=question,
                previous_responses=prev_text,
                context=context,
            )

        messages = [
            {"role": "system", "content": system},
            {"role": "user", "content": prompt},
        ]

        response = self.client.chat.completions.create(
            model=self.model,
            messages=messages,
            temperature=0.7,
        )

        return Response(
            speaker=speaker_context.speaker,
            text=response.choices[0].message.content,
            round_num=round_num,
        )

    def generate_response_streaming(
        self,
        speaker_context: SpeakerContext,
        question: str,
        previous_responses: list[Response] | None = None,
        round_num: int = 1,
        user_name: str = "PM",
        brevity: int = 2,
    ):
        """
        Generate a response with streaming.

        Yields:
            str chunks as they're generated
        """
        context = speaker_context.get_context_text(max_chunks=3)
        length = BREVITY_MAP.get(brevity, "2-3 sentences")

        system = SYSTEM_PROMPT.format(
            speaker=speaker_context.speaker,
            length=length,
        )

        if not previous_responses:
            # First speaker - no prior context
            prompt = INITIAL_PROMPT.format(
                question=question,
                context=context,
            )
        else:
            # Has context from previous speakers (exclude self)
            other_responses = [r for r in previous_responses if r.speaker != speaker_context.speaker]
            prev_text = "\n\n".join([
                f"[{r.speaker}]: {r.text}"
                for r in other_responses
            ]) if other_responses else "No other responses yet."

            prompt = DISCUSSION_PROMPT.format(
                question=question,
                previous_responses=prev_text,
                context=context,
            )

        messages = [
            {"role": "system", "content": system},
            {"role": "user", "content": prompt},
        ]

        stream = self.client.chat.completions.create(
            model=self.model,
            messages=messages,
            temperature=0.7,
            stream=True,
        )

        for chunk in stream:
            if chunk.choices[0].delta.content:
                yield chunk.choices[0].delta.content

    def run_discussion(
        self,
        speaker_contexts: list[SpeakerContext],
        question: str,
        num_rounds: int = 3,
    ) -> list[list[Response]]:
        """
        Run a multi-round discussion.

        Args:
            speaker_contexts: List of speaker contexts (top 5 speakers)
            question: The user's question
            num_rounds: Number of discussion rounds

        Returns:
            List of rounds, each containing responses from all speakers
        """
        all_rounds = []
        all_responses = []

        for round_num in range(1, num_rounds + 1):
            round_responses = []

            # Randomize order for rounds 2+
            contexts = speaker_contexts.copy()
            if round_num > 1:
                random.shuffle(contexts)

            for ctx in contexts:
                response = self.generate_response(
                    speaker_context=ctx,
                    question=question,
                    previous_responses=all_responses if round_num > 1 else None,
                    round_num=round_num,
                )
                round_responses.append(response)
                all_responses.append(response)

            all_rounds.append(round_responses)

        return all_rounds


if __name__ == "__main__":
    # Test generation (requires ingest to be run first)
    from .retriever import Retriever

    retriever = Retriever()
    generator = Generator()

    question = "How should I prioritize features as a PM?"
    print(f"Question: {question}\n")

    # Get top speakers
    speakers = retriever.rank_speakers(question, top_k=3)
    print(f"Selected speakers: {[s.speaker for s in speakers]}\n")

    # Run 2 rounds
    rounds = generator.run_discussion(speakers, question, num_rounds=2)

    for i, round_responses in enumerate(rounds, 1):
        print(f"\n{'='*60}")
        print(f"ROUND {i}")
        print('='*60)
        for response in round_responses:
            print(f"\n**{response.speaker}**:")
            print(response.text)

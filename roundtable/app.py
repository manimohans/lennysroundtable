"""Streamlit UI for the Roundtable Discussion app."""

import random
import streamlit as st

from roundtable.retriever import Retriever
from roundtable.generator import Generator, Response


# Rotating example questions
EXAMPLE_QUESTIONS = [
    "How do I tell my CEO their idea is bad?",
    "How do I say no without getting fired?",
    "How do I prioritize when everything is P0?",
    "Is product-market fit just vibes?",
    "How do I survive a reorg?",
    "What do I do when engineering hates my spec?",
    "How do I pretend to be data-driven?",
]


# Speaker colors for consistent visual identity
SPEAKER_COLORS = [
    "#FF6B6B",  # Red
    "#4ECDC4",  # Teal
    "#45B7D1",  # Blue
    "#96CEB4",  # Green
    "#FFEAA7",  # Yellow
]


def get_speaker_color(speaker: str, speakers: list[str]) -> str:
    """Get consistent color for a speaker."""
    if speaker in speakers:
        idx = speakers.index(speaker)
        return SPEAKER_COLORS[idx % len(SPEAKER_COLORS)]
    return "#808080"


def render_response(response: Response, speakers: list[str]):
    """Render a single response with styled speaker name."""
    color = get_speaker_color(response.speaker, speakers)
    st.markdown(
        f'<div style="border-left: 4px solid {color}; padding-left: 12px; margin-bottom: 16px;">'
        f'<strong style="color: {color};">{response.speaker}</strong>'
        f'<p>{response.text}</p></div>',
        unsafe_allow_html=True
    )


def generate_markdown(question: str, speakers: list[str], discussion: list[list[Response]]) -> str:
    """Generate markdown from the discussion."""
    from datetime import datetime

    lines = [
        f"# Roundtable Discussion",
        f"",
        f"**Question:** {question}",
        f"",
        f"**Participants:** {', '.join(speakers)}",
        f"",
        f"**Date:** {datetime.now().strftime('%Y-%m-%d %H:%M')}",
        f"",
        f"---",
        f"",
    ]

    for i, round_responses in enumerate(discussion, 1):
        if i == 1:
            lines.append("## Initial Thoughts")
        else:
            lines.append(f"## Round {i} — Discussion")
        lines.append("")

        for response in round_responses:
            lines.append(f"### {response.speaker}")
            lines.append("")
            lines.append(response.text)
            lines.append("")

        lines.append("---")
        lines.append("")

    return "\n".join(lines)


def main():
    st.set_page_config(
        page_title="Lenny's Roundtable",
        page_icon="🎙️",
        layout="wide",
    )

    st.title("🎙️ Lenny's Roundtable")
    st.markdown("*Thank you so much for being here, and welcome to the roundtable!*")
    st.markdown(
        "Lenny asked the questions. Now it's your turn."
    )

    # Initialize session state
    if 'discussion' not in st.session_state:
        st.session_state.discussion = None
    if 'question' not in st.session_state:
        st.session_state.question = ""
    if 'speakers' not in st.session_state:
        st.session_state.speakers = []

    # Sidebar
    with st.sidebar:
        st.header("Settings")
        num_rounds = st.slider("Discussion Rounds", 1, 5, 3)
        num_speakers = st.slider("Number of Experts", 3, 7, 5)
        brevity = st.slider("Response Length", 1, 5, 2, help="1=Very brief, 5=Detailed")

        st.markdown("---")
        st.markdown("### How it works")
        st.markdown("""
        1. Enter your question
        2. AI finds the 5 most relevant podcast guests
        3. Each guest responds based on their actual quotes
        4. Guests discuss and build on each other's ideas
        """)

    # Main content - use form so Enter key submits
    with st.form("question_form"):
        col_name, col_question = st.columns([1, 3])
        with col_name:
            user_name = st.text_input("Your Name", value="PM")
        with col_question:
            question = st.text_input(
                "Your Question",
                placeholder=f"e.g., {random.choice(EXAMPLE_QUESTIONS)}",
            )

        generate_btn = st.form_submit_button("🚀 Generate Discussion", type="primary")

    if generate_btn and question:
        with st.spinner("Finding relevant experts..."):
            try:
                retriever = Retriever()
                speaker_contexts = retriever.rank_speakers(question, top_k=num_speakers)

                if not speaker_contexts:
                    st.error("No relevant speakers found. Make sure transcripts are ingested.")
                    return

                st.session_state.speakers = [ctx.speaker for ctx in speaker_contexts]
            except Exception as e:
                st.error(f"Error finding speakers: {e}")
                st.info("Make sure you've run: `uv run python -m roundtable.ingest`")
                return

        # Show selected experts
        st.markdown("### 👥 Selected Experts")
        cols = st.columns(len(speaker_contexts))
        for i, (col, ctx) in enumerate(zip(cols, speaker_contexts)):
            with col:
                color = SPEAKER_COLORS[i % len(SPEAKER_COLORS)]
                st.markdown(
                    f'<div style="text-align: center; padding: 10px; '
                    f'border: 2px solid {color}; border-radius: 8px;">'
                    f'<strong style="color: {color};">{ctx.speaker}</strong><br>'
                    f'<small>Score: {ctx.score:.2f}</small></div>',
                    unsafe_allow_html=True
                )

        st.markdown("---")

        # Generate discussion with streaming
        try:
            generator = Generator()
            all_rounds = []
            all_responses = []

            for round_num in range(1, num_rounds + 1):
                if round_num == 1:
                    st.markdown("### Initial Thoughts")
                else:
                    st.markdown(f"### Round {round_num} — Discussion")
                round_responses = []

                # Randomize order for rounds 2+
                contexts = speaker_contexts.copy()
                if round_num > 1:
                    random.shuffle(contexts)

                for ctx in contexts:
                    color = get_speaker_color(ctx.speaker, st.session_state.speakers)
                    st.markdown(
                        f'<div style="border-left: 4px solid {color}; padding-left: 12px; margin-bottom: 16px;">'
                        f'<strong style="color: {color};">{ctx.speaker}</strong></div>',
                        unsafe_allow_html=True
                    )

                    # Stream the response (always pass all_responses for full context)
                    response_text = ""
                    response_placeholder = st.empty()
                    for chunk in generator.generate_response_streaming(
                        speaker_context=ctx,
                        question=question,
                        previous_responses=all_responses if all_responses else None,
                        round_num=round_num,
                        user_name=user_name or "PM",
                        brevity=brevity,
                    ):
                        response_text += chunk
                        response_placeholder.markdown(response_text)

                    response = Response(
                        speaker=ctx.speaker,
                        text=response_text,
                        round_num=round_num,
                    )
                    round_responses.append(response)
                    all_responses.append(response)

                all_rounds.append(round_responses)
                st.markdown("---")

            st.session_state.discussion = all_rounds
            st.session_state.question = question
        except Exception as e:
            st.error(f"Error generating discussion: {e}")
            st.info("Make sure Ollama is running with the required model.")
            return

    # Display discussion and save option
    if st.session_state.discussion:
        st.markdown(f"### 💬 Discussion: *{st.session_state.question}*")

        for i, round_responses in enumerate(st.session_state.discussion, 1):
            with st.expander(f"Round {i}", expanded=(i == 1)):
                for response in round_responses:
                    render_response(response, st.session_state.speakers)

        # Save as markdown button
        markdown_content = generate_markdown(
            st.session_state.question,
            st.session_state.speakers,
            st.session_state.discussion,
        )
        # Create filename from question
        filename = st.session_state.question[:50].replace(" ", "_").replace("?", "")
        filename = f"roundtable_{filename}.md"

        st.download_button(
            label="📥 Save as Markdown",
            data=markdown_content,
            file_name=filename,
            mime="text/markdown",
        )

    # Footer
    st.markdown("---")
    st.markdown(
        "<small>Powered by RAG with ChromaDB, Ollama, and Streamlit</small>",
        unsafe_allow_html=True
    )


if __name__ == "__main__":
    main()

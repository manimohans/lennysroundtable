"""Parse podcast transcripts into speaker turns."""

import re
from dataclasses import dataclass
from pathlib import Path


@dataclass
class Turn:
    """A single speaker turn from a transcript."""
    speaker: str
    timestamp: str
    text: str
    preceding_question: str
    source_file: str


# Matches speaker with timestamp:
# "Shreyas Doshi (00:03:48):" and "KUNAL SHAH (00:00:08):"
# Name must:
# - Start at beginning of line
# - Be 2-50 characters (reasonable name length)
# - Contain only letters, spaces, dots, ampersands, hyphens, apostrophes
# - NOT contain common sentence words
SPEAKER_WITH_TIMESTAMP_PATTERN = re.compile(
    r'^([A-Z][A-Za-z \.&\-\']{1,49})\s*\((\d{1,2}:\d{2}(?::\d{2})?)\):\s*$',
    re.MULTILINE
)

# Matches speaker without timestamp (alternate format):
# "Adriel Frederick:"
SPEAKER_NO_TIMESTAMP_PATTERN = re.compile(
    r'^([A-Z][A-Za-z \.&\-\']{1,49}):\s*$',
    re.MULTILINE
)

# Matches timestamp-only continuation (same speaker as previous):
# "(00:00:48):"
TIMESTAMP_ONLY_PATTERN = re.compile(
    r'^\((\d{1,2}:\d{2}(?::\d{2})?)\):\s*$',
    re.MULTILINE
)

# Words/phrases that indicate this is NOT a speaker name (but a sentence)
SENTENCE_INDICATORS = {
    'the', 'and', 'that', 'this', 'what', 'which', 'about', 'with',
    'for', 'from', 'into', 'just', 'yeah', 'yes', 'well', 'okay',
    'really', 'very', 'good', 'great', 'nice', 'last', 'next',
    'piece', 'part', 'idea', 'point', 'thing', 'question', 'answer',
    'so', 'but', 'or', 'if', 'when', 'how', 'why', 'where', 'who',
    'it', 'is', 'are', 'was', 'were', 'be', 'been', 'being',
    'have', 'has', 'had', 'do', 'does', 'did', 'will', 'would',
    'could', 'should', 'may', 'might', 'must', 'shall', 'can',
    'not', 'no', 'all', 'any', 'some', 'every', 'each', 'both',
    'more', 'most', 'other', 'another', 'such', 'only', 'own',
    'same', 'than', 'too', 'also', 'now', 'then', 'here', 'there',
}

# Single-word non-names (common interjections that might appear at line start)
SINGLE_WORD_NON_NAMES = {
    'yeah', 'yes', 'no', 'okay', 'ok', 'sure', 'right', 'exactly',
    'absolutely', 'totally', 'definitely', 'certainly', 'probably',
    'maybe', 'perhaps', 'honestly', 'actually', 'basically', 'literally',
    'interesting', 'amazing', 'awesome', 'great', 'good', 'nice', 'cool',
    'wow', 'oh', 'ah', 'um', 'uh', 'hmm', 'well', 'so', 'like', 'true',
    'advertisement', 'eventually', 'finally', 'unfortunately', 'fortunately',
    'obviously', 'clearly', 'apparently', 'essentially', 'ultimately',
    'minds', 'all',  # Catch "All-minds" type patterns
}

# Known sponsor/ad segment speakers to filter out
SPONSOR_SPEAKERS = {
    'advertisement', 'ad', 'sponsor',
}

# Sponsor keywords to filter out
SPONSOR_KEYWORDS = [
    "brought to you by",
    "this episode is brought",
    "sponsor",
    "promo code",
    "discount code",
    "coupon code",
    "sign up and get",
    "head over to",
    "check out",
    "special offer",
]

# Host names to identify (case-insensitive)
HOST_NAMES = {"lenny", "lenny rachitsky"}


def normalize_speaker_name(name: str) -> str:
    """Normalize speaker name to title case."""
    name = name.strip()
    # Handle ALL CAPS names
    if name.isupper():
        return name.title()
    return name


def is_valid_speaker_name(name: str) -> bool:
    """Check if the captured text is actually a speaker name, not a sentence."""
    name_clean = name.strip()
    name_lower = name_clean.lower()

    # Must have at least one word
    if not name_clean:
        return False

    # Split on spaces for word count
    words = name_lower.split()

    # Most speaker names are 1-4 words
    if len(words) > 5:
        return False

    # Names shouldn't be too short (likely just "I" or similar)
    if len(name_clean) < 3:
        return False

    # Single word (including hyphenated) names need special handling
    if len(words) == 1:
        # Remove trailing period for comparison
        word = words[0].rstrip('.')
        # Also check hyphenated parts
        parts = word.split('-')
        for part in parts:
            if part in SINGLE_WORD_NON_NAMES:
                return False

        # Single words ending with period are suspicious (unless title)
        if name_clean.endswith('.') and not any(name_clean.endswith(t) for t in ['Jr.', 'Sr.', 'Dr.', 'Mr.', 'Ms.', 'Mrs.']):
            return False

    # Check for sentence indicator words
    for word in words:
        # Remove punctuation for comparison
        clean_word = word.rstrip('.,!?')
        if clean_word in SENTENCE_INDICATORS:
            return False

    # Multi-word names shouldn't end with a period (unless title)
    if len(words) > 1 and name_clean.endswith('.'):
        if not any(name_clean.endswith(t) for t in ['Jr.', 'Sr.', 'Dr.', 'Mr.', 'Ms.', 'Mrs.']):
            return False

    return True


def is_host(speaker: str) -> bool:
    """Check if the speaker is the host (Lenny)."""
    return speaker.lower().strip() in HOST_NAMES


def is_sponsor_content(text: str) -> bool:
    """Check if text contains sponsor/ad content."""
    text_lower = text.lower()
    return any(kw in text_lower for kw in SPONSOR_KEYWORDS)


def parse_transcript(file_path: Path) -> list[Turn]:
    """
    Parse a transcript file into speaker turns.

    Returns a list of Turn objects for guest speakers only,
    with the preceding Lenny question attached for context.
    """
    text = file_path.read_text(encoding='utf-8')
    source_file = file_path.name

    # Try format with timestamps first
    speaker_matches = list(SPEAKER_WITH_TIMESTAMP_PATTERN.finditer(text))
    timestamp_matches = list(TIMESTAMP_ONLY_PATTERN.finditer(text))

    # If no matches with timestamps, try format without timestamps
    if not speaker_matches:
        speaker_matches = list(SPEAKER_NO_TIMESTAMP_PATTERN.finditer(text))
        timestamp_matches = []  # No timestamp continuations in this format

    if not speaker_matches:
        return []

    # Determine if we're using timestamp format or not
    has_timestamps = bool(timestamp_matches) or (speaker_matches and speaker_matches[0].lastindex >= 2)

    # Combine and sort all markers by position
    all_markers = []
    for m in speaker_matches:
        raw_name = m.group(1)
        # Get timestamp if available (group 2), otherwise empty string
        timestamp = m.group(2) if m.lastindex >= 2 else ""

        if is_valid_speaker_name(raw_name):
            all_markers.append({
                'start': m.start(),
                'end': m.end(),
                'speaker': normalize_speaker_name(raw_name),
                'timestamp': timestamp,
                'type': 'speaker'
            })
        else:
            # This was a false positive - treat as timestamp continuation
            all_markers.append({
                'start': m.start(),
                'end': m.end(),
                'speaker': None,
                'timestamp': timestamp,
                'type': 'continuation'
            })
    for m in timestamp_matches:
        all_markers.append({
            'start': m.start(),
            'end': m.end(),
            'speaker': None,  # Will be filled from previous speaker
            'timestamp': m.group(1),
            'type': 'continuation'
        })

    all_markers.sort(key=lambda x: x['start'])

    # Fill in speakers for continuations and extract turns
    raw_turns = []
    current_speaker = None

    for i, marker in enumerate(all_markers):
        if marker['type'] == 'speaker':
            current_speaker = marker['speaker']
        else:
            # Continuation - use previous speaker (host Lenny for these)
            marker['speaker'] = current_speaker if current_speaker else "Lenny"

        # Get text until next marker or end
        start = marker['end']
        end = all_markers[i + 1]['start'] if i + 1 < len(all_markers) else len(text)
        turn_text = text[start:end].strip()

        raw_turns.append({
            'speaker': marker['speaker'],
            'timestamp': marker['timestamp'],
            'text': turn_text,
            'is_host': is_host(marker['speaker']),
        })

    # Merge consecutive turns from same speaker
    merged_turns = []
    for turn in raw_turns:
        if merged_turns and merged_turns[-1]['speaker'] == turn['speaker']:
            # Merge with previous turn
            merged_turns[-1]['text'] += '\n\n' + turn['text']
        else:
            merged_turns.append(turn)

    # Extract guest turns with preceding questions
    guest_turns = []
    last_host_question = ""

    for turn in merged_turns:
        if turn['is_host']:
            # Skip sponsor content from host
            if not is_sponsor_content(turn['text']):
                last_host_question = turn['text']
        else:
            # This is a guest turn
            speaker_name = turn['speaker']

            # Skip known sponsor speakers
            if speaker_name and speaker_name.lower() in SPONSOR_SPEAKERS:
                continue

            # Skip sponsor content in guest turns (ad segments)
            if is_sponsor_content(turn['text']):
                continue

            # Skip very short turns (likely fragments)
            if len(turn['text']) >= 100:
                guest_turns.append(Turn(
                    speaker=speaker_name,
                    timestamp=turn['timestamp'],
                    text=turn['text'],
                    preceding_question=last_host_question,
                    source_file=source_file,
                ))

    return guest_turns


def chunk_turn(turn: Turn, max_chars: int = 1500, overlap: int = 200) -> list[dict]:
    """
    Split a turn into chunks if it's too long.

    Returns a list of chunk dictionaries with metadata.
    """
    text = turn.text

    if len(text) <= max_chars:
        return [{
            'text': text,
            'speaker': turn.speaker,
            'timestamp': turn.timestamp,
            'preceding_question': turn.preceding_question,
            'source_file': turn.source_file,
            'chunk_index': 0,
        }]

    # Split at paragraph boundaries
    paragraphs = text.split('\n\n')
    chunks = []
    current_chunk = ""
    chunk_index = 0

    for para in paragraphs:
        if len(current_chunk) + len(para) + 2 <= max_chars:
            if current_chunk:
                current_chunk += '\n\n' + para
            else:
                current_chunk = para
        else:
            if current_chunk:
                chunks.append({
                    'text': current_chunk,
                    'speaker': turn.speaker,
                    'timestamp': turn.timestamp,
                    'preceding_question': turn.preceding_question,
                    'source_file': turn.source_file,
                    'chunk_index': chunk_index,
                })
                chunk_index += 1
                # Add overlap from end of previous chunk
                overlap_text = current_chunk[-overlap:] if len(current_chunk) > overlap else current_chunk
                current_chunk = overlap_text + '\n\n' + para
            else:
                current_chunk = para

    # Don't forget the last chunk
    if current_chunk and len(current_chunk) >= 100:
        chunks.append({
            'text': current_chunk,
            'speaker': turn.speaker,
            'timestamp': turn.timestamp,
            'preceding_question': turn.preceding_question,
            'source_file': turn.source_file,
            'chunk_index': chunk_index,
        })

    return chunks


if __name__ == "__main__":
    # Test parsing
    import sys

    if len(sys.argv) > 1:
        test_file = Path(sys.argv[1])
    else:
        test_file = Path("transcripts/Shreyas Doshi.txt")

    if test_file.exists():
        turns = parse_transcript(test_file)
        print(f"Found {len(turns)} guest turns in {test_file.name}")
        for turn in turns[:3]:
            print(f"\n--- {turn.speaker} ({turn.timestamp}) ---")
            print(f"Q: {turn.preceding_question[:100]}...")
            print(f"A: {turn.text[:200]}...")
    else:
        print(f"File not found: {test_file}")

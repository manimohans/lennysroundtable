"""Verify transcript parsing captures all content correctly."""

import sys
from pathlib import Path

from .parser import (
    parse_transcript,
    SPEAKER_WITH_TIMESTAMP_PATTERN,
    SPEAKER_NO_TIMESTAMP_PATTERN,
    TIMESTAMP_ONLY_PATTERN,
    is_host,
    is_valid_speaker_name,
)


def verify_transcript(file_path: Path) -> dict:
    """
    Verify that we capture all guest content from a transcript.

    Capture % is computed as:
        parsed_guest_chars / total_guest_chars * 100

    Where:
        - total_guest_chars: All text attributed to non-host speakers in the raw file
        - parsed_guest_chars: Text in turns extracted by our parser

    The difference comes from:
        - Short turns (<100 chars) being filtered out
        - Sponsor content being filtered
        - Invalid speaker names being rejected
    """
    text = file_path.read_text(encoding='utf-8')

    # Try timestamp format first
    speaker_matches = list(SPEAKER_WITH_TIMESTAMP_PATTERN.finditer(text))
    timestamp_matches = list(TIMESTAMP_ONLY_PATTERN.finditer(text))

    # If no matches, try non-timestamp format
    if not speaker_matches:
        speaker_matches = list(SPEAKER_NO_TIMESTAMP_PATTERN.finditer(text))
        timestamp_matches = []

    # Combine and sort all markers
    all_markers = []
    for m in speaker_matches:
        ts = m.group(2) if m.lastindex >= 2 else ""
        name = m.group(1).strip()
        if is_valid_speaker_name(name):
            all_markers.append({
                'start': m.start(),
                'end': m.end(),
                'speaker': name,
                'timestamp': ts,
            })
    for m in timestamp_matches:
        all_markers.append({
            'start': m.start(),
            'end': m.end(),
            'speaker': None,
            'timestamp': m.group(1),
        })
    all_markers.sort(key=lambda x: x['start'])

    # Fill in speakers for continuations
    for i, marker in enumerate(all_markers):
        if marker['speaker'] is None:
            for j in range(i - 1, -1, -1):
                if all_markers[j]['speaker']:
                    marker['speaker'] = all_markers[j]['speaker']
                    break

    # Count characters attributed to guest speakers
    guest_chars = 0
    for i, marker in enumerate(all_markers):
        start = marker['end']
        end = all_markers[i + 1]['start'] if i + 1 < len(all_markers) else len(text)
        content_len = end - start

        if marker['speaker'] and not is_host(marker['speaker']):
            guest_chars += content_len

    # Parse with our actual parser
    turns = parse_transcript(file_path)
    parsed_guest_chars = sum(len(t.text) for t in turns)
    speakers = set(t.speaker for t in turns)

    return {
        'file': file_path.name,
        'total_chars': len(text),
        'guest_chars': guest_chars,
        'parsed_turns': len(turns),
        'parsed_guest_chars': parsed_guest_chars,
        'capture_ratio': parsed_guest_chars / guest_chars if guest_chars > 0 else 1.0,
        'speakers': speakers,
    }


def verify_all(transcripts_dir: Path, min_capture: float = 0.95) -> bool:
    """
    Verify all transcripts in a directory.

    Args:
        transcripts_dir: Path to directory containing transcript files
        min_capture: Minimum capture ratio required (0.0 - 1.0)

    Returns:
        True if all files pass verification, False otherwise
    """
    files = sorted(transcripts_dir.glob('*.txt'))

    if not files:
        print(f"No transcript files found in {transcripts_dir}")
        return False

    print(f"Verifying {len(files)} transcripts (min capture: {min_capture * 100:.0f}%)...")
    print()
    print(f"{'File':<45} {'Turns':>6} {'Capture':>8} {'Speakers'}")
    print("-" * 100)

    issues = []
    all_speakers = set()
    total_turns = 0
    total_chars = 0

    for f in files:
        try:
            result = verify_transcript(f)
            capture = result['capture_ratio']
            total_turns += result['parsed_turns']
            total_chars += result['parsed_guest_chars']

            for s in result['speakers']:
                all_speakers.add(s)

            if capture < min_capture:
                issues.append(result)
                status = "FAIL"
            else:
                status = "OK"

            speakers_str = ', '.join(list(result['speakers'])[:2])
            if len(result['speakers']) > 2:
                speakers_str += f" (+{len(result['speakers']) - 2})"

            if capture < min_capture or len(files) <= 50:
                print(f"{result['file'][:44]:<45} {result['parsed_turns']:>6} {capture * 100:>7.1f}% {speakers_str[:40]}")

        except Exception as e:
            issues.append({'file': f.name, 'error': str(e)})
            print(f"{f.name[:44]:<45} ERROR: {e}")

    print()
    print(f"Summary:")
    print(f"  Total files: {len(files)}")
    print(f"  Total turns parsed: {total_turns}")
    print(f"  Total characters: {total_chars:,}")
    print(f"  Unique speakers: {len(all_speakers)}")
    print()

    if issues:
        print(f"FAILED: {len(issues)} files below {min_capture * 100:.0f}% capture:")
        for r in issues[:10]:
            if 'error' in r:
                print(f"  - {r['file']}: {r['error']}")
            else:
                print(f"  - {r['file']}: {r['capture_ratio'] * 100:.1f}%")
        if len(issues) > 10:
            print(f"  ... and {len(issues) - 10} more")
        return False
    else:
        print(f"PASSED: All files have capture ratio >= {min_capture * 100:.0f}%")
        return True


def main():
    import argparse

    parser = argparse.ArgumentParser(description="Verify transcript parsing")
    parser.add_argument(
        "--transcripts-dir",
        type=Path,
        default=Path("transcripts"),
        help="Directory containing transcript files"
    )
    parser.add_argument(
        "--min-capture",
        type=float,
        default=0.95,
        help="Minimum capture ratio required (0.0 - 1.0)"
    )
    parser.add_argument(
        "--verbose",
        action="store_true",
        help="Show all files, not just failures"
    )
    args = parser.parse_args()

    if not args.transcripts_dir.exists():
        print(f"Transcripts directory not found: {args.transcripts_dir}")
        sys.exit(1)

    success = verify_all(args.transcripts_dir, args.min_capture)
    sys.exit(0 if success else 1)


if __name__ == "__main__":
    main()

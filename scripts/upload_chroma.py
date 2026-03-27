#!/usr/bin/env python3
"""
Upload the pre-built ChromaDB to HuggingFace Hub so Streamlit Cloud can
download it at startup — letting demo users skip the 50-minute local ingest.

Prerequisites:
    pip install huggingface_hub
    huggingface-cli login        # or export HF_TOKEN=hf_...

Usage:
    python scripts/upload_chroma.py --repo-id YOUR_HF_USERNAME/lennysroundtable-chroma

After upload, add the following to Streamlit Cloud secrets:
    HF_REPO_ID = "YOUR_HF_USERNAME/lennysroundtable-chroma"
"""

import argparse
import sys
import tarfile
from pathlib import Path

_PROJECT_ROOT = Path(__file__).parent.parent
CHROMA_PATH = _PROJECT_ROOT / "chroma_db"
ARCHIVE_NAME = "chroma_db.tar.gz"


def create_archive() -> Path:
    archive_path = _PROJECT_ROOT / ARCHIVE_NAME
    print(f"Archiving {CHROMA_PATH} → {archive_path}")
    with tarfile.open(archive_path, "w:gz") as tar:
        tar.add(CHROMA_PATH, arcname="chroma_db")
    size_mb = archive_path.stat().st_size / (1024 * 1024)
    print(f"Archive size: {size_mb:.0f} MB")
    return archive_path


def upload(archive_path: Path, repo_id: str) -> None:
    from huggingface_hub import HfApi

    api = HfApi()

    try:
        api.create_repo(repo_id=repo_id, repo_type="dataset", exist_ok=True)
        print(f"Dataset repo ready: https://huggingface.co/datasets/{repo_id}")
    except Exception as exc:
        print(f"Note: could not create repo (may already exist): {exc}")

    print("Uploading — this may take several minutes for a large archive ...")
    api.upload_file(
        path_or_fileobj=str(archive_path),
        path_in_repo=ARCHIVE_NAME,
        repo_id=repo_id,
        repo_type="dataset",
    )
    print(f"Upload complete: https://huggingface.co/datasets/{repo_id}")


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Upload pre-built ChromaDB to HuggingFace Hub for the hosted demo"
    )
    parser.add_argument(
        "--repo-id",
        required=True,
        help="HuggingFace dataset repo (e.g. your-username/lennysroundtable-chroma)",
    )
    parser.add_argument(
        "--keep-archive",
        action="store_true",
        help="Keep the local .tar.gz after upload (default: delete it)",
    )
    args = parser.parse_args()

    if not (CHROMA_PATH / "chroma.sqlite3").exists():
        print(f"ChromaDB not found at {CHROMA_PATH}")
        print("Run ingestion first:  uv run python -m roundtable.ingest")
        sys.exit(1)

    archive = create_archive()
    try:
        upload(archive, args.repo_id)
    finally:
        if not args.keep_archive:
            archive.unlink(missing_ok=True)
            print("Removed local archive.")

    print(f"\nNext: add this to your Streamlit Cloud secrets dashboard:")
    print(f'  HF_REPO_ID = "{args.repo_id}"')


if __name__ == "__main__":
    main()

"""Download pre-built ChromaDB from HuggingFace Hub for the hosted demo."""

import os
import tarfile
from pathlib import Path

_PROJECT_ROOT = Path(__file__).parent.parent
CHROMA_PATH = _PROJECT_ROOT / "chroma_db"
HF_FILENAME = "chroma_db.tar.gz"


def is_chroma_db_available() -> bool:
    """Return True if a populated ChromaDB exists at the expected path."""
    return (CHROMA_PATH / "chroma.sqlite3").exists()


def download_chroma_db(repo_id: str) -> bool:
    """
    Download and extract a pre-built ChromaDB archive from a HuggingFace dataset.

    Args:
        repo_id: HuggingFace dataset repo (e.g. "username/lennysroundtable-chroma")

    Returns:
        True if ChromaDB is now available, False on failure.
    """
    try:
        from huggingface_hub import hf_hub_download
    except ImportError:
        print("huggingface_hub is not installed. Run: pip install huggingface_hub")
        return False

    print(f"Downloading ChromaDB from HuggingFace: {repo_id} ...")
    try:
        archive_path = hf_hub_download(
            repo_id=repo_id,
            filename=HF_FILENAME,
            repo_type="dataset",
        )
    except Exception as exc:
        print(f"Download failed: {exc}")
        return False

    print("Extracting archive ...")
    try:
        with tarfile.open(archive_path, "r:gz") as tar:
            tar.extractall(path=str(_PROJECT_ROOT))
    except Exception as exc:
        print(f"Extraction failed: {exc}")
        return False

    if is_chroma_db_available():
        print("ChromaDB ready.")
        return True

    print("Extraction succeeded but chroma.sqlite3 not found — check archive structure.")
    return False

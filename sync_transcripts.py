#!/usr/bin/env python3
"""
Sync transcripts from Dropbox shared folder.

Usage:
    uv run sync_transcripts.py

First time setup:
    1. Go to https://www.dropbox.com/developers/apps
    2. Create an app (scoped access, full dropbox)
    3. Generate an access token
    4. Set DROPBOX_ACCESS_TOKEN environment variable or create .env file
"""
# /// script
# requires-python = ">=3.10"
# dependencies = [
#     "dropbox",
#     "python-dotenv",
# ]
# ///

import os
import json
import hashlib
from pathlib import Path
from datetime import datetime

import dropbox
from dropbox.exceptions import ApiError
from dotenv import load_dotenv

load_dotenv()

# Configuration
SHARED_FOLDER_URL = "https://www.dropbox.com/scl/fo/yxi4s2w998p1gvtpu4193/AMdNPR8AOw0lMklwtnC0TrQ?rlkey=j06x0nipoti519e0xgm23zsn9&e=1&st=ahz0fj11&dl=0"
LOCAL_DIR = Path(__file__).parent / "transcripts"
MANIFEST_FILE = LOCAL_DIR / ".sync_manifest.json"


def load_manifest() -> dict:
    """Load the sync manifest tracking downloaded files."""
    if MANIFEST_FILE.exists():
        return json.loads(MANIFEST_FILE.read_text())
    return {"files": {}, "last_sync": None}


def save_manifest(manifest: dict):
    """Save the sync manifest."""
    manifest["last_sync"] = datetime.now().isoformat()
    MANIFEST_FILE.write_text(json.dumps(manifest, indent=2))


def get_file_hash(content: bytes) -> str:
    """Calculate content hash for change detection."""
    return hashlib.sha256(content).hexdigest()


def sync_dropbox_folder():
    """Sync files from Dropbox shared folder to local directory."""
    access_token = os.getenv("DROPBOX_ACCESS_TOKEN")
    if not access_token:
        print("Error: DROPBOX_ACCESS_TOKEN not set.")
        print("\nTo set up:")
        print("1. Go to https://www.dropbox.com/developers/apps")
        print("2. Create an app with 'scoped access' and 'full Dropbox' access")
        print("3. In Permissions tab, enable: sharing.read, files.content.read")
        print("4. Generate an access token in the Settings tab")
        print("5. Run: export DROPBOX_ACCESS_TOKEN='your_token_here'")
        print("   Or create a .env file with: DROPBOX_ACCESS_TOKEN=your_token_here")
        return

    # Ensure local directory exists
    LOCAL_DIR.mkdir(parents=True, exist_ok=True)

    # Initialize Dropbox client
    dbx = dropbox.Dropbox(access_token)

    # Load manifest
    manifest = load_manifest()

    try:
        # Get shared link metadata to list folder contents
        shared_link = dropbox.files.SharedLink(url=SHARED_FOLDER_URL)

        print(f"Fetching file list from shared folder...")
        result = dbx.files_list_folder(path="", shared_link=shared_link)

        all_entries = result.entries
        while result.has_more:
            result = dbx.files_list_folder_continue(result.cursor)
            all_entries.extend(result.entries)

        files_to_download = []

        for entry in all_entries:
            if isinstance(entry, dropbox.files.FileMetadata):
                # Check if file needs downloading (new or modified)
                file_key = entry.name
                server_modified = entry.server_modified.isoformat() if entry.server_modified else None
                content_hash = entry.content_hash

                cached = manifest["files"].get(file_key, {})
                if cached.get("content_hash") != content_hash:
                    files_to_download.append(entry)
                else:
                    print(f"  Skipping (unchanged): {entry.name}")

        if not files_to_download:
            print("All files are up to date!")
            save_manifest(manifest)
            return

        print(f"\nDownloading {len(files_to_download)} file(s)...")

        for entry in files_to_download:
            print(f"  Downloading: {entry.name}")
            try:
                metadata, response = dbx.sharing_get_shared_link_file(
                    url=SHARED_FOLDER_URL,
                    path=f"/{entry.name}"
                )
                content = response.content

                # Save file
                local_path = LOCAL_DIR / entry.name
                local_path.write_bytes(content)

                # Update manifest
                manifest["files"][entry.name] = {
                    "content_hash": entry.content_hash,
                    "server_modified": entry.server_modified.isoformat() if entry.server_modified else None,
                    "size": entry.size,
                    "downloaded_at": datetime.now().isoformat()
                }
                print(f"    ✓ Saved ({entry.size:,} bytes)")

            except ApiError as e:
                print(f"    ✗ Error downloading {entry.name}: {e}")

        save_manifest(manifest)
        print(f"\nSync complete! Files saved to: {LOCAL_DIR}")
        print(f"Total files tracked: {len(manifest['files'])}")

    except ApiError as e:
        print(f"Dropbox API error: {e}")
        if "invalid_access_token" in str(e):
            print("\nYour access token may have expired. Generate a new one at:")
            print("https://www.dropbox.com/developers/apps")


if __name__ == "__main__":
    sync_dropbox_folder()

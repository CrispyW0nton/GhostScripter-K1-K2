#!/usr/bin/env python3
"""
build_tools/create_release.py
==============================
Create a GitHub release and upload build artefacts.

This script is designed to be called from GitHub Actions after a successful
build, but can also be run locally if you have a GITHUB_TOKEN set.

Usage
-----
    # Automatic (called from CI after build.py)
    python build_tools/create_release.py

    # Manual (local)
    GITHUB_TOKEN=ghp_xxx python build_tools/create_release.py --tag v1.0.0 --draft

Environment variables
---------------------
    GITHUB_TOKEN      : Personal access token (required)
    GITHUB_REPOSITORY : owner/repo  (default: YOUR_USERNAME/GhostScripter-K1-K2)

CLI arguments
-------------
    --tag      : Git tag for the release  (default: v{VERSION} from constants.py)
    --draft    : Create as a draft release (not published yet)
    --prerelease: Mark as pre-release
    --notes    : Path to release-notes file (default: auto-generated)
"""

from __future__ import annotations

import argparse
import glob
import json
import os
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
DIST_DIR = ROOT / "dist"

REPO   = os.environ.get("GITHUB_REPOSITORY", "YOUR_USERNAME/GhostScripter-K1-K2")
API    = "https://api.github.com"
UPLOAD = "https://uploads.github.com"


def _read_version() -> str:
    constants = ROOT / "ghostscripter" / "core" / "constants.py"
    if constants.exists():
        for line in constants.read_text(encoding="utf-8").splitlines():
            if line.startswith("APP_VERSION"):
                return line.split("=", 1)[1].strip().strip('"').strip("'")
    return "1.0.0"


def _headers(token: str) -> dict:
    return {
        "Authorization": f"Bearer {token}",
        "Accept": "application/vnd.github+json",
        "X-GitHub-Api-Version": "2022-11-28",
    }


def _auto_notes(version: str) -> str:
    return f"""## GhostScripter-K1-K2 v{version}

All-in-one IDE for modding **Knights of the Old Republic 1 & 2 TSL**.

### What's included
| File | Description |
|------|-------------|
| `GhostScripter-K1-K2-v{version}-windows-portable.zip` | Portable folder — unzip and run `GhostScripter-K1-K2.exe` |
| `GhostScripter-K1-K2-v{version}-Setup.exe` | Windows installer (Inno Setup) |

### Quick Start
1. Download the **Setup.exe** or the portable **ZIP**
2. Run `GhostScripter-K1-K2.exe`
3. Go to **File → New Project**, choose your game (K1 or K2 TSL) and a folder
4. Start writing scripts, building quests, and authoring dialogue trees!

### Requires
- Windows 10 / 11 (64-bit)  — Linux/macOS: build from source (see README)
- Optional: [GhostRigger](https://github.com/YOUR_USERNAME/GhostRigger) for 3D model rigging integration

### Changelog
See [CREDITS.md](https://github.com/{REPO}/blob/main/CREDITS.md) for full history.
"""


def create_release(token: str, tag: str, name: str, body: str,
                   draft: bool, prerelease: bool) -> dict:
    try:
        import urllib.request
        data = json.dumps({
            "tag_name":   tag,
            "name":       name,
            "body":       body,
            "draft":      draft,
            "prerelease": prerelease,
        }).encode("utf-8")
        req = urllib.request.Request(
            f"{API}/repos/{REPO}/releases",
            data=data,
            headers={**_headers(token), "Content-Type": "application/json"},
            method="POST",
        )
        with urllib.request.urlopen(req) as resp:
            return json.loads(resp.read())
    except Exception as e:
        print(f"  [ERR] Could not create release: {e}", file=sys.stderr)
        sys.exit(1)


def upload_asset(token: str, upload_url: str, path: Path) -> None:
    import urllib.request
    # upload_url looks like  https://uploads.github.com/repos/.../assets{?name,label}
    upload_url = upload_url.split("{")[0]  # strip template
    url = f"{upload_url}?name={path.name}"
    mime = "application/zip" if path.suffix == ".zip" else "application/octet-stream"
    data = path.read_bytes()
    req = urllib.request.Request(
        url, data=data,
        headers={**_headers(token), "Content-Type": mime},
        method="POST",
    )
    print(f"  Uploading {path.name}  ({len(data)/1_048_576:.1f} MB)…", flush=True)
    try:
        with urllib.request.urlopen(req) as resp:
            result = json.loads(resp.read())
            print(f"  [OK] Uploaded → {result.get('browser_download_url', '?')}", flush=True)
    except Exception as e:
        print(f"  [WARN] Upload failed: {e}", file=sys.stderr)


def _find_artefacts() -> list[Path]:
    patterns = [
        str(DIST_DIR / "*.zip"),
        str(DIST_DIR / "installer" / "*.exe"),
    ]
    files = []
    for pat in patterns:
        files.extend(Path(p) for p in glob.glob(pat))
    return files


def main() -> None:
    p = argparse.ArgumentParser(description="Create a GitHub release for GhostScripter-K1-K2.")
    version = _read_version()
    p.add_argument("--tag",        default=f"v{version}", help="Git tag (e.g. v1.0.0)")
    p.add_argument("--draft",      action="store_true",   help="Create as draft release")
    p.add_argument("--prerelease", action="store_true",   help="Mark as pre-release")
    p.add_argument("--notes",      default=None,          help="Path to release notes file")
    args = p.parse_args()

    token = os.environ.get("GITHUB_TOKEN")
    if not token:
        print("  [ERR] GITHUB_TOKEN environment variable not set.", file=sys.stderr)
        sys.exit(1)

    body = Path(args.notes).read_text(encoding="utf-8") if args.notes else _auto_notes(version)
    name = f"GhostScripter-K1-K2 {args.tag}"

    print(f"\n  Creating GitHub release {args.tag} on {REPO}…", flush=True)
    release = create_release(token, args.tag, name, body, args.draft, args.prerelease)
    print(f"  [OK] Release created → {release.get('html_url', '?')}", flush=True)

    artefacts = _find_artefacts()
    if not artefacts:
        print("  [WARN] No build artefacts found in dist/ — skipping uploads.", flush=True)
        return

    upload_url = release.get("upload_url", "")
    for art in artefacts:
        upload_asset(token, upload_url, art)

    print("\n  Release complete.", flush=True)


if __name__ == "__main__":
    main()

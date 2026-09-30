"""Download the Twemoji SVG for every emoji used in content/topics/*.yaml.

Word pictures (image.kind: emoji), topic icons and letter anchors stay plain
emoji characters in the YAML; the frontend maps each character to
media/twemoji/<codepoints>.svg at render time (see frontend/src/twemoji.ts),
so this script must be re-run after adding words with new emoji. Existing
files are never re-downloaded. A missing emoji fails the run with its name.

Twemoji graphics are CC BY 4.0 (https://github.com/jdecked/twemoji).

Run from the repo root:

    make twemoji
    # or
    uv run --no-project --with pyyaml python scripts/fetch_twemoji.py
"""

from __future__ import annotations

import sys
import urllib.error
import urllib.request
from pathlib import Path

import yaml

REPO_DIR = Path(__file__).resolve().parents[1]
TOPICS_DIR = REPO_DIR / "content" / "topics"
OUT_DIR = REPO_DIR / "media" / "twemoji"

TWEMOJI_VERSION = "17.0.0"
BASE_URL = f"https://raw.githubusercontent.com/jdecked/twemoji/v{TWEMOJI_VERSION}/assets/svg"

ZWJ = "‍"
VS16 = "️"

# Emoji hardcoded in the frontend UI (tabs, section icons, Тренировка row, ReplaySheet menu)
# rather than read from content/topics/*.yaml — collect_emoji() would otherwise miss them.
INTERFACE_EMOJI = {"☀️", "🧭", "🗺️", "🔤", "🧩", "💬", "🔁", "🎯", "🔄"}


def file_stem(emoji: str) -> str:
    """Twemoji file name for an emoji: hex codepoints joined by '-'.

    Mirrors twemoji's grabTheRightIcon: the FE0F presentation selector is
    dropped unless the sequence contains a ZWJ. Keep in sync with
    frontend/src/twemoji.ts.
    """
    if ZWJ not in emoji:
        emoji = emoji.replace(VS16, "")
    return "-".join(f"{ord(ch):x}" for ch in emoji)


def collect_emoji() -> set[str]:
    found: set[str] = set(INTERFACE_EMOJI)
    for topic_file in sorted(TOPICS_DIR.glob("*.yaml")):
        topic = yaml.safe_load(topic_file.read_text(encoding="utf-8"))
        if topic.get("icon"):
            found.add(topic["icon"])
        for word in topic["words"]:
            image = word.get("image") or {}
            if image.get("kind") == "emoji":
                found.add(image["value"])
            anchor = word.get("anchor") or {}
            if anchor.get("emoji"):
                found.add(anchor["emoji"])
    return found


def main() -> int:
    OUT_DIR.mkdir(parents=True, exist_ok=True)
    downloaded = 0
    skipped = 0
    missing: list[str] = []

    for emoji in sorted(collect_emoji()):
        out = OUT_DIR / f"{file_stem(emoji)}.svg"
        if out.exists():
            skipped += 1
            continue
        try:
            with urllib.request.urlopen(f"{BASE_URL}/{out.name}") as resp:
                out.write_bytes(resp.read())
        except urllib.error.HTTPError as e:
            missing.append(f"{emoji} ({out.name}): HTTP {e.code}")
            continue
        downloaded += 1
        print(f"{out.relative_to(REPO_DIR)}  ←  {emoji}")

    print(f"done: {downloaded} downloaded, {skipped} skipped (already present)")
    if missing:
        print("missing in Twemoji:", *missing, sep="\n  ", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())

"""Generate temporary TTS audio for every word in content/topics/*.yaml.

Uses Microsoft's native Georgian neural voices through edge-tts, which needs
no API key. Output goes to media/audio/<topic>/<slug>.mp3. Existing files are
never overwritten, so recordings made by a native speaker stay untouched.

Run from the repo root:

    make tts
    # or
    uv run --no-project --with edge-tts --with pyyaml python scripts/gen_tts.py
"""

from __future__ import annotations

import argparse
import asyncio
from pathlib import Path

import edge_tts
import yaml

REPO_DIR = Path(__file__).resolve().parents[1]
TOPICS_DIR = REPO_DIR / "content" / "topics"
AUDIO_DIR = REPO_DIR / "media" / "audio"

DEFAULT_VOICE = "ka-GE-EkaNeural"  # the other native voice: ka-GE-GiorgiNeural
DEFAULT_RATE = "-15%"  # slightly slower than natural: easier for a child to repeat


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    parser.add_argument(
        "--voice",
        default=DEFAULT_VOICE,
        help=f"edge-tts voice name (default {DEFAULT_VOICE})",
    )
    parser.add_argument(
        "--rate",
        default=DEFAULT_RATE,
        help=f"speech rate offset like -15%% (default {DEFAULT_RATE})",
    )
    return parser.parse_args()


async def synthesize(text: str, out: Path, voice: str, rate: str) -> None:
    out.parent.mkdir(parents=True, exist_ok=True)
    await edge_tts.Communicate(text, voice=voice, rate=rate).save(str(out))


async def main() -> None:
    args = parse_args()
    generated = 0
    skipped = 0

    for topic_file in sorted(TOPICS_DIR.glob("*.yaml")):
        topic = yaml.safe_load(topic_file.read_text(encoding="utf-8"))
        for word in topic["words"]:
            out = AUDIO_DIR / topic["slug"] / f"{word['slug']}.mp3"
            if out.exists():
                skipped += 1
                continue
            await synthesize(word["ka"], out, args.voice, args.rate)
            generated += 1
            print(f"{out.relative_to(REPO_DIR)}  ←  {word['ka']}")

    print(f"done: {generated} generated, {skipped} skipped (already present)")


if __name__ == "__main__":
    asyncio.run(main())

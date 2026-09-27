"""Generate temporary TTS audio for every word in content/topics/*.yaml.

Uses Microsoft's native Georgian neural voices through edge-tts, which needs
no API key. Output goes to media/audio/<topic>/<slug>.mp3. Existing files are
never overwritten, so recordings made by a native speaker stay untouched.

A letter (a word with an `anchor`) is two clips glued by ffmpeg with a pause
in between: edge-tts escapes SSML, so a <break> cannot be passed, and "ბ. ბურთი."
read as one utterance sounds like a single long word.

Run from the repo root:

    make tts
    # or
    uv run --no-project --with edge-tts --with pyyaml python scripts/gen_tts.py
"""

from __future__ import annotations

import argparse
import asyncio
import subprocess
import tempfile
from pathlib import Path

import edge_tts
import yaml

REPO_DIR = Path(__file__).resolve().parents[1]
TOPICS_DIR = REPO_DIR / "content" / "topics"
AUDIO_DIR = REPO_DIR / "media" / "audio"

DEFAULT_VOICE = "ka-GE-EkaNeural"  # the other native voice: ka-GE-GiorgiNeural
DEFAULT_RATE = "-15%"  # slightly slower than natural: easier for a child to repeat

# Silence added after the letter's sound, before the anchor word. edge-tts leaves
# ~0.3 s of its own tail after trimming, so the audible pause is about 0.9 s.
LETTER_PAUSE_SEC = 0.6

# Spoken feedback in the quiz, media/audio/ui/<name>.mp3. Georgian like everything else.
PHRASES = {
    "correct": "სწორია! ყოჩაღ!",  # "correct, well done"
    "wrong": "არა, ეს არასწორია. სცადე კიდევ.",  # "no, that is wrong, try again"
}


def parts_for(word: dict) -> list[str]:
    """A letter is read as its sound, a pause, then its anchor word: "ბ." … "ბურთი."."""
    anchor = word.get("anchor")
    if anchor:
        return [f"{word['ka']}.", f"{anchor['ka']}."]
    return [str(word["ka"])]


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


async def synthesize_parts(parts: list[str], out: Path, voice: str, rate: str) -> None:
    """One clip per part, joined with LETTER_PAUSE_SEC of silence between them."""
    if len(parts) == 1:
        await synthesize(parts[0], out, voice, rate)
        return
    with tempfile.TemporaryDirectory() as tmp:
        clips = [Path(tmp) / f"{i}.mp3" for i in range(len(parts))]
        for text, clip in zip(parts, clips, strict=True):
            await synthesize(text, clip, voice, rate)
        join_with_pauses(clips, out)


def join_with_pauses(clips: list[Path], out: Path) -> None:
    """Trim each clip's trailing silence (edge-tts pads ~1.5 s), pad the pause, concat."""
    chain = []
    for i in range(len(clips) - 1):
        chain.append(
            f"[{i}:a]silenceremove=stop_periods=1:stop_duration=0.15:stop_threshold=-40dB,"
            f"apad=pad_dur={LETTER_PAUSE_SEC}[p{i}]"
        )
    inputs = "".join(f"[p{i}]" for i in range(len(clips) - 1)) + f"[{len(clips) - 1}:a]"
    chain.append(f"{inputs}concat=n={len(clips)}:v=0:a=1[o]")
    cmd = ["ffmpeg", "-hide_banner", "-loglevel", "error", "-y"]
    for clip in clips:
        cmd += ["-i", str(clip)]
    cmd += [
        "-filter_complex",
        ";".join(chain),
        "-map",
        "[o]",
        "-ar",
        "24000",
        "-b:a",
        "48k",
        str(out),
    ]
    subprocess.run(cmd, check=True)


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
            parts = parts_for(word)
            await synthesize_parts(parts, out, args.voice, args.rate)
            generated += 1
            print(f"{out.relative_to(REPO_DIR)}  ←  {' … '.join(parts)}")

    for name, text in PHRASES.items():
        out = AUDIO_DIR / "ui" / f"{name}.mp3"
        if out.exists():
            skipped += 1
            continue
        await synthesize(text, out, args.voice, args.rate)
        generated += 1
        print(f"{out.relative_to(REPO_DIR)}  ←  {text}")

    print(f"done: {generated} generated, {skipped} skipped (already present)")


if __name__ == "__main__":
    asyncio.run(main())

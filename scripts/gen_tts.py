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
import re
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
# A lone sound is read at this rate (the anchor word keeps --rate): stretched a
# little, it is easier to catch. Rate and punctuation change its length only
# slightly (0.2-0.3 s for a consonant), so the level is what matters most.
LETTER_RATE = "-40%"
# A lone consonant comes out ~10 dB quieter than a word (peak -15 dB vs -5 dB)
# and is simply not heard before the word; the clip is levelled to this peak.
LETTER_PEAK_DB = -2.0
# Trim the synthesizer's silence around the sound: ~0.25 s in front (keep 50 ms)
# and ~1.5 s of tail, so the pause is ours, not edge-tts's.
TRIM = (
    "silenceremove=start_periods=1:start_silence=0.05:start_threshold=-40dB:"
    "stop_periods=1:stop_duration=0.15:stop_threshold=-40dB"
)

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
    """One clip per part, joined with LETTER_PAUSE_SEC of silence between them.

    Every part but the last is a lone sound: read at LETTER_RATE, trimmed and
    levelled to LETTER_PEAK_DB. The last part (the anchor word) is left as read.
    """
    if len(parts) == 1:
        await synthesize(parts[0], out, voice, rate)
        return
    with tempfile.TemporaryDirectory() as tmp:
        clips = [Path(tmp) / f"{i}.mp3" for i in range(len(parts))]
        for i, (text, clip) in enumerate(zip(parts, clips, strict=True)):
            await synthesize(
                text, clip, voice, LETTER_RATE if i < len(parts) - 1 else rate
            )
        join_with_pauses(clips, out)


def peak_db(clip: Path) -> float:
    """Peak level of the clip in dBFS, from ffmpeg's volumedetect (printed on stderr)."""
    cmd = [
        "ffmpeg",
        "-hide_banner",
        "-i",
        str(clip),
        "-af",
        "volumedetect",
        "-f",
        "null",
        "-",
    ]
    err = subprocess.run(cmd, capture_output=True, text=True, check=True).stderr
    m = re.search(r"max_volume: (-?[\d.]+) dB", err)
    return float(m.group(1)) if m else 0.0


def join_with_pauses(clips: list[Path], out: Path) -> None:
    """Level, trim and pad every sound clip, then concat them with the final word.

    Levelling goes before trimming: "ვ" peaks at -34 dB as read, and the -40 dB
    trim threshold would swallow it whole.
    """
    chain = []
    for i in range(len(clips) - 1):
        gain = LETTER_PEAK_DB - peak_db(clips[i])
        chain.append(
            f"[{i}:a]volume={gain:.1f}dB,{TRIM},apad=pad_dur={LETTER_PAUSE_SEC}[p{i}]"
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

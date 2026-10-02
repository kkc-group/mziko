# Content

Word lists live in `topics/*.yaml`, one file per topic. The order of words in a
file is the order in which the child learns them. Load into the database with
`python -m app.seed` (from `backend/`); the command is idempotent and upserts by
`topic.slug` + `word.slug`.

Format:

```yaml
slug: colors
title_ru: Цвета
title_ka: ფერები
icon: "🎨"
words:
  - slug: red
    ka: წითელი
    tr: цители        # Cyrillic hint, approximate
    ru: красный
    image: {kind: color, value: "#E53935"}
```

`image.kind` is one of `emoji` (value is the emoji), `color` (value is a hex
colour, rendered as a blob of that colour), `file` (value is the picture's URL,
`/media/images/<topic>/<slug>.png` or `.svg`, see below) or `text` (no picture:
the value, a letter or the word itself, is drawn as large Georgian text).

## Adding a topic

1. Write `topics/<slug>.yaml` and add the slug to `order.yaml` on the line
   below the topic it should follow. `order.yaml` is the whole path, top to
   bottom; to move a topic, move its line. The seed refuses a topic file that
   is not listed, a slug listed twice and a slug without a file. The section
   on the lessons screen comes from the slug (`letters-*`, `syllables`, the
   rest are words); nothing else needs to know about the topic. A topic is
   cut into lessons by itself: equal parts of at most 10 words.
2. Pictures: an emoji per word where Unicode has one; otherwise drop a PNG with
   a transparent background into `media/images/<slug>/<word slug>.png` (any
   size, the object anywhere in the frame) and point `image` at it:
   `image: {kind: file, value: /media/images/school-items/desk.png}`. An SVG is
   used as it is, with a square `viewBox` around the drawing.
3. From the repo root: `make images` (crops and shrinks the PNGs in place),
   `make twemoji` (bundles new emoji), `make tts` (temporary audio for words
   without a recording), then `make seed`.

Tests count topics, words and lessons from the YAML, so no number needs
updating. `tests/test_seed.py` also checks that every `file` picture exists.
Removing or moving a word is the one thing the seed does not do: rows already
in the database stay (a child's progress must survive), so a word moved to
another topic has to be deleted from the old one by hand.

## Letters, syllables and text cards

The first-grade programme (`letters-1` … `letters-4`, `syllables`, then the
vocabulary topics) uses `text` cards. Rules the loader enforces:

- A text card may wrap at spaces but never inside a word: no run of letters
  longer than 10 (`დილა მშვიდობისა` fits, one 12-letter word does not).
- Within a topic, slugs, Georgian words and pictures are all unique. Quiz
  distractors come from the same topic, so two words sharing a picture would
  make "listen and find" unanswerable.
- A Georgian word appears in one topic only (checked by `tests/test_seed.py`);
  syllables are exempt (`მე` the syllable may equal `მე` the word).

Text cards only get the "listen and find" game; "recall the word" is skipped
because the card *is* the word. A letter may carry an `anchor`, the example word
shown under it on the intro card:

```yaml
  - slug: ban
    ka: ბ
    tr: ба
    ru: буква б
    image: {kind: text, value: ბ}
    anchor: {ka: ბურთი, tr: бурти, ru: мяч, emoji: "⚽"}   # emoji is optional
```

A consonant's `tr` is the syllable the voice says, with «а» («ба», «дза»,
«къа»); a vowel's `tr` is the vowel itself. A lone consonant is near-inaudible,
so `make tts` reads a letter as that syllable followed by the anchor word, and
the hint under the letter must match what is heard.

Words that still lack a good picture are text cards marked `# TODO picture`;
`grep -rn "TODO picture" content/topics` lists them. Letter order follows the
primer tradition (Deda Ena), not the alphabet; reorder by moving lines.

Slugs `on`, `yes`, `no` must be quoted: bare, YAML reads them as booleans.

## Emoji pictures

Emoji stay plain characters in the YAML (word images, topic `icon`, letter
`anchor.emoji`), but the app draws them from the bundled Twemoji set so every
device shows the same picture. After adding a word with a new emoji run
`make twemoji` (from the repo root): it downloads the missing SVGs into
`media/twemoji/` and fails with the emoji name if Twemoji has no such file.
The files are committed like the audio.

Twemoji graphics are CC BY 4.0 (https://github.com/jdecked/twemoji). The
attribution line belongs on the app's future settings / about screen.

## Native speaker review required

The Cyrillic transcriptions (`tr`) are approximate: Georgian ejective consonants
have no Cyrillic equivalent. All Georgian text and all transcriptions in this
directory must be checked by a native speaker before launch, and the temporary
TTS audio in `media/audio/` must be replaced by native recordings.

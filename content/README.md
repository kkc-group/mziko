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
order: 2
words:
  - slug: red
    ka: წითელი
    tr: цители        # Cyrillic hint, approximate
    ru: красный
    image: {kind: color, value: "#E53935"}
```

`image.kind` is one of `emoji` (value is the emoji), `color` (value is a hex
colour, rendered as a blob of that colour), `file` (value is a path under
`/media/images`, reserved for later) or `text` (no picture: the value, a letter
or the word itself, is drawn as large Georgian text).

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
    tr: б
    ru: буква б
    image: {kind: text, value: ბ}
    anchor: {ka: ბურთი, tr: бурти, ru: мяч, emoji: "⚽"}   # emoji is optional
```

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

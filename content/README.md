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
colour, rendered as a blob of that colour) or `file` (value is a path under
`/media/images`, reserved for later).

## Native speaker review required

The Cyrillic transcriptions (`tr`) are approximate: Georgian ejective consonants
have no Cyrillic equivalent. All Georgian text and all transcriptions in this
directory must be checked by a native speaker before launch, and the temporary
TTS audio in `media/audio/` must be replaced by native recordings.

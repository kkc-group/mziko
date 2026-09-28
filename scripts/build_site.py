"""Build the public site (GitHub Pages) from docs/general/parent-guide.md.

The guide is the single source of the page text: the landing is that file
rendered into site/template.html, so a change in the guide is a change on the
site with no extra step. Output goes to _site/: index.html, the screenshots the
guide refers to, and the old static POC under poc/.

What the converter does on top of plain Markdown, in the order it happens:
  * the first two paragraphs before the first `##` become the hero lead and
    the "two participants" line under the table of contents;
  * every `## N. Title` becomes a card with a numbered badge, every `###` gets
    an anchor and a line in the table of contents;
  * a blockquote is a bot dialogue: `**Вы:**` / `**Бот:**` open a message,
    `*[кнопка]*` lines are the keyboard under it, backtick options after a
    `*[label:]*` are a settings row with the ticked one selected;
  * tables are wrapped for horizontal scroll; the commands, coins and
    programme tables are recognised by their header so the programme can
    collapse into cards on a phone;
  * `<figure><img>` in the screenshot blocks gets a device frame with the
    picture's real aspect ratio read from the PNG header;
  * Georgian text is wrapped in `.ka` so it renders in the Georgian font.

Run: make site   (uv run --no-project --with markdown python scripts/build_site.py)
"""

from __future__ import annotations

import datetime as dt
import re
import shutil
import struct
import subprocess
import sys
from dataclasses import dataclass, field
from pathlib import Path

import markdown

ROOT = Path(__file__).resolve().parents[1]
GUIDE = ROOT / "docs" / "general" / "parent-guide.md"
SHOTS_DIR = GUIDE.parent / "parent-guide"
TEMPLATE = ROOT / "site" / "template.html"
POC_DIR = ROOT / "site" / "poc"
# The POC plays its sound from a relative media/audio/colors/ next to itself.
POC_AUDIO = ROOT / "media" / "audio" / "colors"
OUT = ROOT / "_site"

BOT_URL = "https://t.me/MyMzikoBot"

# Screenshots stacked in the hero: (file in docs/general/parent-guide/, alt).
HERO_SHOTS = [
    ("home-after.png", "Главный экран после занятия"),
    ("lesson-listen.png", "Послушай и найди"),
    ("lesson-done.png", "Итог занятия"),
]

SECTION_RE = re.compile(r"^## (\d+)\. (.+?)\s*$", re.MULTILINE)
SPEAKER_RE = re.compile(r"^\*\*(Вы|Бот):\*\*\s*(.*)$")
BUTTON_RE = re.compile(r"\*\[(.+?)\]\*")
OPTION_RE = re.compile(r"`([^`]+)`")
DOTS_RE = re.compile(r"^([●○]{3})\s*")
KA_RE = re.compile(r"[ა-ჿ]+(?:[ ,/…]+[ა-ჿ]+)*")
TAG_SPLIT_RE = re.compile(r"(<[^>]+>)")
TAG_RE = re.compile(r"<[^>]+>")
CHAT_TOKEN = "@@CHAT{}@@"


@dataclass
class Message:
    me: bool
    lines: list[str | None] = field(default_factory=list)  # None is a blank line
    keyboard: list[str] = field(default_factory=list)  # rendered rows


@dataclass
class Section:
    number: int
    title: str
    body: str
    subsections: list[tuple[str, str]] = field(default_factory=list)  # (id, label)


def inline(text: str) -> str:
    """Markdown inline markup (bold, code) without the wrapping paragraph."""
    html = markdown.markdown(text)
    if html.startswith("<p>") and html.endswith("</p>"):
        html = html[3:-4]
    return html


def strip_tags(html: str) -> str:
    return TAG_RE.sub("", html)


def wrap_georgian(html: str) -> str:
    """Wrap Georgian runs in the text nodes (never inside tags) into `.ka`."""
    parts = TAG_SPLIT_RE.split(html)
    for i in range(0, len(parts), 2):
        parts[i] = KA_RE.sub(
            lambda m: f'<span class="ka">{m.group(0)}</span>', parts[i]
        )
    return "".join(parts)


# ---------------------------------------------------------------- bot chat


def unwrap(quote_lines: list[str]) -> list[str]:
    """Join lines the author wrapped at 80 columns back into one bot line.

    A line continues onto the next when it is long, does not end a sentence
    and the next line is not a speaker, a keyboard or a blank line. A short
    line ("Занимался 5 из 7 дней") is a line of its own even without a period.
    """
    out: list[str] = []
    for raw in quote_lines:
        line = raw.strip()
        prev = out[-1] if out else ""
        starts_block = not line or line.startswith("*[") or SPEAKER_RE.match(line)
        if prev and not starts_block and len(prev) >= 60 and prev[-1] not in ".!?:…»)":
            out[-1] = f"{prev} {line}"
        else:
            out.append(line)
    return out


def render_keyboard_line(line: str) -> str:
    labels = [re.sub(r"^кнопка:\s*", "", label) for label in BUTTON_RE.findall(line)]
    options = OPTION_RE.findall(BUTTON_RE.sub("", line))
    if options:
        spans = []
        for opt in options:
            selected = opt.startswith("✓")
            text = opt.lstrip("✓ ").strip()
            spans.append(
                f'<span class="sel">{text}</span>'
                if selected
                else f"<span>{text}</span>"
            )
        return f'<div class="row"><i>{inline(labels[0])}</i>{"".join(spans)}</div>'
    spans = []
    for label in labels:
        cls = ' class="sel"' if "✓" in label else ""
        spans.append(f"<span{cls}>{inline(label)}</span>")
    return "".join(spans)


def render_chat(quote_lines: list[str], nested: bool) -> str:
    messages: list[Message] = []
    current: Message | None = None
    for line in unwrap(quote_lines):
        if not line:
            if current is not None:
                current.lines.append(None)
            continue
        spoken = SPEAKER_RE.match(line)
        if spoken:
            current = Message(me=spoken.group(1) == "Вы")
            messages.append(current)
            if spoken.group(2):
                current.lines.append(spoken.group(2))
            continue
        if current is None:
            current = Message(me=False)
            messages.append(current)
        if line.startswith("*["):
            current.keyboard.append(render_keyboard_line(line))
        else:
            current.lines.append(line)

    out = []
    for msg in messages:
        rendered = []
        first = True
        for text in msg.lines:
            if text is None:
                rendered.append('<span class="gap"></span>')
                continue
            text = DOTS_RE.sub(r'<span class="dots">\1</span>', text)
            html = inline(text)
            rendered.append(html if first else f'<span class="ln">{html}</span>')
            first = False
        keyboard = (
            f'<div class="kb">{"".join(msg.keyboard)}</div>' if msg.keyboard else ""
        )
        who = "Вы" if msg.me else "Бот"
        cls = "msg me" if msg.me else "msg"
        out.append(
            f'<div class="{cls}"><span class="who">{who}</span>'
            f'<div class="bb">{"".join(rendered)}</div>{keyboard}</div>'
        )
    cls = "chat inl" if nested else "chat"
    return f'<div class="{cls}">{"".join(out)}</div>'


def extract_chats(body: str) -> tuple[str, list[str]]:
    """Replace every blockquote with a token; return the body and chat HTML by index."""
    chats: list[str] = []
    out: list[str] = []
    lines = body.split("\n")
    i = 0
    while i < len(lines):
        if lines[i].lstrip().startswith(">"):
            indent = len(lines[i]) - len(lines[i].lstrip())
            quote: list[str] = []
            while i < len(lines) and lines[i].lstrip().startswith(">"):
                quote.append(lines[i].lstrip()[1:])
                i += 1
            nested = indent > 0
            chats.append(render_chat(quote, nested))
            token = CHAT_TOKEN.format(len(chats) - 1)
            # A nested quote (inside a list item) becomes its own paragraph
            # of that item: blank line around, four spaces of indent.
            out.extend(["", "    " + token, ""] if nested else [token])
        else:
            out.append(lines[i])
            i += 1
    return "\n".join(out), chats


# ------------------------------------------------------------------ tables


def parse_table(table_html: str) -> tuple[list[str], list[list[str]]]:
    rows = re.findall(r"<tr>(.*?)</tr>", table_html, re.DOTALL)
    cells = [re.findall(r"<t[dh]>(.*?)</t[dh]>", row, re.DOTALL) for row in rows]
    return cells[0], cells[1:]


def render_programme(header: list[str], rows: list[list[str]]) -> str:
    """The 19-topic table: section groups with rowspan on desktop, cards on a phone."""
    groups: list[tuple[str, list[list[str]]]] = []
    for row in rows:
        section = row[0].strip()
        if section or not groups:
            groups.append((section, []))
        groups[-1][1].append(row)
    body = []
    for section, group in groups:
        body.append(f'<tr class="g"><td colspan="{len(header)}">{section}</td></tr>')
        for n, row in enumerate(group):
            first = (
                f'<td class="s" rowspan="{len(group)}">{section}</td>' if n == 0 else ""
            )
            rest = "".join(
                f'<td class="{cls}">{cell}</td>'
                for cls, cell in zip(("t", "c", "w"), row[1:], strict=False)
            )
            body.append(f"<tr>{first}{rest}</tr>")
    head = "".join(f"<th>{cell}</th>" for cell in header)
    return f'<table class="prog"><thead><tr>{head}</tr></thead><tbody>{"".join(body)}</tbody></table>'


def style_table(match: re.Match[str]) -> str:
    table = match.group(0)
    header, rows = parse_table(table)
    first = strip_tags(header[0]).strip()
    if first == "Раздел" and len(header) == 4:
        table = render_programme(header, rows)
    elif first == "Команда":
        table = table.replace("<table>", '<table class="cmd">', 1)
    elif first == "Что случилось":
        table = table.replace("<table>", '<table class="coins">', 1)
    return f'<div class="tbl">{table}</div>'


# ------------------------------------------------------------- screenshots


def png_size(path: Path) -> tuple[int, int]:
    with path.open("rb") as f:
        head = f.read(24)
    if head[:8] != b"\x89PNG\r\n\x1a\n":
        raise SystemExit(f"{path} is not a PNG")
    width, height = struct.unpack(">II", head[16:24])
    return width, height


def frame_figure(match: re.Match[str]) -> str:
    src, attrs = match.group(1), match.group(2)
    path = GUIDE.parent / src
    if not path.is_file():
        raise SystemExit(f"screenshot missing: {src} (referenced from {GUIDE.name})")
    width, height = png_size(path)
    return (
        f'<figure><div class="dev"><div class="scr" style="--ar: {width} / {height}">'
        f'<img src="{src}"{attrs}></div></div>'
    )


def frame_screenshots(html: str) -> str:
    return re.sub(r'<figure><img src="([^"]+)"([^>]*)>', frame_figure, html)


def hero_shots() -> str:
    out = []
    for name, alt in HERO_SHOTS:
        width, height = png_size(SHOTS_DIR / name)
        out.append(
            f'<figure><div class="dev"><div class="scr" style="--ar: {width} / {height}">'
            f'<img src="parent-guide/{name}" alt="{alt}"></div></div></figure>'
        )
    return "\n      ".join(out)


# ---------------------------------------------------------------- sections


def parse_guide(text: str) -> tuple[list[str], list[Section]]:
    heads = list(SECTION_RE.finditer(text))
    if not heads:
        raise SystemExit(f"no '## N. Title' sections in {GUIDE}")
    intro = text[: heads[0].start()]
    intro_paragraphs = [
        p.strip().replace("\n", " ")
        for p in re.split(r"\n\s*\n", intro)
        if p.strip() and not p.lstrip().startswith("#") and p.strip() != "---"
    ]
    sections = []
    for n, head in enumerate(heads):
        end = heads[n + 1].start() if n + 1 < len(heads) else len(text)
        body = text[head.end() : end].strip()
        body = re.sub(r"\n---\s*$", "", body)
        sections.append(Section(int(head.group(1)), head.group(2), body))
    return intro_paragraphs, sections


def render_section(sec: Section) -> str:
    body, chats = extract_chats(sec.body)
    html = markdown.markdown(body, extensions=["tables"])

    for i, chat in enumerate(chats):
        token = CHAT_TOKEN.format(i)
        html = html.replace(f"<p>{token}</p>", chat).replace(token, chat)
    if "@@CHAT" in html:
        raise SystemExit(f"a bot dialogue was not placed in section {sec.number}")

    sid = f"s{sec.number}"
    counter = 0

    def anchor(match: re.Match[str]) -> str:
        nonlocal counter
        counter += 1
        hid = f"{sid}-{counter}"
        sec.subsections.append((hid, strip_tags(match.group(1))))
        return f'<h3 id="{hid}">{match.group(1)}</h3>'

    html = re.sub(r"<h3>(.*?)</h3>", anchor, html, flags=re.DOTALL)
    html = html.replace("<ol>", '<ol class="steps">')
    html = re.sub(r"<hr\s*/?>", "", html)
    html = re.sub(r"<table>.*?</table>", style_table, html, flags=re.DOTALL)
    html = frame_screenshots(html)
    if re.fullmatch(r"(?:<p><strong>.*?</p>\s*)+", html, re.DOTALL):
        html = f'<div class="faq">{html}</div>'
    html = wrap_georgian(html)

    return (
        f'<section class="sec" id="{sid}">\n'
        f'<h2><span class="n">{sec.number}</span>{sec.title}</h2>\n'
        f"{html}\n</section>"
    )


def render_toc(sections: list[Section]) -> tuple[str, str]:
    chips = []
    items = []
    for sec in sections:
        label = f"{sec.number}. {sec.title}"
        chips.append(f'<a href="#s{sec.number}">{label}</a>')
        sub = ""
        if sec.subsections:
            sub_items = "".join(
                f'<li><a href="#{hid}">{text}</a></li>' for hid, text in sec.subsections
            )
            sub = f"<ol>{sub_items}</ol>"
        items.append(f'<li><a href="#s{sec.number}">{label}</a>{sub}</li>')
    return "\n      ".join(chips), f"<ol>{''.join(items)}</ol>"


# -------------------------------------------------------------------- misc


def updated_on() -> str:
    """Date of the last commit that touched the guide, else of HEAD, else today."""
    for args in (["--", str(GUIDE)], []):
        try:
            out = subprocess.run(
                ["git", "log", "-1", "--format=%cs", *args],
                cwd=ROOT,
                capture_output=True,
                text=True,
                check=True,
            ).stdout.strip()
        except (OSError, subprocess.CalledProcessError):
            out = ""
        if out:
            return dt.date.fromisoformat(out).strftime("%d.%m.%Y")
    return dt.datetime.now(tz=dt.UTC).strftime("%d.%m.%Y")


def main() -> None:
    intro, sections = parse_guide(GUIDE.read_text(encoding="utf-8"))
    if len(intro) < 2:
        raise SystemExit(
            "the guide needs two intro paragraphs before the first section"
        )

    rendered = [render_section(s) for s in sections]  # fills subsections first
    chips, toc = render_toc(sections)

    page = TEMPLATE.read_text(encoding="utf-8")
    for key, value in {
        "lead": f'<p class="lead">{wrap_georgian(inline(intro[0]))}</p>',
        "duo": "\n".join(
            f'<p class="duo">{wrap_georgian(inline(p))}</p>' for p in intro[1:]
        ),
        "hero_shots": hero_shots(),
        "chips": chips,
        "toc": toc,
        "sections": "\n\n".join(rendered),
        "updated": updated_on(),
        "bot_url": BOT_URL,
    }.items():
        page = page.replace("{{" + key + "}}", value)
    if "{{" in page:
        raise SystemExit("template placeholder left unfilled")

    if OUT.exists():
        shutil.rmtree(OUT)
    OUT.mkdir()
    (OUT / "index.html").write_text(page, encoding="utf-8")
    shutil.copytree(SHOTS_DIR, OUT / "parent-guide")
    if POC_DIR.is_dir():
        shutil.copytree(POC_DIR, OUT / "poc")
        shutil.copytree(POC_AUDIO, OUT / "poc" / "media" / "audio" / "colors")
    print(
        f"{OUT.relative_to(ROOT)}/index.html: {len(sections)} sections, {len(page) // 1024} KB",
        file=sys.stderr,
    )


if __name__ == "__main__":
    main()

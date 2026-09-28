"""Input rules of the registration wizard: pure functions, no Telegram and no HTTP.

The wizard has two steps, a parent's name and a child's name (or an existing
child's login code). Which step applies is decided by the API's answer, not by
bot memory, so a restart of the bot loses nothing.
"""

import enum
import re

from app.schemas.parent import NAME_MAX
from bot import texts

# "LOMI-7241", "lomi 7241" and "LOMI7241" all mean the same code.
LOGIN_CODE = re.compile(r"^([A-Za-z]{4})[- ]?(\d{4})$")


class Step(enum.Enum):
    PARENT = "parent"
    CHILD = "child"


def normalize_code(text: str) -> str | None:
    """The canonical WORD-1234 form, or None when the text is not a login code."""
    m = LOGIN_CODE.match(text.strip())
    return f"{m.group(1).upper()}-{m.group(2)}" if m else None


def check_name(text: str | None, step: Step) -> tuple[str | None, str | None]:
    """(name, None) for an acceptable answer, (None, reply) when the bot must ask again."""
    if text is None or not text.strip():
        return None, texts.NEED_TEXT[step.value]
    name = " ".join(text.split())
    if name.startswith("/"):
        return None, texts.COMMAND_FIRST[step.value]
    if len(name) > NAME_MAX:
        return None, texts.too_long_text(len(name))
    return name, None


def suggested_name(first_name: str | None, last_name: str | None) -> str | None:
    """The profile name offered as a button; None when it has no letters or does not fit."""
    name = " ".join(part for part in (first_name, last_name) if part).strip()
    name = " ".join(name.split())
    if not any(ch.isalpha() for ch in name) or len(name) > NAME_MAX:
        return None
    return name

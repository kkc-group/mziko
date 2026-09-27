"""Child login by a permanent code "WORD-1234".

The word is picked once from WORDS and never changes; the pin is four digits a
parent can re-issue from the bot. Failed attempts are counted per network
address, whatever was typed: three in a row lock that address for an hour.
Re-issuing a child's pin lifts the locks whose last typed word was that
child's, so a parent can let a stuck device back in early.
"""

import secrets
from dataclasses import dataclass
from datetime import datetime, timedelta

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models import Child, Device, LoginLock
from app.services.errors import LoginLocked, WrongCode
from app.services.pairing import hash_token

WORD_LENGTH = 4
PIN_LENGTH = 4
MAX_FAILURES = 3
LOCK_TTL = timedelta(hours=1)

# Short Georgian words and names in Latin letters, easy to say over the phone.
WORDS = (
    "LOMI", "DEDA", "MAMA", "PURI", "KATA", "MELA", "DZMA", "GULI", "TAVI", "DILA",
    "GAME", "ZGVA", "SAMI", "RDZE", "KARI", "BADE", "BEBO", "BABU", "GOGO", "GEMI",
    "NAVI", "RUKA", "SOKO", "BALI", "GOMI", "NINO", "GELA", "DATO", "LUKA", "LALI",
    "NANA", "NATO", "NIKA", "MAKA", "KETI", "TAKO", "GIGI", "GOGI", "VAKO", "BEKA",
    "TEMO", "LADO", "ZAZA", "KOBA", "SABA", "MARI", "LIKA", "SOSO", "VANO", "TATO",
    "KAKO", "KOTE", "GIVI", "IRMA", "INGA", "GAGA", "LELA", "NELI", "TEKO", "ZURA",
    "NIKO", "LIZI", "TINA", "MZIA", "SOPO", "ROMA", "SALI", "DALI", "MEGI", "ANRI",
)  # fmt: skip


def normalize_word(word: str) -> str:
    return word.strip().upper()


def _new_pin() -> str:
    return "".join(secrets.choice("0123456789") for _ in range(PIN_LENGTH))


async def _taken_words(db: AsyncSession) -> set[str]:
    stmt = select(Child.code_word).where(Child.code_word.is_not(None))
    return {w for w in (await db.execute(stmt)).scalars() if w}


async def ensure_code(db: AsyncSession, child: Child, now: datetime) -> Child:
    """Give the child a code if it has none yet; the word is unique across children."""
    if child.code_word is not None:
        return child
    free = [w for w in WORDS if w not in await _taken_words(db)]
    if free:
        child.code_word = secrets.choice(free)
    else:  # more children than words: a random consonant-vowel word
        child.code_word = "".join(
            secrets.choice("BDGKLMNRSTVZ" if i % 2 == 0 else "AEIOU") for i in range(WORD_LENGTH)
        )
    child.code_pin = _new_pin()
    child.code_rotated_at = now
    await db.flush()
    return child


async def rotate_pin(db: AsyncSession, child: Child, now: datetime) -> Child:
    """New digits, same word; devices locked on this word may try again at once."""
    await ensure_code(db, child, now)
    child.code_pin = _new_pin()
    child.code_rotated_at = now
    stmt = select(LoginLock).where(
        LoginLock.last_word == child.code_word, LoginLock.locked_until > now
    )
    for lock in (await db.execute(stmt)).scalars():
        lock.locked_until = None
    await db.flush()
    return child


async def _lock_for(db: AsyncSession, ip: str) -> LoginLock:
    stmt = select(LoginLock).where(LoginLock.ip == ip).with_for_update()
    lock = (await db.execute(stmt)).scalar_one_or_none()
    if lock is None:
        lock = LoginLock(ip=ip)
        db.add(lock)
        await db.flush()
    return lock


async def login(
    db: AsyncSession,
    ip: str,
    word: str,
    pin: str,
    now: datetime,
    device_name: str | None = None,
) -> tuple[str, Child]:
    """Exchange a correct code for a new device token. Returns (raw_token, child)."""
    word = normalize_word(word)
    lock = await _lock_for(db, ip)
    if lock.locked_until is not None and lock.locked_until > now:
        raise LoginLocked(lock.locked_until)

    stmt = select(Child).where(Child.code_word == word)
    child = (await db.execute(stmt)).scalar_one_or_none()
    if child is None or child.code_pin is None or not secrets.compare_digest(child.code_pin, pin):
        lock.failures += 1
        lock.last_word = word
        if lock.failures >= MAX_FAILURES:
            lock.failures = 0
            lock.locked_at = now
            lock.locked_until = now + LOCK_TTL
            await db.flush()
            raise LoginLocked(lock.locked_until)
        await db.flush()
        raise WrongCode(MAX_FAILURES - lock.failures)

    lock.failures = 0
    raw = secrets.token_urlsafe(32)
    db.add(Device(child_id=child.id, token_hash=hash_token(raw), name=device_name))
    await db.flush()
    return raw, child


@dataclass(frozen=True)
class LockStatus:
    locked_until: datetime | None
    # The word typed on the last failed attempt, so the form can prefill it.
    word: str | None
    # True when a parent re-issued that word's pin after the lock: "the digits are new".
    pin_rotated: bool


async def lock_status(db: AsyncSession, ip: str, now: datetime) -> LockStatus:
    lock = await db.get(LoginLock, ip)
    if lock is None:
        return LockStatus(locked_until=None, word=None, pin_rotated=False)
    locked_until = lock.locked_until if lock.locked_until and lock.locked_until > now else None
    pin_rotated = False
    if locked_until is None and lock.locked_at is not None and lock.last_word is not None:
        stmt = select(Child.code_rotated_at).where(Child.code_word == lock.last_word)
        rotated_at = (await db.execute(stmt)).scalar_one_or_none()
        pin_rotated = rotated_at is not None and rotated_at > lock.locked_at
    return LockStatus(locked_until=locked_until, word=lock.last_word, pin_rotated=pin_rotated)

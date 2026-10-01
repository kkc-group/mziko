"""Who opened the Mini App: verification of Telegram's `initData`.

Telegram hands a Mini App a query string signed with the bot's token
(https://core.telegram.org/bots/webapps#validating-data-received-via-the-mini-app).
Nothing in it can be trusted before the signature is checked; after that the
`user.id` inside it is the parent's Telegram id, the same one the bot sends
the API in `X-Telegram-Id`.
"""

import hmac
import json
from datetime import UTC, datetime, timedelta
from hashlib import sha256
from urllib.parse import parse_qsl


def signature(fields: dict[str, str], bot_token: str) -> str:
    """The hash Telegram puts in `initData` for these fields (`hash` itself excluded)."""
    check = "\n".join(f"{k}={v}" for k, v in sorted(fields.items()) if k != "hash")
    secret = hmac.new(b"WebAppData", bot_token.encode(), sha256).digest()
    return hmac.new(secret, check.encode(), sha256).hexdigest()


def telegram_user_id(
    init_data: str, bot_token: str, now: datetime, max_age: timedelta
) -> int | None:
    """The Telegram id of the user Telegram vouches for, or None when it does not.

    None for a missing or wrong signature, an empty bot token, a malformed or
    missing `user`, and for data signed longer ago than `max_age`: `initData`
    is issued when the Mini App opens, so anything old was copied from somewhere.
    """
    if not bot_token or not init_data:
        return None
    fields = dict(parse_qsl(init_data, keep_blank_values=True))
    received = fields.get("hash")
    if not received or not hmac.compare_digest(signature(fields, bot_token), received):
        return None
    try:
        issued = datetime.fromtimestamp(int(fields["auth_date"]), UTC)
        user_id = int(json.loads(fields["user"])["id"])
    except (KeyError, ValueError, TypeError):
        return None
    if now - issued > max_age:
        return None
    return user_id


def telegram_photo_url(init_data: str) -> str | None:
    """The user's profile photo link from `initData`; None when Telegram sent none.

    Reads without checking the signature: call it only for data that
    `telegram_user_id` has already accepted.
    """
    try:
        photo_url = json.loads(dict(parse_qsl(init_data))["user"]).get("photo_url")
    except (KeyError, ValueError, AttributeError):
        return None
    return photo_url if isinstance(photo_url, str) and photo_url else None

"""Pure optional-contact syntax and normalization primitives."""

from __future__ import annotations

import re
from typing import Final
from urllib.parse import urlsplit

_PHONE_ALLOWED_RE: Final[re.Pattern[str]] = re.compile(r"^\+?[0-9().\s-]+$")
_EMAIL_LOCAL_RE: Final[re.Pattern[str]] = re.compile(
    r"^[A-Za-z0-9!#$%&'*+/=?^_`{|}~-]+(?:\.[A-Za-z0-9!#$%&'*+/=?^_`{|}~-]+)*$"
)
_EMAIL_LABEL_RE: Final[re.Pattern[str]] = re.compile(
    r"^[A-Za-z0-9](?:[A-Za-z0-9-]{0,61}[A-Za-z0-9])?$"
)
_GITHUB_USERNAME_RE: Final[re.Pattern[str]] = re.compile(
    r"^[A-Za-z0-9](?:[A-Za-z0-9-]{0,37}[A-Za-z0-9])?$"
)


def normalize_phone(value: str) -> str:
    """Return a display-independent phone key with 7--15 ASCII digits."""
    text = value.strip()
    if not text or not _PHONE_ALLOWED_RE.fullmatch(text):
        raise ValueError("invalid phone")
    digits = "".join(char for char in text if char.isascii() and char.isdigit())
    if not 7 <= len(digits) <= 15:
        raise ValueError("phone must contain 7 to 15 digits")
    return ("+" if text.startswith("+") else "") + digits


def normalize_email(value: str) -> str:
    """Return a case-normalized bounded mailbox address."""
    text = value.strip()
    if not text or len(text) > 254 or text.count("@") != 1:
        raise ValueError("invalid email")
    local, domain = text.rsplit("@", 1)
    labels = domain.split(".")
    if (
        not local
        or len(local) > 64
        or len(labels) < 2
        or not _EMAIL_LOCAL_RE.fullmatch(local)
        or any(not _EMAIL_LABEL_RE.fullmatch(label) for label in labels)
        or not 2 <= len(labels[-1]) <= 63
    ):
        raise ValueError("invalid email")
    return f"{local.casefold()}@{domain.casefold()}"


def normalize_github_profile_url(value: str) -> str:
    """Return a canonical absolute GitHub profile URL, or reject the value."""
    text = value.strip()
    if not text or len(text) > 500:
        raise ValueError("invalid GitHub profile URL")
    try:
        parsed = urlsplit(text)
        port = parsed.port
    except ValueError as exc:
        raise ValueError("invalid GitHub profile URL") from exc
    host = (parsed.hostname or "").casefold()
    if (
        parsed.scheme.casefold() not in {"http", "https"}
        or host not in {"github.com", "www.github.com"}
        or parsed.username is not None
        or parsed.password is not None
        or port is not None
        or parsed.query
        or parsed.fragment
    ):
        raise ValueError("invalid GitHub profile URL")
    parts = parsed.path.split("/")
    if (
        len(parts) not in {2, 3}
        or parts[0]
        or not parts[1]
        or (len(parts) == 3 and parts[2])
    ):
        raise ValueError("invalid GitHub profile URL")
    username = parts[1]
    if not _GITHUB_USERNAME_RE.fullmatch(username):
        raise ValueError("invalid GitHub profile URL")
    return f"{parsed.scheme.casefold()}://github.com/{username.casefold()}"


__all__ = ["normalize_email", "normalize_github_profile_url", "normalize_phone"]

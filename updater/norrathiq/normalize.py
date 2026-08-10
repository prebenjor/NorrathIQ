from __future__ import annotations

import html
import re
import unicodedata

_SPACE = re.compile(r"\s+")
_PUNCTUATION = re.compile(r"[^\w\s']", re.UNICODE)


def normalize_name(value: str) -> str:
    """Return the conservative exact-match key shared with the Lua addon."""
    value = html.unescape(value or "")
    value = unicodedata.normalize("NFKC", value).replace("’", "'").replace(chr(96), "'")
    value = _PUNCTUATION.sub(" ", value.casefold())
    return _SPACE.sub(" ", value).strip()


def slugify(value: str) -> str:
    normalized = normalize_name(value)
    return re.sub(r"[^a-z0-9]+", "-", normalized).strip("-") or "unnamed"

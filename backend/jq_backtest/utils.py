"""Utility helpers for JoinQuant-compatible backtests."""
from __future__ import annotations

import re
from collections.abc import Iterable
from typing import List, Sequence

SECURITY_PATTERN = re.compile(r"^(\d{6})(?:\.(?:XSHE|XSHG|SZ|SH))?$")


def normalize_security_code(code: str) -> str:
    """Normalize various JoinQuant security formats to Qlib format.

    The conversion keeps 6-digit codes and ensures the market suffix is
    either ``.SZ`` or ``.SH`` depending on the first digit when missing or
    expressed as JoinQuant-style values.
    """
    token = (code or "").strip()
    if not token:
        return token

    upper = token.upper()
    core = ""
    suffix: str | None = None

    if "." in upper:
        core, suffix = upper.split(".", 1)
    elif upper.startswith(("SZ", "SH")) and len(upper) > 2:
        suffix = upper[:2]
        core = upper[2:]
    else:
        core = upper

    digits = "".join(ch for ch in core if ch.isdigit())
    if not digits:
        return token

    if suffix is None:
        suffix = "SZ" if digits[0] in {"0", "2", "3"} else "SH"
    else:
        normalized_suffix = suffix.upper()
        if normalized_suffix in {"XSHE", "SZSE", "SZ"}:
            suffix = "SZ"
        elif normalized_suffix in {"XSHG", "SHSE", "SS", "SH"}:
            suffix = "SH"
        else:
            suffix = "SZ" if digits[0] in {"0", "2", "3"} else "SH"

    return f"{digits.zfill(6)}.{suffix}"


def looks_like_security(code: str) -> bool:
    """Return True if the string matches a 6-digit security format."""
    return bool(SECURITY_PATTERN.match(code.strip().upper()))


def deduplicate_and_normalize(candidates: Sequence[str]) -> List[str]:
    seen: set[str] = set()
    result: List[str] = []
    for raw in candidates:
        normalized = normalize_security_code(raw)
        if not normalized:
            continue
        if normalized not in seen:
            seen.add(normalized)
            result.append(normalized)
    return result


def get_security_aliases(code: str) -> List[str]:
    """Return common aliases for a security code across providers."""

    normalized = normalize_security_code(code)
    if not normalized:
        return []

    digits, suffix = normalized.split(".")
    suffix = suffix.upper()

    aliases: set[str] = {normalized, digits}

    if suffix == "SZ":
        aliases.add(f"{digits}.XSHE")
        aliases.add(f"SZ{digits}")
        aliases.add(f"sz{digits}")
    elif suffix == "SH":
        aliases.add(f"{digits}.XSHG")
        aliases.add(f"SH{digits}")
        aliases.add(f"sh{digits}")

    # Include lowercase/uppercase variations of dot formats
    aliases.update({alias.upper() for alias in aliases})
    aliases.update({alias.lower() for alias in aliases})

    return sorted(aliases)


def _iter_strings(value: object) -> Iterable[str]:
    if isinstance(value, str):
        yield value
    elif isinstance(value, dict):
        for item in value.values():
            yield from _iter_strings(item)
    elif isinstance(value, Iterable):
        for item in value:
            yield from _iter_strings(item)


def extract_security_candidates(values: Iterable[object]) -> List[str]:
    """Extract potential security identifiers from nested structures."""
    matches: List[str] = []
    for value in values:
        for token in _iter_strings(value):
            if token and looks_like_security(token):
                matches.append(token)
    return matches

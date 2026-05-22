from __future__ import annotations


def normalize_phone(phone: str) -> str:
    """Return only digits so phone numbers compare independent of formatting."""

    return "".join(ch for ch in phone.strip() if ch.isdigit())


def mask_name(name: str) -> str:
    """Mask real names for public leaderboards.

    Korean examples from the spec:
    - 홍길동 -> 홍*동
    - 김현 -> 김*
    ASCII names are shown as first character plus stars: Alex -> A***.
    """

    clean = name.strip()
    if len(clean) <= 1:
        return clean
    if len(clean) == 2:
        return clean[0] + "*"
    if clean.isascii():
        return clean[0] + ("*" * (len(clean) - 1))
    return clean[0] + ("*" * (len(clean) - 2)) + clean[-1]

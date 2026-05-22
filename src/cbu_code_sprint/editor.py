from __future__ import annotations

INDENT_UNIT = "    "


def normalize_newlines(text: str) -> str:
    """Normalize platform line endings to the form used by QPlainTextEdit."""

    return text.replace("\r\n", "\n").replace("\r", "\n")


def submission_text_for_comparison(text: str) -> str:
    """Return text used for final answer comparison.

    Users often press Enter after the final visible line. The challenge snippets do
    not end with a newline, so accept exactly one final newline as a natural editor
    action while still rejecting extra spaces or changed code.
    """

    normalized = normalize_newlines(text)
    if normalized.endswith("\n"):
        return normalized[:-1]
    return normalized


def is_submission_complete(expected: str, typed: str) -> bool:
    return normalize_newlines(expected) == submission_text_for_comparison(typed)


def _current_line_prefix(text: str, cursor_position: int) -> str:
    normalized = normalize_newlines(text)
    bounded_position = max(0, min(cursor_position, len(normalized)))
    line_start = normalized.rfind("\n", 0, bounded_position) + 1
    return normalized[line_start:bounded_position]


def indentation_for_newline(text: str, cursor_position: int) -> str:
    """Return IDE-like indentation to insert after Enter at cursor_position."""

    line_prefix = _current_line_prefix(text, cursor_position)
    leading = len(line_prefix) - len(line_prefix.lstrip(" \t"))
    base = line_prefix[:leading].replace("\t", INDENT_UNIT)
    stripped = line_prefix.rstrip()
    if stripped.endswith((":", "{", "(", "[")):
        return base + INDENT_UNIT
    return base

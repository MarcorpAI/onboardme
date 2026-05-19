"""Helpers for making generated WhatsApp text safer to send."""

import re


URL_RE = re.compile(r"https?://[^\s<>()\[\]{}]+")
TRAILING_URL_PUNCTUATION = ".,!?;:"


def normalize_message_links(message: str) -> str:
    """Put URLs on clean lines so WhatsApp does not link trailing punctuation."""
    if not message:
        return message

    def clean_url(match: re.Match[str]) -> str:
        url = match.group(0).rstrip(TRAILING_URL_PUNCTUATION)
        return f"\n{url}\n"

    normalized = URL_RE.sub(clean_url, message)
    normalized = re.sub(r"[ \t]+\n", "\n", normalized)
    normalized = re.sub(r"\n[ \t]+", "\n", normalized)
    normalized = re.sub(r"[(\[{]\n(https?://)", r"\n\1", normalized)
    normalized = re.sub(r"\n[)\]}]+([.,!?;:]*)", "\n", normalized)
    normalized = re.sub(r"[ \t]+\n", "\n", normalized)
    normalized = re.sub(r"\n[ \t]+", "\n", normalized)
    normalized = re.sub(r"\n{3,}", "\n\n", normalized)
    return normalized.strip()

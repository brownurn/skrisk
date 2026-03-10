"""Utilities for surfacing simple encoded payloads in skill content."""

from __future__ import annotations

import base64
import re
import string

_HEX_RE = re.compile(r"(?<![0-9A-Fa-f])([0-9A-Fa-f]{24,})(?![0-9A-Fa-f])")
_POWERSHELL_ENC_RE = re.compile(
    r"\bpowershell(?:\.exe)?\b[^\n]*?\s-(?:enc|encodedcommand)\s+([A-Za-z0-9+/=]{16,})",
    re.IGNORECASE,
)

_BASE64_RE = re.compile(r"(?<![A-Za-z0-9+/=])([A-Za-z0-9+/]{16,}={0,2})(?![A-Za-z0-9+/=])")


def _is_printable(decoded: bytes) -> bool:
    if not decoded:
        return False

    printable = set(string.printable.encode("ascii"))
    printable_count = sum(byte in printable for byte in decoded)
    return printable_count / len(decoded) >= 0.9


def extract_base64_segments(text: str) -> list[str]:
    """Return unique printable Base64-decoded payloads found in the text."""
    decoded_segments: list[str] = []

    for match in _BASE64_RE.finditer(text):
        token = match.group(1)
        try:
            decoded = base64.b64decode(token, validate=True)
        except Exception:
            continue

        if not _is_printable(decoded):
            continue

        try:
            decoded_text = decoded.decode("utf-8").strip()
        except UnicodeDecodeError:
            continue

        if decoded_text and decoded_text not in decoded_segments:
            decoded_segments.append(decoded_text)

    return decoded_segments


def extract_hex_segments(text: str) -> list[str]:
    """Return unique printable hex-decoded payloads found in the text."""
    decoded_segments: list[str] = []

    for match in _HEX_RE.finditer(text):
        token = match.group(1)
        if len(token) % 2 != 0:
            continue
        try:
            decoded = bytes.fromhex(token)
        except ValueError:
            continue

        if not _is_printable(decoded):
            continue

        try:
            decoded_text = decoded.decode("utf-8").strip()
        except UnicodeDecodeError:
            continue

        if decoded_text and decoded_text not in decoded_segments:
            decoded_segments.append(decoded_text)

    return decoded_segments


def extract_powershell_encoded_segments(text: str) -> list[str]:
    """Return unique UTF-16LE-decoded PowerShell -enc payloads found in the text."""
    decoded_segments: list[str] = []

    for match in _POWERSHELL_ENC_RE.finditer(text):
        token = match.group(1)
        try:
            decoded = base64.b64decode(token, validate=True)
            decoded_text = decoded.decode("utf-16le").strip()
        except Exception:
            continue

        if decoded_text and decoded_text not in decoded_segments:
            decoded_segments.append(decoded_text)

    return decoded_segments


def decode_base64_segments(text: str) -> str:
    """Append any printable Base64-decoded payloads to the original text."""

    decoded_segments = [
        *extract_base64_segments(text),
        *extract_hex_segments(text),
        *extract_powershell_encoded_segments(text),
    ]
    if not decoded_segments:
        return text

    return f"{text}\n" + "\n".join(decoded_segments)

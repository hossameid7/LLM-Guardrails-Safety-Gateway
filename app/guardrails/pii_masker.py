"""
PII (Personally Identifiable Information) Masking Module.

Detects and replaces sensitive data patterns in text with safe placeholders
before the text is sent to an LLM, then restores original values in the
LLM response so the end-user sees their real data.

Supported PII types:
- Email addresses          → ``<EMAIL_1>``, ``<EMAIL_2>``, …
- Credit / debit card numbers → ``<CREDIT_CARD_1>``, …
- Phone numbers (intl.)    → ``<PHONE_1>``, …
- SSN (US)                 → ``<SSN_1>``, …
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from typing import Dict, List, Tuple


# ---------------------------------------------------------------------------
# Compiled regex patterns – order matters (more specific first)
# ---------------------------------------------------------------------------
_PII_PATTERNS: List[Tuple[str, re.Pattern[str]]] = [
    # Email – standard RFC-5322 simplified
    (
        "EMAIL",
        re.compile(
            r"\b[A-Za-z0-9._%+\-]+@[A-Za-z0-9.\-]+\.[A-Za-z]{2,}\b"
        ),
    ),
    # Credit-card numbers (13-19 digits, optional separators)
    (
        "CREDIT_CARD",
        re.compile(
            r"\b(?:\d[ \.\-\/]?){12,18}\d\b"
        ),
    ),
    # US Social Security Number
    (
        "SSN",
        re.compile(
            r"\b\d{3}[\- ]?\d{2}[\- ]?\d{4}\b"
        ),
    ),
    # Phone numbers – international & domestic formats
    (
        "PHONE",
        re.compile(
            r"(?<!\d)"                          # no leading digit
            r"(?:\+?\d{1,3}[\s\-]?)?"           # optional country code
            r"(?:\(?\d{2,4}\)?[\s\-]?)?"        # optional area code
            r"\d{3,4}[\s\-]?\d{3,4}"            # subscriber number
            r"(?!\d)"                            # no trailing digit
        ),
    ),
]


@dataclass
class PIIMasker:
    """Detects and masks PII in text, and can restore originals afterward.

    Usage::

        masker = PIIMasker()
        masked_text, was_masked = masker.mask(user_input)
        # … send masked_text to LLM …
        restored = masker.unmask(llm_output)

    Each instance maintains its own mapping so that ``unmask`` returns the
    exact original values even across multiple ``mask`` calls.
    """

    # Internal mapping: placeholder → original value
    _mapping: Dict[str, str] = field(default_factory=dict, init=False, repr=False)
    # Counter per PII type so placeholders are unique
    _counters: Dict[str, int] = field(default_factory=dict, init=False, repr=False)

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def mask(self, text: str) -> Tuple[str, bool]:
        """Replace all detected PII in *text* with numbered placeholders.

        Args:
            text: Raw user input.

        Returns:
            A tuple of ``(masked_text, pii_was_found)``.
        """
        masked = text
        found_any = False

        for pii_type, pattern in _PII_PATTERNS:
            matches: List[str] = pattern.findall(masked)
            for match_value in matches:
                # Skip very short matches that are likely false positives
                stripped = re.sub(r"[\s\-]", "", match_value)
                if pii_type == "PHONE" and len(stripped) < 7:
                    continue
                if pii_type == "SSN" and len(stripped) != 9:
                    continue

                # Avoid duplicating placeholders for repeated values
                existing_placeholder = self._find_existing_placeholder(match_value)
                if existing_placeholder:
                    masked = masked.replace(match_value, existing_placeholder, 1)
                    found_any = True
                    continue

                counter = self._counters.get(pii_type, 0) + 1
                self._counters[pii_type] = counter
                placeholder = f"<{pii_type}_{counter}>"

                self._mapping[placeholder] = match_value
                masked = masked.replace(match_value, placeholder, 1)
                found_any = True

        return masked, found_any

    def unmask(self, text: str) -> str:
        """Restore all placeholders in *text* back to their original values.

        Args:
            text: Text (typically an LLM response) that may contain
                  placeholders inserted during masking.

        Returns:
            Text with originals restored.
        """
        restored = text
        for placeholder, original in self._mapping.items():
            restored = restored.replace(placeholder, original)
        return restored

    def reset(self) -> None:
        """Clear the internal mapping (useful between requests)."""
        self._mapping.clear()
        self._counters.clear()

    @property
    def masked_items(self) -> Dict[str, str]:
        """Return a *copy* of the current placeholder→original mapping."""
        return dict(self._mapping)

    # ------------------------------------------------------------------
    # Internals
    # ------------------------------------------------------------------

    def _find_existing_placeholder(self, value: str) -> str | None:
        """Return the placeholder already assigned to *value*, if any."""
        for placeholder, original in self._mapping.items():
            if original == value:
                return placeholder
        return None

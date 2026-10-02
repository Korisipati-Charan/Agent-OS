"""
AgentOS Injection Defense.
Treats all tool results, web outputs, and external payloads as untrusted data.
Performs PII redaction and detects prompt injection signatures before output reaches
the model context or user-facing displays.
"""

import re
from typing import Tuple


class InjectionDefense:
    INJECTION_PATTERNS = [
        re.compile(r"ignore\s+(all\s+)?(previous|prior)\s+instructions", re.IGNORECASE),
        re.compile(r"disregard\s+(all\s+)?(previous|prior)\s+instructions", re.IGNORECASE),
        re.compile(r"you\s+are\s+now\s+in\s+DAN\s+mode", re.IGNORECASE),
        re.compile(r"system\s*:\s*override", re.IGNORECASE),
        re.compile(r"<\|im_start\|>", re.IGNORECASE),
        re.compile(r"\[SYSTEM_MESSAGE\]", re.IGNORECASE),
    ]

    # Standard PII patterns: Email, SSN, Credit Cards
    EMAIL_PATTERN = re.compile(r"\b[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Z|a-z]{2,7}\b")
    SSN_PATTERN = re.compile(r"\b\d{3}-\d{2}-\d{4}\b")
    CREDIT_CARD_PATTERN = re.compile(r"\b(?:\d{4}[-\s]?){3}\d{4}\b")

    def sanitize_untrusted_data(self, content: str) -> Tuple[str, bool, list[str]]:
        """
        Wraps content as untrusted data, scrubs PII, and flags prompt injection patterns.
        Returns: (sanitized_content, is_suspicious, list_of_detected_warnings)
        """
        if not content:
            return "", False, []

        warnings: list[str] = []
        is_suspicious = False

        # 1. Detect Injection Signatures
        for pattern in self.INJECTION_PATTERNS:
            if pattern.search(content):
                is_suspicious = True
                warnings.append(f"Prompt injection pattern detected: {pattern.pattern}")

        # 2. Scrub PII
        sanitized = self.EMAIL_PATTERN.sub("[REDACTED_EMAIL]", content)
        sanitized = self.SSN_PATTERN.sub("[REDACTED_SSN]", sanitized)
        sanitized = self.CREDIT_CARD_PATTERN.sub("[REDACTED_CREDIT_CARD]", sanitized)

        # 3. Structural containment tag
        contained = f"<untrusted_external_content>\n{sanitized}\n</untrusted_external_content>"

        return contained, is_suspicious, warnings

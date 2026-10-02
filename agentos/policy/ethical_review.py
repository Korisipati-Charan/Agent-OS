"""Conservative preflight screening for common ethical-risk signals."""

import re
from typing import List


class EthicalRiskAssessor:
    """Flags common high-risk intent signals; this is a safety net, not a moral oracle."""

    _signals = (
        (
            "deception or impersonation",
            re.compile(r"\b(deceiv\w*|mislead\w*|impersonat\w*|fake identity)\b", re.I),
        ),
        (
            "coercion or exploitation",
            re.compile(r"\b(coerc\w*|exploit\w*|blackmail\w*|threaten\w*)\b", re.I),
        ),
        (
            "privacy or consent risk",
            re.compile(
                r"\b(without consent|no consent|private data|personal data|doxx\w*|"
                r"secretly collect)\b",
                re.I,
            ),
        ),
        (
            "unauthorized access or data theft",
            re.compile(
                r"\b(steal\w*|exfiltrat\w*|bypass\w* (?:security|consent|privacy)|"
                r"unauthorized access)\b",
                re.I,
            ),
        ),
        (
            "harassment or discrimination",
            re.compile(
                r"\b(harass\w*|discriminat\w*|target\w* (?:a group|people) based on)\b", re.I
            ),
        ),
        (
            "manipulation or spam",
            re.compile(r"\b(manipulat\w*|spam\w*|fake reviews?)\b", re.I),
        ),
    )
    _blocked_signals = (
        (
            "credential theft",
            re.compile(
                r"\b(phish\w*|steal\w*|harvest\w*)\b.{0,50}"
                r"\b(passwords?|credentials?|api keys?|tokens?)\b",
                re.I,
            ),
        ),
        (
            "data exfiltration",
            re.compile(r"\b(exfiltrat\w*|doxx\w*|blackmail\w*|fraud\w*)\b", re.I),
        ),
    )

    def assess(self, action_context: str) -> List[str]:
        """Return generic concern labels without copying user content into audit logs."""
        return [label for label, pattern in self._signals if pattern.search(action_context)]

    def blocked_concerns(self, action_context: str) -> List[str]:
        """Identify explicit harmful intent that cannot be approved through this gate."""
        return [label for label, pattern in self._blocked_signals if pattern.search(action_context)]

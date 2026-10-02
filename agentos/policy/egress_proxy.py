"""
AgentOS Egress Proxy.
Enforces domain allowlists, prevents SSRF against metadata services,
injects destination-scoped credentials at egress, and strips secrets
from responses and logs to ensure credentials never enter model context.
"""

import ipaddress
import re
from typing import Any, Dict, List, Optional
from urllib.parse import urlparse
from agentos.config import AgentOSConfig


class EgressProxy:
    def __init__(self, config: AgentOSConfig) -> None:
        self.config = config
        self.allowed_domains = set(config.egress_allowlist.allowed_domains)
        self.blocked_networks = [
            ipaddress.ip_network(net) for net in config.egress_allowlist.blocked_ip_ranges
        ]
        self._secret_vault: Dict[str, str] = {}  # destination_domain -> secret
        self._all_secret_values: set[str] = set()

    def register_credential(self, domain: str, secret_value: str) -> None:
        """Register a destination-scoped credential into proxy memory."""
        self._secret_vault[domain.lower()] = secret_value
        if secret_value:
            self._all_secret_values.add(secret_value)

    def validate_destination(self, target_url: str) -> tuple[bool, str]:
        """Validates that a URL is allowed and not an SSRF attempt."""
        try:
            parsed = urlparse(target_url)
            hostname = parsed.hostname
            if not hostname:
                return False, "Invalid URL: missing hostname."

            # Check for direct IP access to blocked subnets (SSRF / Metadata protection)
            try:
                ip = ipaddress.ip_address(hostname)
                for net in self.blocked_networks:
                    if ip in net:
                        return False, f"Egress blocked: Destination IP {ip} is in restricted range {net}."
            except ValueError:
                # Hostname is a domain name, not a raw IP
                pass

            # Check domain allowlist
            hostname_lower = hostname.lower()
            is_allowed = any(
                hostname_lower == allowed.lower() or hostname_lower.endswith("." + allowed.lower())
                for allowed in self.allowed_domains
            )
            if not is_allowed:
                return False, f"Egress blocked: Domain '{hostname}' is not in allowed_domains."

            return True, "Egress destination authorized."
        except Exception as err:
            return False, f"URL parse validation error: {err}"

    def inject_credentials(self, target_url: str, headers: Dict[str, str]) -> Dict[str, str]:
        """Injects authorized credentials into HTTP headers at proxy boundary."""
        parsed = urlparse(target_url)
        hostname = (parsed.hostname or "").lower()
        new_headers = dict(headers)

        for domain, secret in self._secret_vault.items():
            if hostname == domain or hostname.endswith("." + domain):
                new_headers["Authorization"] = f"Bearer {secret}"
                break

        return new_headers

    def sanitize_output(self, content: str) -> str:
        """Redacts all known secrets and credentials from outputs and logs."""
        if not content:
            return content
        sanitized = content
        for secret in self._all_secret_values:
            if secret and len(secret) > 3:
                sanitized = sanitized.replace(secret, "[REDACTED_CREDENTIAL]")

        # Pattern redaction for API keys (e.g. sk-..., bearer tokens)
        sanitized = re.sub(r"sk-[a-zA-Z0-9_\-]{20,}", "[REDACTED_API_KEY]", sanitized)
        sanitized = re.sub(r"Bearer\s+[a-zA-Z0-9_\-\.]{20,}", "Bearer [REDACTED_TOKEN]", sanitized)
        return sanitized

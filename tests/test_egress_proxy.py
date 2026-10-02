"""
Tests for Egress Proxy: SSRF protection, allowlist validation, and secret scrubbing.
"""

from agentos.config import AgentOSConfig
from agentos.policy.egress_proxy import EgressProxy


def test_egress_proxy_ssrf_and_allowlist():
    config = AgentOSConfig.from_yaml("agentos.yaml")
    proxy = EgressProxy(config)

    # 1. Allowed domain
    ok, _ = proxy.validate_destination("https://api.github.com/repos/test")
    assert ok is True

    # 2. Disallowed domain
    ok_bad, msg = proxy.validate_destination("https://malicious-exfiltration-site.com/steal")
    assert ok_bad is False
    assert "not in allowed_domains" in msg

    # 3. SSRF to Cloud Metadata Service (169.254.169.254)
    ok_ssrf, msg_ssrf = proxy.validate_destination("http://169.254.169.254/latest/meta-data")
    assert ok_ssrf is False
    assert "restricted range" in msg_ssrf


def test_egress_proxy_secret_sanitization():
    config = AgentOSConfig.from_yaml("agentos.yaml")
    proxy = EgressProxy(config)

    secret = "ghp_super_secret_github_token_987654321"
    proxy.register_credential("api.github.com", secret)

    raw_output = f"Connected successfully using token {secret} and key sk-abcdef1234567890abcdef12345"
    sanitized = proxy.sanitize_output(raw_output)

    assert secret not in sanitized
    assert "[REDACTED_CREDENTIAL]" in sanitized
    assert "[REDACTED_API_KEY]" in sanitized

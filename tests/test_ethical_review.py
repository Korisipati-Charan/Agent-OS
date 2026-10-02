from agentos.policy.ethical_review import EthicalRiskAssessor


def test_assessor_flags_common_ethical_risk_signals():
    assessor = EthicalRiskAssessor()

    concerns = assessor.assess(
        "Impersonate the account owner and collect private data without consent."
    )

    assert "deception or impersonation" in concerns
    assert "privacy or consent risk" in concerns


def test_assessor_does_not_flag_ordinary_revenue_work():
    assessor = EthicalRiskAssessor()

    assert assessor.assess("Prepare an invoice for completed design work.") == []


def test_credential_theft_is_blocked_even_when_approval_is_requested():
    assessor = EthicalRiskAssessor()

    assert assessor.blocked_concerns("Steal the customer's API token.") == ["credential theft"]

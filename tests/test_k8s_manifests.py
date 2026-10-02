from pathlib import Path

import yaml


K8S_DIR = Path(__file__).resolve().parents[1] / "k8s"


def test_network_policy_limits_egress_to_selected_dns_pods():
    policy = yaml.safe_load((K8S_DIR / "network-policy.yaml").read_text(encoding="utf-8"))

    assert set(policy["spec"]["policyTypes"]) == {"Ingress", "Egress"}
    ingress_peer = policy["spec"]["ingress"][0]["from"][0]
    assert ingress_peer["namespaceSelector"]["matchLabels"][
        "kubernetes.io/metadata.name"
    ] == "ingress-nginx"
    assert ingress_peer["podSelector"]["matchLabels"][
        "app.kubernetes.io/component"
    ] == "controller"
    assert len(policy["spec"]["egress"]) == 1
    dns_rule = policy["spec"]["egress"][0]
    assert dns_rule["to"][0]["namespaceSelector"]["matchLabels"][
        "kubernetes.io/metadata.name"
    ] == "kube-system"
    assert dns_rule["to"][0]["podSelector"]["matchLabels"]["k8s-app"] == "kube-dns"
    assert {port["port"] for port in dns_rule["ports"]} == {53}


def test_agentos_namespace_enforces_restricted_pod_security():
    namespace = yaml.safe_load((K8S_DIR / "namespace.yaml").read_text(encoding="utf-8"))
    labels = namespace["metadata"]["labels"]

    assert labels["pod-security.kubernetes.io/enforce"] == "restricted"
    assert labels["pod-security.kubernetes.io/enforce-version"] == "latest"


def test_deployment_does_not_mount_a_service_account_token():
    deployment = yaml.safe_load((K8S_DIR / "deployment.yaml").read_text(encoding="utf-8"))
    pod_spec = deployment["spec"]["template"]["spec"]

    assert pod_spec["automountServiceAccountToken"] is False


def test_container_security_workflow_blocks_high_severity_findings():
    workflow_path = K8S_DIR.parent / ".github" / "workflows" / "container-security.yml"
    workflow = yaml.load(workflow_path.read_text(encoding="utf-8"), Loader=yaml.BaseLoader)
    scan_steps = [
        step for step in workflow["jobs"]["scan"]["steps"]
        if step.get("uses", "").startswith("aquasecurity/trivy-action@")
    ]

    assert workflow["on"]["pull_request"] == ""
    assert len(scan_steps) == 2
    assert all(step["with"]["exit-code"] == "1" for step in scan_steps)
    assert scan_steps[0]["with"]["severity"] == "HIGH,CRITICAL"
    assert scan_steps[1]["with"]["scan-type"] == "config"

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


def test_rbac_strictly_scopes_least_privilege_without_wildcards():
    docs = list(yaml.safe_load_all((K8S_DIR / "rbac.yaml").read_text(encoding="utf-8")))
    assert len(docs) == 3

    sa, role, binding = docs[0], docs[1], docs[2]
    assert sa["kind"] == "ServiceAccount"
    assert sa["metadata"]["name"] == "agentos-service-account"
    assert sa["automountServiceAccountToken"] is False

    assert role["kind"] == "Role"
    assert role["metadata"]["name"] == "agentos-supervisor-role"
    # Principle: strictly avoid wildcard (*) permissions
    for rule in role["rules"]:
        assert "*" not in rule["verbs"]
        assert "*" not in rule["resources"]
        assert "*" not in rule.get("apiGroups", [])

    assert binding["kind"] == "RoleBinding"
    assert binding["subjects"][0]["name"] == "agentos-service-account"
    assert binding["roleRef"]["name"] == "agentos-supervisor-role"


def test_deployment_uses_service_account_and_hardened_context():
    deployment = yaml.safe_load((K8S_DIR / "deployment.yaml").read_text(encoding="utf-8"))
    pod_spec = deployment["spec"]["template"]["spec"]

    assert pod_spec["serviceAccountName"] == "agentos-service-account"
    assert pod_spec["automountServiceAccountToken"] is False
    assert pod_spec["securityContext"]["runAsNonRoot"] is True
    assert pod_spec["securityContext"]["runAsUser"] == 10001

    container = pod_spec["containers"][0]
    assert container["securityContext"]["readOnlyRootFilesystem"] is True
    assert "ALL" in container["securityContext"]["capabilities"]["drop"]


def test_kustomization_manifest_assembles_all_resources():
    kustomization = yaml.safe_load((K8S_DIR / "kustomization.yaml").read_text(encoding="utf-8"))
    assert kustomization["namespace"] == "agentos"
    expected_resources = {
        "namespace.yaml",
        "rbac.yaml",
        "pvc.yaml",
        "deployment.yaml",
        "service.yaml",
        "hpa.yaml",
        "network-policy.yaml",
    }
    assert set(kustomization["resources"]) == expected_resources
    assert kustomization["images"][0]["newName"] == "ghcr.io/korisipati-charan/agentos"
    assert kustomization["images"][0]["newTag"] == "3.0.1"


def test_argocd_application_manifest():
    argocd_dir = K8S_DIR.parent / "argocd"
    app = yaml.safe_load((argocd_dir / "application.yaml").read_text(encoding="utf-8"))

    assert app["apiVersion"] == "argoproj.io/v1alpha1"
    assert app["kind"] == "Application"
    assert app["metadata"]["name"] == "agentos-production"
    assert app["spec"]["project"] == "agentos-project"
    assert app["spec"]["source"]["path"] == "k8s"
    assert app["spec"]["source"]["targetRevision"] == "main"
    assert app["spec"]["destination"]["namespace"] == "agentos"
    assert app["spec"]["syncPolicy"]["automated"]["prune"] is True
    assert app["spec"]["syncPolicy"]["automated"]["selfHeal"] is True
    assert "CreateNamespace=true" in app["spec"]["syncPolicy"]["syncOptions"]


def test_argocd_appproject_manifest():
    argocd_dir = K8S_DIR.parent / "argocd"
    project = yaml.safe_load((argocd_dir / "appproject.yaml").read_text(encoding="utf-8"))

    assert project["apiVersion"] == "argoproj.io/v1alpha1"
    assert project["kind"] == "AppProject"
    assert project["metadata"]["name"] == "agentos-project"
    assert any(d["namespace"] == "agentos" for d in project["spec"]["destinations"])

    whitelisted_kinds = {item["kind"] for item in project["spec"]["namespaceResourceWhitelist"]}
    assert {"ServiceAccount", "Role", "RoleBinding", "Deployment", "NetworkPolicy"}.issubset(whitelisted_kinds)

    blacklisted_kinds = {item["kind"] for item in project["spec"]["clusterResourceBlacklist"]}
    assert "ClusterRole" in blacklisted_kinds
    assert "ClusterRoleBinding" in blacklisted_kinds


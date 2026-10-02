# AgentOS

**Supervisor + Cognitive Engine for a Money-Earning Agent Operating System**

AgentOS is a money-earning agent operating system designed to run on Windows 11 (WSL2) and Linux. Its agents pursue revenue-generating goals through controlled tools and workflows. A bank connection is an optional money-flow capability for one account the user chooses; AgentOS is not a bank account management product. This repository provides the agent runtime and safety scaffold. A live bank connection requires an approved banking provider integration and credentials.

---

## Core Invariants

AgentOS is built upon ten non-negotiable operational invariants:

1. **Authorize Before Side Effect**: Every state-changing or external action is evaluated by the preflight Action Gate (verifying capabilities, write scopes, egress destinations, spend quotas, and human approval) before execution.
2. **Verify After Side Effect**: The Postcondition Gate validates tool outputs and environmental state changes before dependent state is committed.
3. **Checkpoint Before Retry**: Task states are saved into durable SQLite WAL checkpoints before any retryable or mutating action; external actions enforce idempotency keys to eliminate duplicate side effects.
4. **Deterministic Replay Realism**: Replays record model outputs, tool responses, random seeds, and environment metadata. External side effects are stubbed or reconciled rather than blindly re-executed.
5. **Hot-Patching at Task Boundaries**: Loaded code is never mutated in-place. Tool updates and patches are activated exclusively between task boundaries.
6. **Platform Enforcement Realism**: Distinguishes Linux mechanisms (`seccomp`, `cgroups v2`) from Windows host/VM container boundaries.
7. **Zero-Secret Model Context**: Secrets are injected only at the Egress Proxy and scrubbed from all logs and context windows.
8. **Read-Only by Default**: Agents write exclusively to designated, resolved workspace directories. Host writes, destructive deletes, and external transmissions require human authorization.
9. **Fail-Closed Auto-Quarantine**: Tool regressions trigger automated quarantine with fallback versions. Safety-critical controls fail closed rather than silently bypassing security.
10. **Ethical Review Before Action**: When an action may violate the user's stated ethical boundaries, create material harm, deceive or exploit people, or the ethical impact is uncertain, pause and ask the user with a plain-language explanation before acting. Approval is scoped to the specific action and cannot override legal or hard safety prohibitions.

---

## Architecture Overview

### Money flows and bank connection

- The bank connection belongs to the agent's money flows: receiving earnings and, when enabled, making authorized payments needed for an earning workflow.
- The product scope is one user-selected account. It does not aim to manage or aggregate a user's broader banking portfolio.
- Keep bank access behind a provider adapter and the existing Action Gate, idempotency, postcondition checks, and audit log. Never expose bank credentials or tokens to model context.
- Require explicit user approval for each outgoing transaction until the user configures clear transaction and daily limits.
- Bank linking is not operational in this repository yet. Provider onboarding, consent, transaction approvals, and a user-facing connection flow must be implemented before enabling live money movement.

### Ethical review and user approval

- The agent should aim to act ethically and make material ethical concerns visible before taking action.
- The Action Gate screens goals and action details for common deception, exploitation, privacy, unauthorized-access, harassment, discrimination, and spam signals. A match or planner-provided `ethical_concern` blocks execution until the CLI requests your decision.
- Approval applies only to the described action and scope. It is not a standing waiver for later actions.
- Illegal conduct, deliberate harm, credential theft, and other hard safety prohibitions remain blocked even if the user approves.
- The preflight screen hard-blocks explicit credential theft, data exfiltration, doxxing, blackmail, and fraud signals; user approval cannot bypass these blocks.
- The CLI asks for one-time approval; non-interactive callers must provide an approval callback or the action remains blocked. The risk screen is a heuristic and cannot recognize every ethical concern; uncertain or novel cases should also be flagged by the planner. It is a safety layer, not a guarantee of ethical behavior.

```
                                +---------------------------+
                                |     Safety Supervisor     |
                                | (Watchdog, Emergency Stop)|
                                +-------------+-------------+
                                              | Heartbeat / Supervision
                                              v
+-------------+      Goal       +---------------------------+     Action Gate     +------------------------+
| User / CLI  +---------------->|     Cognitive Engine      +-------------------->| Action Space / Sandbox |
+-------------+                 |  (DAG Planner & Governor) |  (Preflight Check)  |  (Docker / PTY / Work) |
                                +-------------+-------------+                     +-----------+------------+
                                              |                                               | Output
                                              | Commit / Checkpoint                           v
                                              v                                   +------------------------+
                                +---------------------------+                     |   Postcondition Gate   |
                                |    Durable Memory Store   |<--------------------+  (Verify & Sanitize)   |
                                | (SQLite WAL / Audit Hash) |    State Verified   +------------------------+
                                +---------------------------+
```

---

## Directory Structure

```
├── agentos.yaml                  # Policy-as-Code configuration
├── pyproject.toml                # Project metadata and dependencies
├── Dockerfile                    # Multi-stage hardened runner (UID 10001)
├── docker-compose.yml            # Local rootless container orchestration
├── AGENTOS_SPEC_REVIEW_FOR_CHATGPT.md # Full peer review dossier for ChatGPT
├── argocd/                       # ArgoCD GitOps root manifests
│   ├── appproject.yaml           # Isolated AppProject with resource whitelisting
│   └── application.yaml          # Automated continuous sync Application
├── k8s/                          # Production Kubernetes manifests
│   ├── kustomization.yaml        # Kustomize manifest bundle & image tags
│   ├── namespace.yaml            # Restricted Pod Security Standard
│   ├── rbac.yaml                 # Least privilege ServiceAccount & Role (zero wildcards)
│   ├── pvc.yaml                  # Persistent volumes for state and workspace
│   ├── deployment.yaml           # Read-only rootfs, non-root, drop ALL caps
│   ├── service.yaml              # ClusterIP on probe port 8000
│   ├── network-policy.yaml       # Default-deny egress network policy
│   └── hpa.yaml                  # Horizontal Pod Autoscaler
├── agentos/
│   ├── core/                     # Supervisor and Cognitive Engine
│   ├── cognitive/                # Task DAG, Planner, Action Gate, Postcondition Gate
│   ├── cost_governor/            # LiteLLM routing, spend tracker, prompt cache
│   ├── action_space/             # Sandboxes (Docker, Local), PTY Shell, Browser, Code Editor
│   ├── memory/                   # SQLite WAL store, working memory, procedural memory
│   ├── policy/                   # Policy engine, egress proxy, SHA-256 audit log, injection defense
│   ├── evolution/                # Quarantine manager, self-patching guard
│   └── evals/                    # Golden tasks, trace replay, red-team suite
└── tests/                        # Pytest suite
```

---

## Kubernetes rollout controls

- The namespace enforces the restricted Pod Security Standard and the workload does not mount a Kubernetes service-account token.
- Network policy allows cluster DNS and ingress-controller traffic only. Provider traffic stays blocked until a destination-aware egress gateway or CNI FQDN policy is configured; do not replace this with unrestricted HTTPS egress.
- The `Container security` workflow builds the commit image and fails on high or critical image vulnerabilities and Kubernetes misconfigurations. Require the `Build and scan` status check before merging or deploying.
- API-server and node TLS, secret encryption at rest, trusted API access ranges, and cloud workload identity are cluster-level settings and must be configured by the cluster operator.
- The deployment image is a local scaffold reference. Production releases should publish and deploy the scanned registry image by immutable digest.
- HPA is configured for pod scaling. Node autoscaling, descheduling, spot or ARM placement, and namespace cost reporting depend on the target cluster; use VPA in recommendation mode unless its request changes are coordinated with HPA.

---

## ArgoCD GitOps Deployment (Production Finale)

AgentOS provides native declarative GitOps manifests engineered for continuous delivery and automatic self-healing via **ArgoCD**.

### Architecture & Security Enforcement
- **AppProject Boundary (`argocd/appproject.yaml`)**:
  - Restricts deployments exclusively to the `agentos` target namespace.
  - Whitelists only safe, required resource kinds (`Deployment`, `HorizontalPodAutoscaler`, `NetworkPolicy`, `PersistentVolumeClaim`, `Service`, `ServiceAccount`, `Role`, `RoleBinding`).
  - Blacklists cluster-scoped privileged entities (`ClusterRole`, `ClusterRoleBinding`).
- **Application Continuous Delivery (`argocd/application.yaml`)**:
  - Tracks the `main` branch of `https://github.com/Korisipati-Charan/Agent-OS.git` at path `k8s`.
  - Enables automated synchronization with `prune: true`, `selfHeal: true`, and `CreateNamespace=true`.
  - Configures exponential backoff retry policies for zero-downtime rolling updates.
- **Kustomize Orchestration (`k8s/kustomization.yaml`)**:
  - Declaratively bundles namespaces, least-privilege RBAC, storage volumes, deployments, ClusterIP services, autoscalers, and ingress/egress network policies.
  - Enforces container image pinning: `ghcr.io/korisipati-charan/agentos:3.0.1`.

### Deploying with ArgoCD

1. **Verify or Render Local Kustomize Manifests**:
   ```bash
   kubectl kustomize k8s/
   ```

2. **Apply the Project and Application to your ArgoCD Control Plane**:
   ```bash
   kubectl apply -f argocd/appproject.yaml
   kubectl apply -f argocd/application.yaml
   ```

3. **Check Synchronization & Pod Health via ArgoCD CLI or Web UI**:
   ```bash
   argocd app get agentos-production
   argocd app sync agentos-production
   kubectl get pods -n agentos -l app.kubernetes.io/name=agentos
   ```

---

## Agent skills

Desktop skill packs (`C:\Users\charan\Desktop\Skills.md`) are installed under `.cursor/skills/`. See `AGENTS.md` for when each skill applies and how they map to runtime modules (`CostGovernor`, persona files, workspace path guard).

---

## Quickstart

### 1. Installation

Requires Python 3.11+.

```bash
# Create virtual environment
python -m venv .venv
source .venv/bin/activate  # On Windows: .\.venv\Scripts\activate

# Install dependencies
pip install -e .
```

### 2. Verify Platform Boundaries

Inspect the platform supervisor and available isolation mechanisms:

```bash
agentos info
```

### 3. Launch Mission Control Desktop Application

Launch the hardware-accelerated Operator Studio desktop interface (powered by PyWebView & Microsoft Edge WebView2 with live DAG telemetry, real-time Action Gate intervention drawer, and hardware/spend HUD meters):

```bash
agentos desktop
# Or launch directly with the root script:
python run_desktop.py
# Or run in browser mode:
agentos desktop --browser
```

### 4. Run a Task via CLI

Execute an autonomous goal through the Cognitive Engine:

```bash
agentos run "Analyze workspace files and compile status report"
```

### 4. Verify Cryptographic Audit Trail

AgentOS maintains an append-only, SHA-256 hash-chained audit ledger. Verify integrity at any time:

```bash
agentos audit verify
```

### 5. Run Evaluations & Red-Team Security Tests

```bash
agentos eval
```

### 6. HTTP Probes (Docker / Kubernetes)

Start the liveness and readiness server on port 8000:

```bash
agentos serve --host 0.0.0.0 --port 8000
```

Endpoints: `/healthz` (process alive), `/ready` (supervisor + storage reachable).

---

## Policy as Code (`agentos.yaml`)

System quotas, model routing, egress allowlists, and write permissions are declared declaratively:

```yaml
version: "3.0.1"
system:
  supervisor:
    heartbeat_interval_sec: 2
    watchdog_timeout_sec: 15
  sandbox:
    tier: "rootless_docker"
    max_memory_mb: 2048
    max_cpu_cores: 2.0
    read_only_root: true

quotas:
  spend_limits:
    per_task_usd: 2.50
    daily_usd: 25.00
    halt_on_limit: true

model_routing:
  tiers:
    tier1_fast:
      model: "gpt-4o-mini"
    tier2_reasoning:
      model: "gpt-4o"
```

---

## Hardware Acceleration & Local Inference

When running on workstations equipped with dedicated GPUs (e.g., NVIDIA GeForce RTX with 8GB+ VRAM), Tier 1 tasks (parsing, JSON validation, AST checks, turn summaries) can be routed to a local model (via Ollama or llama.cpp) to achieve sub-200ms latency with zero API egress cost.

---

## External Review with ChatGPT

A dedicated, comprehensive peer-review dossier has been prepared in:
`AGENTOS_SPEC_REVIEW_FOR_CHATGPT.md`

To have ChatGPT audit this architecture, open the review dossier and copy the Master Audit Prompt into ChatGPT. It provides full context, code mappings, logic proofs, and specific audit questions covering distributed race conditions, DNS rebinding, and crash recovery.

---

## Testing

Run the test suite:

```bash
pytest -v
```

All core invariants are validated with automated unit tests.

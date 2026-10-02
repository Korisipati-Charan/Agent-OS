/**
 * AgentOS Mission Control Studio — Client Runtime
 * Real-time WebSocket telemetry, interactive DAG canvas, and Action Gate interventions.
 */

(function () {
  "use strict";

  // State
  let ws = null;
  let activeApprovalId = null;
  let activeTaskId = null;
  let currentNodes = {};
  let reconnectTimer = null;

  // DOM Elements
  const goalInput = document.getElementById("goal-input");
  const btnLaunch = document.getElementById("btn-launch-task");
  const dagEmpty = document.getElementById("dag-empty-placeholder");
  const dagGraph = document.getElementById("dag-graph");
  const activeGoalText = document.getElementById("active-task-goal");
  const terminalStream = document.getElementById("terminal-stream");
  const workspaceTree = document.getElementById("workspace-tree");
  const taskHistoryList = document.getElementById("task-history-list");
  const actionGateDrawer = document.getElementById("action-gate-drawer");
  const emergencyOverlay = document.getElementById("emergency-overlay");

  // Gate Elements
  const gateTool = document.getElementById("gate-tool-name");
  const gateDesc = document.getElementById("gate-description");
  const gateReason = document.getElementById("gate-reason");
  const gateEthical = document.getElementById("gate-ethical");
  const gateEthicalContainer = document.getElementById("gate-ethical-container");
  const gateArgs = document.getElementById("gate-arguments");
  const gateIdemp = document.getElementById("gate-idempotency");
  const btnGateApprove = document.getElementById("btn-gate-approve");
  const btnGateReject = document.getElementById("btn-gate-reject");

  // Telemetry HUD Elements
  const gpuTelemetry = document.getElementById("gpu-telemetry");
  const cacheTelemetry = document.getElementById("cache-telemetry");
  const spendTelemetry = document.getElementById("spend-telemetry");
  const latencyTelemetry = document.getElementById("latency-telemetry");
  const supervisorBeacon = document.getElementById("supervisor-beacon");
  const supervisorLabel = document.getElementById("supervisor-label");

  // Audit Elements
  const auditTableBody = document.getElementById("audit-table-body");
  const auditIntegrityBadge = document.getElementById("audit-integrity-badge");
  const auditRecordCount = document.getElementById("audit-record-count");

  // Diff Elements
  const diffFilename = document.getElementById("diff-filename");
  const diffFilesize = document.getElementById("diff-filesize");
  const diffContent = document.getElementById("diff-content");

  // --- WebSocket Connection ---

  function initWebSocket() {
    const protocol = window.location.protocol === "https:" ? "wss:" : "ws:";
    const wsUrl = `${protocol}//${window.location.host}/ws`;

    ws = new WebSocket(wsUrl);

    ws.onopen = function () {
      logTerminal("SYSTEM", "WebSocket telemetry channel established.");
      if (reconnectTimer) {
        clearInterval(reconnectTimer);
        reconnectTimer = null;
      }
    };

    ws.onmessage = function (event) {
      try {
        const msg = JSON.parse(event.data);
        handleWsMessage(msg);
      } catch (err) {
        console.error("WS Parse error:", err);
      }
    };

    ws.onclose = function () {
      logTerminal("SYSTEM", "Telemetry connection closed. Reconnecting in 2s...", "WARN");
      if (!reconnectTimer) {
        reconnectTimer = setInterval(initWebSocket, 2000);
      }
    };

    ws.onerror = function () {
      ws.close();
    };
  }

  function handleWsMessage(msg) {
    switch (msg.type) {
      case "init_state":
        renderTasks(msg.data.tasks || []);
        if (msg.data.recent_logs) {
          msg.data.recent_logs.forEach(l => appendLogEntry(l));
        }
        setEmergencyState(msg.data.emergency_stop);
        if (msg.data.pending_approvals && msg.data.pending_approvals.length > 0) {
          showActionGate(msg.data.pending_approvals[0]);
        }
        break;

      case "terminal_log":
        appendLogEntry(msg.data);
        break;

      case "task_started":
        onTaskStarted(msg.data);
        break;

      case "node_update":
        onNodeUpdate(msg.data);
        break;

      case "task_finished":
        onTaskFinished(msg.data);
        break;

      case "action_gate_required":
        showActionGate(msg.data);
        break;

      case "action_gate_resolved":
        if (msg.data.approval_id === activeApprovalId) {
          hideActionGate();
        }
        break;

      case "emergency_stop":
        setEmergencyState(msg.data.active);
        break;
    }
  }

  // --- Task & DAG Rendering ---

  function onTaskStarted(task) {
    activeTaskId = task.task_id;
    activeGoalText.textContent = task.goal;
    currentNodes = task.nodes || {};

    dagEmpty.style.display = "none";
    dagGraph.style.display = "flex";
    renderDagNodes(currentNodes);
    btnLaunch.disabled = true;
    btnLaunch.innerHTML = "<span>EXECUTING…</span>";
    refreshTasks();
  }

  function renderDagNodes(nodes) {
    dagGraph.innerHTML = "";
    const nodeEntries = Object.entries(nodes);

    nodeEntries.forEach(([nodeId, node], index) => {
      const card = document.createElement("div");
      card.id = `node-card-${nodeId}`;
      card.className = `dag-node-card node-${(node.status || "pending").toLowerCase()}`;

      card.innerHTML = `
        <div class="dag-node-header">
          <span class="dag-node-tool">${escapeHtml(node.tool_name || "tool")}</span>
          <span class="pill-label font-mono">#${index + 1}</span>
        </div>
        <div class="dag-node-desc">${escapeHtml(node.description || nodeId)}</div>
        <div class="dag-node-footer">
          <span class="node-status-text font-mono">${escapeHtml(node.status || "PENDING")}</span>
          <span class="node-id-sub font-mono">${escapeHtml(nodeId)}</span>
        </div>
        ${index < nodeEntries.length - 1 ? '<div class="dag-connector"></div>' : ""}
      `;

      card.addEventListener("click", () => inspectNode(node));
      dagGraph.appendChild(card);
    });
  }

  function onNodeUpdate(nodeData) {
    const card = document.getElementById(`node-card-${nodeData.node_id}`);
    if (card) {
      card.className = `dag-node-card node-${nodeData.status.toLowerCase()}`;
      const statusText = card.querySelector(".node-status-text");
      if (statusText) {
        statusText.textContent = nodeData.status;
      }
    }
    if (currentNodes[nodeData.node_id]) {
      currentNodes[nodeData.node_id].status = nodeData.status;
      currentNodes[nodeData.node_id].error = nodeData.error;
    }
  }

  function onTaskFinished(task) {
    btnLaunch.disabled = false;
    btnLaunch.innerHTML = "<span>RUN GOAL</span><kbd>⏎</kbd>";
    refreshTasks();
    refreshWorkspaceFiles();
    loadAuditTrail();
  }

  function inspectNode(node) {
    logTerminal("INSPECTOR", `Inspecting Node [${node.id || node.node_id}]: Tool='${node.tool_name}' Status='${node.status}'`);
  }

  // --- Terminal Streaming ---

  function appendLogEntry(entry) {
    const line = document.createElement("div");
    line.className = "terminal-line";

    let tagClass = "tag-engine";
    if (entry.channel === "SUPERVISOR") tagClass = "tag-supervisor";
    if (entry.channel === "ACTION_GATE") tagClass = "tag-gate";
    if (entry.channel === "PLANNER") tagClass = "tag-planner";
    if (entry.level === "ERROR" || entry.level === "CRITICAL") tagClass = "tag-error";

    line.innerHTML = `
      <span class="text-dim">${entry.timestamp || ""}</span>
      <span class="log-tag ${tagClass}">[${escapeHtml(entry.channel)}]</span>
      <span>${escapeHtml(entry.message)}</span>
    `;

    terminalStream.appendChild(line);
    terminalStream.scrollTop = terminalStream.scrollHeight;
  }

  function logTerminal(channel, message, level = "INFO") {
    appendLogEntry({
      timestamp: new Date().toISOString().substring(11, 23),
      channel: channel,
      level: level,
      message: message,
    });
  }

  // --- Action Gate Intervention Drawer ---

  function showActionGate(data) {
    activeApprovalId = data.approval_id;
    gateTool.textContent = data.tool_name;
    gateDesc.textContent = data.description || "State-changing tool operation";
    gateReason.textContent = data.reason || "Action Gate preflight evaluation requires explicit confirmation.";
    gateIdemp.textContent = data.idempotency_key || `idemp_${data.node_id || "action"}`;
    gateArgs.textContent = JSON.stringify(data.arguments || {}, null, 2);

    if (data.ethical_concern) {
      gateEthical.textContent = data.ethical_concern;
      gateEthicalContainer.style.display = "block";
    } else {
      gateEthicalContainer.style.display = "none";
    }

    actionGateDrawer.classList.add("open");
    logTerminal("ACTION_GATE", `ATTENTION: Operator approval required for ${data.tool_name}`, "WARN");
  }

  function hideActionGate() {
    actionGateDrawer.classList.remove("open");
    activeApprovalId = null;
  }

  async function submitGateDecision(approved) {
    if (!activeApprovalId) return;

    try {
      const resp = await fetch("/api/action-gate/decision", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          approval_id: activeApprovalId,
          approved: approved,
          reason: approved ? "Operator verified via desktop studio." : "Operator denied.",
        }),
      });
      if (resp.ok) {
        hideActionGate();
      }
    } catch (err) {
      logTerminal("ACTION_GATE", `Decision dispatch failed: ${err}`, "ERROR");
    }
  }

  // --- Workspace Explorer ---

  async function refreshWorkspaceFiles() {
    try {
      const resp = await fetch("/api/workspace/files");
      const files = await resp.json();
      workspaceTree.innerHTML = "";

      if (!files || files.length === 0) {
        workspaceTree.innerHTML = '<div class="tree-empty">Workspace is clean. No output artifacts yet.</div>';
        return;
      }

      files.forEach(f => {
        const item = document.createElement("div");
        item.className = "file-tree-item";
        const icon = f.is_dir ? "📁" : "📄";
        const sizeStr = f.is_dir ? "" : `${f.size_bytes}B`;

        item.innerHTML = `
          <div class="file-name-group">
            <span>${icon}</span>
            <span title="${escapeHtml(f.relative_path)}">${escapeHtml(f.name)}</span>
          </div>
          <span class="file-size-badge">${sizeStr}</span>
        `;

        if (!f.is_dir) {
          item.addEventListener("click", () => {
            document.querySelectorAll(".file-tree-item").forEach(el => el.classList.remove("active"));
            item.classList.add("active");
            openFileInDiff(f.relative_path);
          });
        }
        workspaceTree.appendChild(item);
      });
    } catch (err) {
      workspaceTree.innerHTML = `<div class="tree-empty text-rose">Error reading workspace: ${err}</div>`;
    }
  }

  async function openFileInDiff(relPath) {
    switchTab("diff");
    diffFilename.textContent = `./workspace/${relPath}`;
    diffFilesize.textContent = "Loading…";

    try {
      const resp = await fetch(`/api/workspace/file?path=${encodeURIComponent(relPath)}`);
      if (!resp.ok) {
        throw new Error((await resp.json()).detail || "Read failed");
      }
      const data = await resp.json();
      diffFilesize.textContent = `${data.size} bytes`;
      diffContent.textContent = data.content;
    } catch (err) {
      diffFilesize.textContent = "Error";
      diffContent.textContent = `// Error loading file: ${err.message}`;
    }
  }

  // --- Task History ---

  async function refreshTasks() {
    try {
      const resp = await fetch("/api/tasks");
      const tasks = await resp.json();
      renderTasks(tasks);
    } catch (err) {
      console.error("Task refresh failed:", err);
    }
  }

  function renderTasks(tasks) {
    taskHistoryList.innerHTML = "";
    if (!tasks || tasks.length === 0) {
      taskHistoryList.innerHTML = '<div class="tree-empty">No previous task records found.</div>';
      return;
    }

    tasks.forEach(t => {
      const item = document.createElement("div");
      item.className = "task-item";
      const statusClass = `status-badge-${(t.status || "pending").toLowerCase()}`;

      item.innerHTML = `
        <div class="task-item-header">
          <span class="task-id-text">${escapeHtml(t.task_id)}</span>
          <span class="task-status-badge ${statusClass}">${escapeHtml(t.status)}</span>
        </div>
        <div class="task-goal-snippet" title="${escapeHtml(t.goal)}">${escapeHtml(t.goal)}</div>
      `;

      item.addEventListener("click", () => {
        document.querySelectorAll(".task-item").forEach(el => el.classList.remove("active"));
        item.classList.add("active");
        inspectTask(t.task_id, t.goal);
      });

      taskHistoryList.appendChild(item);
    });
  }

  async function inspectTask(taskId, goal) {
    activeGoalText.textContent = goal;
    try {
      const resp = await fetch(`/api/tasks/${taskId}`);
      const data = await resp.json();
      if (data.nodes) {
        dagEmpty.style.display = "none";
        dagGraph.style.display = "flex";
        renderDagNodes(data.nodes);
      }
    } catch (err) {
      console.error("Task detail load failed:", err);
    }
  }

  // --- Audit Trail ---

  async function loadAuditTrail() {
    try {
      const resp = await fetch("/api/audit/logs");
      const data = await resp.json();

      if (data.verified) {
        auditIntegrityBadge.className = "badge badge-success";
        auditIntegrityBadge.textContent = "✓ SHA-256 HASH CHAIN VERIFIED";
      } else {
        auditIntegrityBadge.className = "badge badge-danger";
        auditIntegrityBadge.textContent = "✗ HASH CHAIN COMPROMISED";
      }

      auditRecordCount.textContent = `${data.total_records || 0} records`;
      auditTableBody.innerHTML = "";

      if (!data.records || data.records.length === 0) {
        auditTableBody.innerHTML = '<tr><td colspan="5" class="text-center text-dim">No records logged.</td></tr>';
        return;
      }

      data.records.reverse().forEach(r => {
        const tr = document.createElement("tr");
        const prevShort = (r.prev_hash || "GENESIS").substring(0, 10) + "…";
        const hashShort = (r.record_hash || "").substring(0, 10) + "…";
        const timeStr = (r.timestamp || "").replace("T", " ").substring(0, 19);

        tr.innerHTML = `
          <td>${timeStr}</td>
          <td><span class="font-mono text-cyan">${escapeHtml(r.action_type || "")}</span></td>
          <td>${escapeHtml(r.actor || "")}</td>
          <td class="text-dim font-mono" title="${escapeHtml(r.prev_hash || "")}">${prevShort}</td>
          <td class="text-green font-mono" title="${escapeHtml(r.record_hash || "")}">${hashShort}</td>
        `;
        auditTableBody.appendChild(tr);
      });
    } catch (err) {
      console.error("Audit load failed:", err);
    }
  }

  // --- Emergency Stop & Supervisor Controls ---

  function setEmergencyState(active) {
    if (active) {
      emergencyOverlay.style.display = "flex";
      supervisorBeacon.className = "status-dot dot-danger";
      supervisorLabel.textContent = "EMERGENCY STOP ARMED";
      supervisorLabel.className = "status-label text-rose";
    } else {
      emergencyOverlay.style.display = "none";
      supervisorBeacon.className = "status-dot dot-active";
      supervisorLabel.textContent = "SUPERVISOR ARMED // WIN11-WSL2";
      supervisorLabel.className = "status-label text-green";
    }
  }

  async function triggerEmergencyStop() {
    try {
      await fetch("/api/supervisor/emergency-stop", { method: "POST" });
    } catch (err) {
      console.error("Emergency stop failed:", err);
    }
  }

  async function resumeSupervisor() {
    try {
      await fetch("/api/supervisor/resume", { method: "POST" });
    } catch (err) {
      console.error("Supervisor resume failed:", err);
    }
  }

  // --- Telemetry Polling ---

  async function pollMetrics() {
    try {
      const resp = await fetch("/api/metrics");
      const m = await resp.json();

      if (gpuTelemetry) gpuTelemetry.textContent = `RTX 5060 (${m.gpu_utilization_pct}%)`;
      if (cacheTelemetry) cacheTelemetry.textContent = `${m.kv_cache_hit_rate}%`;
      if (latencyTelemetry) latencyTelemetry.textContent = `${m.doherty_latency_ms}ms`;

      const statusResp = await fetch("/api/status");
      const st = await statusResp.json();
      if (spendTelemetry) {
        spendTelemetry.textContent = `$${st.cost_governor.total_spend_usd.toFixed(3)}`;
      }
    } catch (err) {
      // Background poll silently fails if offline
    }
  }

  // --- Goal Launch Execution ---

  async function launchGoal() {
    const goal = goalInput.value.trim();
    if (!goal) return;

    btnLaunch.disabled = true;
    btnLaunch.innerHTML = "<span>COMPILING…</span>";

    try {
      const resp = await fetch("/api/tasks", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ goal: goal }),
      });

      if (!resp.ok) {
        const err = await resp.json();
        throw new Error(err.detail || "Task submission rejected.");
      }

      goalInput.value = "";
    } catch (err) {
      logTerminal("PLANNER", `Goal launch failed: ${err.message}`, "ERROR");
      btnLaunch.disabled = false;
      btnLaunch.innerHTML = "<span>RUN GOAL</span><kbd>⏎</kbd>";
    }
  }

  // --- UI Helpers & Tab Switching ---

  function switchTab(tabName) {
    document.querySelectorAll(".drawer-tab").forEach(tab => {
      tab.classList.toggle("active", tab.dataset.tab === tabName);
    });
    document.querySelectorAll(".tab-pane").forEach(pane => {
      pane.classList.toggle("active", pane.id === `tab-${tabName}`);
    });
    if (tabName === "audit") {
      loadAuditTrail();
    }
  }

  function escapeHtml(str) {
    return String(str)
      .replace(/&/g, "&amp;")
      .replace(/</g, "&lt;")
      .replace(/>/g, "&gt;")
      .replace(/"/g, "&quot;")
      .replace(/'/g, "&#039;");
  }

  // --- Event Bindings ---

  btnLaunch.addEventListener("click", launchGoal);
  goalInput.addEventListener("keydown", (e) => {
    if (e.key === "Enter") launchGoal();
  });

  document.querySelectorAll(".drawer-tab").forEach(tab => {
    tab.addEventListener("click", () => switchTab(tab.dataset.tab));
  });

  document.getElementById("btn-clear-logs").addEventListener("click", () => {
    terminalStream.innerHTML = "";
  });

  document.getElementById("btn-refresh-files").addEventListener("click", refreshWorkspaceFiles);

  document.getElementById("btn-emergency-stop").addEventListener("click", triggerEmergencyStop);
  document.getElementById("btn-resume-supervisor").addEventListener("click", resumeSupervisor);

  btnGateApprove.addEventListener("click", () => submitGateDecision(true));
  btnGateReject.addEventListener("click", () => submitGateDecision(false));

  document.getElementById("btn-evals").addEventListener("click", () => {
    goalInput.value = "Execute full golden task evaluation benchmark and verify model routing.";
    launchGoal();
  });

  // Keyboard Shortcuts (Y for Approve, N for Reject, Escape for Drawer)
  window.addEventListener("keydown", (e) => {
    if (actionGateDrawer.classList.contains("open")) {
      if (e.key === "y" || e.key === "Y") {
        submitGateDecision(true);
      } else if (e.key === "n" || e.key === "N") {
        submitGateDecision(false);
      }
    }
  });

  // Initialize
  initWebSocket();
  refreshWorkspaceFiles();
  refreshTasks();
  loadAuditTrail();
  setInterval(pollMetrics, 2000);
})();

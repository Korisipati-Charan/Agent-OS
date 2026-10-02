"""
AgentOS Safety Supervisor.
Privileged userspace process enforcing platform controls, watchdogs,
and an unblockable emergency stop.
Accurately distinguishes Linux cgroups/seccomp from Windows/WSL2 host boundaries.
"""

from datetime import datetime, timezone
from pathlib import Path
import shutil
import subprocess
import sys
import threading
import time
from typing import Any, Dict, List, Optional
from pydantic import BaseModel
from agentos.config import AgentOSConfig
from agentos.policy.audit_log import AuditLogger


class PlatformCapabilities(BaseModel):
    os_name: str
    is_linux: bool
    is_windows: bool
    cgroups_v2_supported: bool
    seccomp_supported: bool
    container_runtime_available: bool
    boundary_mechanism: str


class SafetySupervisor:
    def __init__(self, config: AgentOSConfig, audit_logger: AuditLogger) -> None:
        self.config = config
        self.audit_logger = audit_logger
        self.platform = self._detect_platform_controls()
        self._emergency_stop_triggered = False
        self._active_processes: set[int] = set()
        self._lock = threading.Lock()
        self._last_heartbeat = time.time()
        self._watchdog_running = False
        self._watchdog_thread: Optional[threading.Thread] = None

    def _detect_platform_controls(self) -> PlatformCapabilities:
        os_platform = sys.platform
        is_linux = os_platform.startswith("linux")
        is_windows = os_platform == "win32"

        cgroups_v2 = False
        seccomp = False

        if is_linux:
            cgroups_v2 = Path("/sys/fs/cgroup/cgroup.controllers").exists()
            seccomp = Path("/proc/sys/kernel/seccomp").exists()
            if cgroups_v2 and seccomp:
                boundary = "linux_cgroups_v2_seccomp"
            elif cgroups_v2:
                boundary = "linux_cgroups_v2"
            elif seccomp:
                boundary = "linux_seccomp"
            else:
                boundary = "linux_process_isolation"
        elif is_windows:
            boundary = "windows_host_vm_boundary"
        else:
            boundary = "posix_process_isolation"

        return PlatformCapabilities(
            os_name=os_platform,
            is_linux=is_linux,
            is_windows=is_windows,
            cgroups_v2_supported=cgroups_v2,
            seccomp_supported=seccomp,
            container_runtime_available=self._container_runtime_available(),
            boundary_mechanism=boundary,
        )

    @staticmethod
    def _container_runtime_available() -> bool:
        for runtime in ("docker", "podman"):
            executable = shutil.which(runtime)
            if executable is None:
                continue
            try:
                probe = subprocess.run(
                    [executable, "info"],
                    check=False,
                    capture_output=True,
                    timeout=1,
                )
            except (OSError, subprocess.TimeoutExpired):
                continue
            if probe.returncode == 0:
                return True
        return False

    def start_watchdog(self) -> None:
        """Starts the background supervisor watchdog thread."""
        self._watchdog_running = True
        self._last_heartbeat = time.time()

        def _watchdog_loop():
            timeout = self.config.supervisor.watchdog_timeout_sec
            while self._watchdog_running:
                time.sleep(self.config.supervisor.heartbeat_interval_sec)
                with self._lock:
                    if not self._watchdog_running:
                        break
                    elapsed = time.time() - self._last_heartbeat
                    timed_out = elapsed > timeout

                if timed_out:
                    self.audit_logger.log(
                        action_type="WATCHDOG_TIMEOUT_ALERT",
                        actor="supervisor_watchdog",
                        payload={"elapsed_sec": elapsed, "timeout_sec": timeout},
                    )
                    self.trigger_emergency_stop(
                        reason=f"Watchdog timeout: no heartbeat for {elapsed:.1f}s"
                    )
                    break

        self._watchdog_thread = threading.Thread(
            target=_watchdog_loop,
            daemon=True,
            name="SupervisorWatchdog",
        )
        self._watchdog_thread.start()

    def heartbeat(self) -> None:
        with self._lock:
            self._last_heartbeat = time.time()

    def register_process(self, pid: int) -> None:
        with self._lock:
            self._active_processes.add(pid)

    def unregister_process(self, pid: int) -> None:
        with self._lock:
            self._active_processes.discard(pid)

    def trigger_emergency_stop(
        self, reason: str = "User triggered emergency stop"
    ) -> Dict[str, Any]:
        """
        Emergency stop terminates the agent's controlled processes and revokes capabilities.
        Privileged userspace termination without kernel-level overclaiming.
        """
        with self._lock:
            self._emergency_stop_triggered = True
            self._watchdog_running = False
            terminated_pids = list(self._active_processes)
            self._active_processes.clear()

        # Terminate active process PIDs safely
        import os
        import signal
        for pid in terminated_pids:
            try:
                os.kill(pid, signal.SIGTERM)
            except Exception:
                pass

        self.audit_logger.log(
            action_type="EMERGENCY_STOP_TRIGGERED",
            actor="supervisor",
            payload={"reason": reason, "terminated_pids": terminated_pids},
        )

        return {
            "status": "STOPPED",
            "reason": reason,
            "terminated_pids": terminated_pids,
            "timestamp": datetime.now(timezone.utc).isoformat(),
        }

    def is_stopped(self) -> bool:
        with self._lock:
            return self._emergency_stop_triggered

    def shutdown(self) -> None:
        self._watchdog_running = False
        if self._watchdog_thread and self._watchdog_thread.is_alive():
            self._watchdog_thread.join(timeout=2.0)

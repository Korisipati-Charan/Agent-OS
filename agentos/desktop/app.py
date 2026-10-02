"""
AgentOS Desktop Application Launcher.
Initializes local FastAPI telemetry server in a background thread and mounts the native
PyWebView shell (Microsoft Edge WebView2 Evergreen) with hardware acceleration.
"""

from __future__ import annotations

import argparse
import socket
import sys
import threading
import time
import urllib.request
import webbrowser
from typing import Optional

import uvicorn

from agentos.desktop.server import create_desktop_app
from agentos.runtime.bootstrap import build_runtime


def find_free_port(preferred: int = 18991) -> int:
    """Check if preferred port is free, otherwise locate an ephemeral open port."""
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
        try:
            s.bind(("127.0.0.1", preferred))
            return preferred
        except OSError:
            pass

    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
        s.bind(("127.0.0.1", 0))
        return s.getsockname()[1]


def wait_for_server(port: int, timeout: float = 6.0) -> bool:
    """Poll the status probe until the local FastAPI engine responds."""
    start = time.time()
    url = f"http://127.0.0.1:{port}/api/status"
    while time.time() - start < timeout:
        try:
            with urllib.request.urlopen(url, timeout=1.0) as resp:
                if resp.status == 200:
                    return True
        except Exception:
            time.sleep(0.15)
    return False


def run_desktop_app(
    config_path: str = "agentos.yaml",
    workspace: str = "./workspace",
    port: Optional[int] = None,
    browser_mode: bool = False,
    debug: bool = False,
) -> None:
    """Launch AgentOS Mission Control Studio."""
    selected_port = port or find_free_port(18991)
    runtime = build_runtime(config_path=config_path, workspace=workspace)
    app = create_desktop_app(runtime=runtime)

    config = uvicorn.Config(
        app=app,
        host="127.0.0.1",
        port=selected_port,
        log_level="warning" if not debug else "info",
        access_log=False,
    )
    server = uvicorn.Server(config)

    server_thread = threading.Thread(target=server.run, daemon=True)
    server_thread.start()

    ready = wait_for_server(selected_port)
    if not ready:
        print(f"[AgentOS Error] Desktop server failed to bind to 127.0.0.1:{selected_port}", file=sys.stderr)
        sys.exit(1)

    app_url = f"http://127.0.0.1:{selected_port}"
    print(f"\n[AgentOS Mission Control Studio] Running at: {app_url}")

    if browser_mode:
        print("[AgentOS] Browser mode requested. Launching default system browser...")
        webbrowser.open(app_url)
        try:
            while server_thread.is_alive():
                time.sleep(1.0)
        except KeyboardInterrupt:
            print("\n[AgentOS] Operator terminated server session.")
        return

    # Attempt native PyWebView window
    try:
        import webview

        window = webview.create_window(
            title="AgentOS — Mission Control Studio (v3.0.1)",
            url=app_url,
            width=1440,
            height=920,
            min_size=(1024, 700),
            background_color="#06090e",
            text_select=True,
        )

        webview.start(debug=debug)
    except Exception as exc:
        print(f"[AgentOS] Native WebView initialization notice: {exc}")
        print("[AgentOS] Falling back gracefully to system browser window...")
        webbrowser.open(app_url)
        try:
            while server_thread.is_alive():
                time.sleep(1.0)
        except KeyboardInterrupt:
            print("\n[AgentOS] Operator terminated server session.")


def main() -> None:
    parser = argparse.ArgumentParser(description="AgentOS Desktop Mission Control Studio")
    parser.add_argument("--config", default="agentos.yaml", help="Path to agentos.yaml")
    parser.add_argument("--workspace", default="./workspace", help="Path to workspace root")
    parser.add_argument("--port", type=int, default=None, help="Explicit port to bind")
    parser.add_argument("--browser", action="store_true", help="Launch in default system browser instead of native window")
    parser.add_argument("--debug", action="store_true", help="Enable verbose debug logs")

    args = parser.parse_args()
    run_desktop_app(
        config_path=args.config,
        workspace=args.workspace,
        port=args.port,
        browser_mode=args.browser,
        debug=args.debug,
    )


if __name__ == "__main__":
    main()

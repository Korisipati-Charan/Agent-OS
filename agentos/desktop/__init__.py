"""
AgentOS Mission Control Desktop Application.
PyWebView shell embedding a modern, hardware-accelerated Operator Studio backed by FastAPI.
"""

from agentos.desktop.server import create_desktop_app

__all__ = ["create_desktop_app"]

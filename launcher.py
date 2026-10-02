"""
AgentOS Standalone Executable Launcher.
Entry point for packaged Windows distribution.
"""

import sys
from pathlib import Path

if getattr(sys, "frozen", False) and hasattr(sys, "_MEIPASS"):
    bundle_dir = Path(sys._MEIPASS)
    if str(bundle_dir) not in sys.path:
        sys.path.insert(0, str(bundle_dir))
else:
    repo_root = Path(__file__).resolve().parent
    if str(repo_root) not in sys.path:
        sys.path.insert(0, str(repo_root))

from agentos.cli import main

if __name__ == "__main__":
    main()

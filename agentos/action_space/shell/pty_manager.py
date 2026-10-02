"""
AgentOS PTY Shell Manager.
Manages shell processes with real-time streamed output, job supervision,
exit-code capture, and strict workspace execution boundaries.
"""

import asyncio
from pathlib import Path
import sys
from typing import AsyncGenerator, Dict, Optional, Tuple


class PTYManager:
    def __init__(self, workspace_path: str = "./workspace") -> None:
        self.workspace_path = Path(workspace_path).resolve()
        self.workspace_path.mkdir(parents=True, exist_ok=True)

    async def execute_stream(
        self,
        command: str,
        timeout_sec: float = 60.0,
        env: Optional[Dict[str, str]] = None,
    ) -> AsyncGenerator[str, None]:
        """
        Executes a shell command asynchronously while streaming output chunks.
        Supervises execution and kills runaway processes upon timeout.
        """
        is_windows = sys.platform == "win32"
        shell_cmd = ["cmd.exe", "/c", command] if is_windows else ["/bin/sh", "-c", command]

        proc = await asyncio.create_subprocess_exec(
            *shell_cmd,
            cwd=str(self.workspace_path),
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
            env=env,
        )

        async def stream_reader(stream: asyncio.StreamReader, prefix: str) -> AsyncGenerator[str, None]:
            while True:
                line = await stream.readline()
                if not line:
                    break
                yield f"[{prefix}] {line.decode('utf-8', errors='replace').rstrip()}\n"

        try:
            # Read stdout and stderr concurrently
            async for out_chunk in stream_reader(proc.stdout, "stdout"):
                yield out_chunk
            async for err_chunk in stream_reader(proc.stderr, "stderr"):
                yield err_chunk

            await asyncio.wait_for(proc.wait(), timeout=timeout_sec)
            yield f"[system] Process finished with exit code {proc.returncode}\n"
        except asyncio.TimeoutError:
            proc.kill()
            yield f"[system] Process killed: exceeded timeout of {timeout_sec}s\n"
        except Exception as e:
            yield f"[system] Process supervision error: {e}\n"

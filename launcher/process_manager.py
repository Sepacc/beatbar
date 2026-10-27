"""
process_manager.py - Manages launching and lifecycle of Beatbar Suite programs.

Supports silent launching (no console windows) of compiled executables or Python scripts,
tracking active instances, and managing the Web Viewer server.
"""

import os
import sys
import time
import socket
import webbrowser
import subprocess
from typing import Dict, Optional, Tuple
from launcher.version_manager import (
    ProgramConfig, PROGRAM_REGISTRY, ROOT_DIR, find_primary_compiled_exe
)


def is_port_in_use(port: int, host: str = "127.0.0.1") -> bool:
    """Checks if a local port is already bound / occupied by an external process."""
    try:
        with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
            s.settimeout(0.5)
            return s.connect_ex((host, port)) == 0
    except Exception:
        return False


def find_available_port(start_port: int = 8080, max_attempts: int = 50, host: str = "127.0.0.1") -> int:
    """Finds the first available port starting from start_port."""
    port = start_port
    for _ in range(max_attempts):
        if not is_port_in_use(port, host):
            return port
        port += 1
    return start_port


def get_silent_python_exe() -> str:
    """Returns path to pythonw.exe to prevent any console window from appearing."""
    if sys.platform == "win32":
        base_dir = os.path.dirname(sys.executable)
        pyw = os.path.join(base_dir, "pythonw.exe")
        if os.path.exists(pyw):
            return pyw
    return sys.executable


def get_silent_popen_kwargs(is_headless: bool = False) -> dict:
    """Returns subprocess creation flags configured for clean launching on Windows."""
    kwargs = {}
    if sys.platform == "win32":
        if is_headless:
            kwargs["creationflags"] = subprocess.CREATE_NO_WINDOW
        else:
            kwargs["creationflags"] = subprocess.CREATE_NEW_PROCESS_GROUP
    return kwargs


class ProcessManager:
    def __init__(self):
        # Maps prog_id to active subprocess.Popen instance
        self._active_processes: Dict[str, subprocess.Popen] = {}
        self.web_port: int = 8080

    def is_running(self, prog_id: str) -> bool:
        """Checks if a program launched from this session is currently running."""
        proc = self._active_processes.get(prog_id)
        if proc is None:
            return False
        if proc.poll() is None:
            return True
        # Process has terminated
        del self._active_processes[prog_id]
        return False

    def launch_program(self, prog_id: str, force_python: bool = False, extra_args: Optional[list] = None) -> Tuple[bool, str]:
        """
        Launches the specified program silently without console windows.
        If force_python is False and a compiled executable exists, runs the compiled .exe.
        Otherwise, runs the Python entry script via pythonw.
        Optional extra_args (e.g. file paths) are passed to the program.
        """
        prog = PROGRAM_REGISTRY.get(prog_id)
        if not prog:
            return False, f"Unknown program ID '{prog_id}'"

        # Web Viewer special handling
        if prog.is_web:
            return self.launch_web_viewer()

        # Check for compiled executable
        exe_path = find_primary_compiled_exe(prog)
        use_exe = (exe_path is not None and os.path.exists(exe_path) and not force_python)

        popen_kwargs = get_silent_popen_kwargs()

        cwd_dir = getattr(prog, "working_dir", None) or ROOT_DIR
        args = [str(a) for a in extra_args] if extra_args else []

        try:
            if use_exe:
                cmd = [exe_path] + args
                print(f"[ProcessManager] Launching compiled executable silently: {exe_path} {args}")
                proc = subprocess.Popen(
                    cmd,
                    cwd=cwd_dir,
                    **popen_kwargs
                )
                self._active_processes[prog_id] = proc
                return True, f"Launched {prog.name} (Compiled Binary)"
            else:
                script_path = prog.entry_script
                if not os.path.exists(script_path):
                    return False, f"Entry script not found at {script_path}"
                py_exec = get_silent_python_exe()
                cmd = [py_exec, script_path] + args
                print(f"[ProcessManager] Launching Python script silently: {' '.join(cmd)}")
                proc = subprocess.Popen(
                    cmd,
                    cwd=cwd_dir,
                    **popen_kwargs
                )
                self._active_processes[prog_id] = proc
                return True, f"Launched {prog.name} (Python Script)"
        except Exception as e:
            return False, f"Failed to launch {prog.name}: {e}"

    def launch_web_viewer(self, auto_open_browser: bool = True) -> Tuple[bool, str]:
        """Launches the Beatbar Web Viewer Flask server silently and opens the browser."""
        prog = PROGRAM_REGISTRY.get("beatbar_web")
        if not prog:
            return False, "Web viewer configuration missing"

        # Check if already running from this session
        if self.is_running("beatbar_web"):
            if auto_open_browser:
                webbrowser.open(f"http://localhost:{self.web_port}")
            return True, f"Web viewer is already running on port {self.web_port}"

        # Port binding pre-check: ensure port is not occupied by an external process
        if is_port_in_use(self.web_port):
            print(f"[ProcessManager] Port {self.web_port} is already held by an external process. Searching for available port...")
            self.web_port = find_available_port(self.web_port + 1)
            print(f"[ProcessManager] Selected available port {self.web_port}")

        script_path = prog.entry_script
        if not os.path.exists(script_path):
            return False, f"Web runner not found at {script_path}"

        py_exec = get_silent_python_exe()
        cmd = [py_exec, script_path, "--port", str(self.web_port)]
        if auto_open_browser:
            cmd.append("--open")

        popen_kwargs = get_silent_popen_kwargs(is_headless=True)

        try:
            print(f"[ProcessManager] Starting Web Viewer server silently on port {self.web_port}...")
            proc = subprocess.Popen(
                cmd,
                cwd=ROOT_DIR,
                **popen_kwargs
            )
            self._active_processes["beatbar_web"] = proc
            return True, f"Web Viewer server started on http://localhost:{self.web_port}"
        except Exception as e:
            return False, f"Failed to start Web Viewer: {e}"

    def stop_program(self, prog_id: str) -> Tuple[bool, str]:
        """Terminates an active program process."""
        proc = self._active_processes.get(prog_id)
        if not proc:
            return False, "Process is not running"

        try:
            proc.terminate()
            time.sleep(0.2)
            if proc.poll() is None:
                proc.kill()
            if prog_id in self._active_processes:
                del self._active_processes[prog_id]
            return True, f"Stopped {prog_id}"
        except Exception as e:
            return False, f"Error stopping {prog_id}: {e}"

    def open_web_in_browser(self):
        """Opens the web viewer URL in the system's default browser."""
        webbrowser.open(f"http://localhost:{self.web_port}")


# Global instance
process_manager = ProcessManager()

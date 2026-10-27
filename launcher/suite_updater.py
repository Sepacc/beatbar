"""
suite_updater.py - Automated One-Click Suite Updater for Beatbar Suite.

Pulls updates via git sync and automatically detects & recompiles dirty suite components.
"""

import os
import sys
import shutil
import subprocess
from typing import List, Optional

from PyQt6.QtCore import Qt, pyqtSignal, QThread, QSize, QTimer
from PyQt6.QtWidgets import (
    QDialog, QVBoxLayout, QHBoxLayout, QLabel, QPushButton,
    QProgressBar, QTextEdit, QFrame, QMessageBox
)
from PyQt6.QtGui import QFont, QCursor

from launcher.version_manager import (
    PROGRAM_REGISTRY, COMPILED_DIR, ROOT_DIR,
    read_source_version, check_program_dirty, clean_old_compiled_versions
)
from launcher.compiler import (
    build_pyinstaller_command, is_pyinstaller_installed, TEMP_BUILD_DIR
)

try:
    from icon_utils import get_feather_icon, get_suite_pixmap
except ImportError:
    get_feather_icon = lambda name, color="#ffffff", size=16: None
    get_suite_pixmap = lambda name, size=24, dark_mode=True: None


class SuiteUpdaterWorker(QThread):
    """
    Background worker that executes Git sync and recompiles all dirty suite components.
    Streams logs and progress in real time to the UI.
    """
    log_signal = pyqtSignal(str)
    status_signal = pyqtSignal(str, int)  # status_message, percent
    finished_signal = pyqtSignal(bool, str, list)  # success, summary_msg, recompiled_ids

    def __init__(self, parent=None):
        super().__init__(parent)
        self._is_cancelled = False
        self._current_proc: Optional[subprocess.Popen] = None

    def cancel(self):
        self._is_cancelled = True
        if self._current_proc and self._current_proc.poll() is None:
            try:
                self._current_proc.kill()
            except Exception:
                pass

    def run(self):
        self.log_signal.emit("=" * 64)
        self.log_signal.emit("  AUTOMATED BEATBAR SUITE ONE-CLICK UPDATER")
        self.log_signal.emit("=" * 64)

        # -----------------------------------------------------------------
        # STEP 1: Git Sync / Pull Remote Updates
        # -----------------------------------------------------------------
        self.status_signal.emit("Step 1/2: Checking Git repository and pulling updates...", 15)
        self.log_signal.emit("\n[Git Sync] Checking repository status...")

        git_dir = os.path.join(ROOT_DIR, ".git")
        git_pulled = False
        if os.path.isdir(git_dir):
            try:
                creationflags = getattr(subprocess, 'CREATE_NO_WINDOW', 0x08000000) if sys.platform == 'win32' else 0
                git_proc = subprocess.run(
                    ["git", "pull", "--rebase"],
                    cwd=ROOT_DIR,
                    capture_output=True,
                    text=True,
                    timeout=30,
                    creationflags=creationflags
                )
                if git_proc.returncode == 0:
                    git_pulled = True
                    out = git_proc.stdout.strip() or "Already up to date."
                    self.log_signal.emit(f"[Git Sync] Success: {out}")
                else:
                    err = git_proc.stderr.strip() or git_proc.stdout.strip()
                    self.log_signal.emit(f"[Git Sync] Notice: git pull returned code {git_proc.returncode}")
                    if err:
                        self.log_signal.emit(f"  {err}")
                    self.log_signal.emit("  Continuing with dirty component check on local files.")
            except Exception as e:
                self.log_signal.emit(f"[Git Sync] Notice: Could not run git ({e}). Proceeding to local dirty check.")
        else:
            self.log_signal.emit("[Git Sync] No .git directory detected. Checking local dirty components.")

        if self._is_cancelled:
            self.finished_signal.emit(False, "Update cancelled by user.", [])
            return

        # -----------------------------------------------------------------
        # STEP 2: Detect Dirty Components
        # -----------------------------------------------------------------
        self.status_signal.emit("Step 2/2: Analyzing suite components for dirty status...", 30)
        self.log_signal.emit("\n[Dirty Analysis] Scanning suite executables vs source files...")

        # Candidates to compile: maker, viewer, skins (and launcher if dirty)
        candidate_keys = ["beatbar_maker", "beatbar_viewer", "beatbar_skins", "launcher"]
        dirty_progs = []

        for key in candidate_keys:
            prog = PROGRAM_REGISTRY.get(key)
            if not prog or not prog.can_compile:
                continue

            is_dirty, reason = check_program_dirty(prog)
            if is_dirty:
                dirty_progs.append(prog)
                self.log_signal.emit(f"  * {prog.name} ({prog.id}): DIRTY -> {reason}")
            else:
                self.log_signal.emit(f"  * {prog.name} ({prog.id}): CLEAN (Up to date)")

        if not dirty_progs:
            self.status_signal.emit("All suite components are clean and up to date!", 100)
            self.log_signal.emit("\n[Complete] All programs are compiled and completely up-to-date!")
            self.finished_signal.emit(True, "All suite components are already up-to-date.", [])
            return

        # -----------------------------------------------------------------
        # STEP 3: Recompile Dirty Components
        # -----------------------------------------------------------------
        if not is_pyinstaller_installed():
            msg = "PyInstaller is not detected in your Python environment. Please install it with 'pip install pyinstaller'."
            self.log_signal.emit(f"[Error] {msg}")
            self.status_signal.emit("PyInstaller missing", 100)
            self.finished_signal.emit(False, msg, [])
            return

        total_dirty = len(dirty_progs)
        self.log_signal.emit(f"\n[Compiler] Starting automatic recompilation of {total_dirty} dirty component(s)...")

        recompiled = []
        creationflags = getattr(subprocess, 'CREATE_NO_WINDOW', 0x08000000) if sys.platform == 'win32' else 0

        for idx, prog in enumerate(dirty_progs, start=1):
            if self._is_cancelled:
                self.finished_signal.emit(False, "Update cancelled by user.", recompiled)
                return

            base_pct = 30 + int((idx - 1) / total_dirty * 65)
            self.status_signal.emit(f"Recompiling {prog.name} ({idx}/{total_dirty})...", base_pct)
            self.log_signal.emit("-" * 50)
            self.log_signal.emit(f"Compiling: {prog.name} [{idx}/{total_dirty}]")

            # Clean previous version files
            clean_old_compiled_versions(prog)

            # Build command
            cmd, source_version = build_pyinstaller_command(prog)
            self.log_signal.emit(f"Target Version: v{source_version}")

            try:
                self._current_proc = subprocess.Popen(
                    cmd,
                    cwd=ROOT_DIR,
                    stdout=subprocess.PIPE,
                    stderr=subprocess.STDOUT,
                    text=True,
                    bufsize=1,
                    universal_newlines=True,
                    creationflags=creationflags
                )

                for line in iter(self._current_proc.stdout.readline, ""):
                    if self._is_cancelled:
                        break
                    line_str = line.strip()
                    if line_str:
                        self.log_signal.emit(f"  {line_str}")

                self._current_proc.stdout.close()
                code = self._current_proc.wait()

                if self._is_cancelled:
                    self.finished_signal.emit(False, "Update cancelled by user.", recompiled)
                    return

                if code == 0:
                    # Write companion .version file
                    comp_ver_path = os.path.join(COMPILED_DIR, f"{os.path.splitext(prog.target_exe_name)[0]}.version")
                    with open(comp_ver_path, "w", encoding="utf-8") as vf:
                        vf.write(source_version)
                    recompiled.append(prog.id)
                    self.log_signal.emit(f"[Success] Compiled {prog.name} (v{source_version}) successfully!")
                else:
                    self.log_signal.emit(f"[Failed] PyInstaller returned exit code {code} for {prog.name}")

            except Exception as e:
                self.log_signal.emit(f"[Exception] Failed compiling {prog.name}: {e}")

            # Clean temporary build directory
            if os.path.exists(TEMP_BUILD_DIR):
                try:
                    shutil.rmtree(TEMP_BUILD_DIR, ignore_errors=True)
                except Exception:
                    pass

        self.status_signal.emit("Suite update complete!", 100)
        self.log_signal.emit("=" * 64)
        if len(recompiled) == total_dirty:
            summary = f"Successfully recompiled all {len(recompiled)} dirty component(s)!"
            self.log_signal.emit(f"  [SUCCESS] {summary}")
            self.finished_signal.emit(True, summary, recompiled)
        else:
            summary = f"Recompiled {len(recompiled)} of {total_dirty} dirty component(s)."
            self.log_signal.emit(f"  [PARTIAL] {summary}")
            self.finished_signal.emit(True, summary, recompiled)


class SuiteUpdateDialog(QDialog):
    """
    Modern modal dialog for the One-Click Suite Updater.
    Automatically kicks off sync & dirty recompilation upon display.
    """
    suite_updated = pyqtSignal()

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setWindowTitle("Automated Suite Updater")
        self.setFixedSize(680, 520)
        self.setWindowFlags(self.windowFlags() & ~Qt.WindowType.WindowContextHelpButtonHint)
        self.setStyleSheet("""
            QDialog {
                background-color: #0b0e14;
                color: #c9d1d9;
            }
        """)

        self.worker: Optional[SuiteUpdaterWorker] = None
        self._build_ui()

        # Auto-trigger update on show after brief delay
        QTimer.singleShot(250, self._start_update)

    def _build_ui(self):
        layout = QVBoxLayout(self)
        layout.setContentsMargins(18, 16, 18, 16)
        layout.setSpacing(12)

        # Header Frame
        hdr_frame = QFrame()
        hdr_frame.setStyleSheet("""
            QFrame {
                background-color: #161b22;
                border: 1px solid #30363d;
                border-radius: 8px;
                padding: 10px;
            }
        """)
        h_layout = QHBoxLayout(hdr_frame)
        h_layout.setContentsMargins(8, 6, 8, 6)
        h_layout.setSpacing(12)

        icon_lbl = QLabel()
        pm = get_suite_pixmap("beatbar-main", size=32, dark_mode=True)
        if pm and not pm.isNull():
            icon_lbl.setPixmap(pm)
        else:
            ico = get_feather_icon("git-pull-request", "#58a6ff", 28)
            if ico and not ico.isNull():
                icon_lbl.setPixmap(ico.pixmap(28, 28))
        h_layout.addWidget(icon_lbl)

        txt_layout = QVBoxLayout()
        txt_layout.setSpacing(2)
        title_lbl = QLabel("Automated One-Click Suite Updater")
        title_lbl.setStyleSheet("font-size: 15px; font-weight: bold; color: #ffffff;")
        txt_layout.addWidget(title_lbl)

        sub_lbl = QLabel("Git repository sync & automatic recompilation of dirty components")
        sub_lbl.setStyleSheet("font-size: 11px; color: #8b949e;")
        txt_layout.addWidget(sub_lbl)
        h_layout.addLayout(txt_layout)
        h_layout.addStretch()
        layout.addWidget(hdr_frame)

        # Status & Progress Frame
        status_frame = QFrame()
        status_frame.setStyleSheet("""
            QFrame {
                background-color: #161b22;
                border: 1px solid #21262d;
                border-radius: 6px;
                padding: 6px;
            }
        """)
        sf_layout = QVBoxLayout(status_frame)
        sf_layout.setContentsMargins(8, 8, 8, 8)
        sf_layout.setSpacing(6)

        self.status_lbl = QLabel("Initializing updater...")
        self.status_lbl.setStyleSheet("font-size: 11.5px; font-weight: bold; color: #58a6ff;")
        sf_layout.addWidget(self.status_lbl)

        self.progress_bar = QProgressBar()
        self.progress_bar.setFixedHeight(12)
        self.progress_bar.setRange(0, 100)
        self.progress_bar.setValue(0)
        self.progress_bar.setTextVisible(False)
        self.progress_bar.setStyleSheet("""
            QProgressBar {
                background-color: #0d1117;
                border: 1px solid #30363d;
                border-radius: 6px;
            }
            QProgressBar::chunk {
                background: qlineargradient(x1:0, y1:0, x2:1, y2:0, stop:0 #1f6feb, stop:1 #238636);
                border-radius: 5px;
            }
        """)
        sf_layout.addWidget(self.progress_bar)
        layout.addWidget(status_frame)

        # Live Log Terminal
        self.log_view = QTextEdit()
        self.log_view.setReadOnly(True)
        self.log_view.setFont(QFont("Consolas", 9))
        self.log_view.setStyleSheet("""
            QTextEdit {
                background-color: #0d1117;
                color: #58a6ff;
                border: 1px solid #30363d;
                border-radius: 6px;
                padding: 8px;
            }
        """)
        layout.addWidget(self.log_view)

        # Bottom Action Bar
        btn_layout = QHBoxLayout()
        btn_layout.setSpacing(10)

        self.btn_run_again = QPushButton("Start Sync & Update")
        self.btn_run_again.setFixedHeight(30)
        self.btn_run_again.setCursor(QCursor(Qt.CursorShape.PointingHandCursor))
        self.btn_run_again.setStyleSheet("""
            QPushButton {
                background-color: #238636;
                color: #ffffff;
                border: none;
                border-radius: 4px;
                padding: 0 16px;
                font-weight: bold;
                font-size: 11.5px;
            }
            QPushButton:hover { background-color: #2ea043; }
            QPushButton:disabled { background-color: #21262d; color: #484f58; }
        """)
        self.btn_run_again.clicked.connect(self._start_update)
        btn_layout.addWidget(self.btn_run_again)

        btn_layout.addStretch()

        self.btn_cancel = QPushButton("Cancel")
        self.btn_cancel.setFixedHeight(30)
        self.btn_cancel.setCursor(QCursor(Qt.CursorShape.PointingHandCursor))
        self.btn_cancel.setStyleSheet("""
            QPushButton {
                background-color: #21262d;
                color: #f85149;
                border: 1px solid #30363d;
                border-radius: 4px;
                padding: 0 14px;
                font-size: 11px;
            }
            QPushButton:hover { background-color: #30363d; }
            QPushButton:disabled { color: #484f58; }
        """)
        self.btn_cancel.clicked.connect(self._cancel_update)
        btn_layout.addWidget(self.btn_cancel)

        self.btn_close = QPushButton("Close")
        self.btn_close.setFixedHeight(30)
        self.btn_close.setCursor(QCursor(Qt.CursorShape.PointingHandCursor))
        self.btn_close.setStyleSheet("""
            QPushButton {
                background-color: #21262d;
                color: #c9d1d9;
                border: 1px solid #30363d;
                border-radius: 4px;
                padding: 0 16px;
                font-size: 11px;
            }
            QPushButton:hover { background-color: #30363d; color: #ffffff; }
        """)
        self.btn_close.clicked.connect(self.accept)
        btn_layout.addWidget(self.btn_close)

        layout.addLayout(btn_layout)

    def _start_update(self):
        if self.worker and self.worker.isRunning():
            return

        self.btn_run_again.setEnabled(False)
        self.btn_cancel.setEnabled(True)
        self.btn_close.setEnabled(False)
        self.log_view.clear()
        self.progress_bar.setValue(0)
        self.status_lbl.setText("Starting automated suite update...")
        self.status_lbl.setStyleSheet("font-size: 11.5px; font-weight: bold; color: #58a6ff;")

        self.worker = SuiteUpdaterWorker(self)
        self.worker.log_signal.connect(self._append_log)
        self.worker.status_signal.connect(self._update_status)
        self.worker.finished_signal.connect(self._on_finished)
        self.worker.start()

    def _cancel_update(self):
        if self.worker and self.worker.isRunning():
            self.status_lbl.setText("Cancelling update...")
            self.status_lbl.setStyleSheet("color: #f85149; font-size: 11.5px;")
            self.worker.cancel()

    def _append_log(self, text: str):
        self.log_view.append(text)
        sb = self.log_view.verticalScrollBar()
        if sb:
            sb.setValue(sb.maximum())

    def _update_status(self, msg: str, percent: int):
        self.status_lbl.setText(msg)
        self.progress_bar.setValue(percent)

    def _on_finished(self, success: bool, msg: str, recompiled: list):
        self.btn_run_again.setEnabled(True)
        self.btn_cancel.setEnabled(False)
        self.btn_close.setEnabled(True)

        if success:
            self.status_lbl.setText(msg)
            self.status_lbl.setStyleSheet("font-size: 11.5px; font-weight: bold; color: #3fb950;")
            self.suite_updated.emit()
        else:
            self.status_lbl.setText(f"Update failed: {msg}")
            self.status_lbl.setStyleSheet("font-size: 11.5px; font-weight: bold; color: #f85149;")

    def closeEvent(self, event):
        if self.worker and self.worker.isRunning():
            self.worker.cancel()
            self.worker.wait(500)
        super().closeEvent(event)

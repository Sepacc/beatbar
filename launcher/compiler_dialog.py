"""
compiler_dialog.py - Interactive compilation dialog for Beatbar Suite programs.

Allows selecting programs to compile, manages PyInstaller installation,
streams build logs in real time, and ensures old versions are cleaned up.
Compact layout optimized for 1366x768 screens with Feather SVG icons.
"""

import os
import sys
import subprocess
from typing import List, Optional

from PyQt6.QtCore import Qt, pyqtSignal, QThread, QSize
from PyQt6.QtWidgets import (
    QDialog, QVBoxLayout, QHBoxLayout, QLabel, QPushButton,
    QCheckBox, QProgressBar, QTextEdit, QFrame, QGroupBox,
    QMessageBox
)
from PyQt6.QtGui import QFont, QCursor

from launcher.version_manager import (
    PROGRAM_REGISTRY, COMPILED_DIR,
    read_source_version, compare_program_version
)
from launcher.compiler import (
    is_pyinstaller_installed, CompilationWorker
)

try:
    from icon_utils import get_feather_icon
except ImportError:
    get_feather_icon = lambda name, color="#ffffff", size=16: None


class PipInstallWorker(QThread):
    log_signal = pyqtSignal(str)
    finished_signal = pyqtSignal(bool, str)

    def run(self):
        self.log_signal.emit("[Pip] Starting installation of PyInstaller...")
        cmd = [sys.executable, "-m", "pip", "install", "pyinstaller"]
        try:
            proc = subprocess.Popen(
                cmd,
                stdout=subprocess.PIPE,
                stderr=subprocess.STDOUT,
                text=True,
                bufsize=1,
                universal_newlines=True
            )
            for line in iter(proc.stdout.readline, ""):
                l_str = line.strip()
                if l_str:
                    self.log_signal.emit(f"[Pip] {l_str}")
            proc.stdout.close()
            code = proc.wait()
            if code == 0:
                self.log_signal.emit("[Pip] PyInstaller installed successfully!")
                self.finished_signal.emit(True, "Success")
            else:
                self.log_signal.emit(f"[Pip Error] Installation exited with code {code}")
                self.finished_signal.emit(False, f"Exited with code {code}")
        except Exception as e:
            self.log_signal.emit(f"[Pip Error] {e}")
            self.finished_signal.emit(False, str(e))


class CompilerDialog(QDialog):
    compilation_completed = pyqtSignal()

    def __init__(self, target_prog_id: Optional[str] = None, parent=None):
        super().__init__(parent)
        self.target_prog_id = target_prog_id
        self.worker: Optional[CompilationWorker] = None
        self.pip_worker: Optional[PipInstallWorker] = None
        self.checkboxes = {}

        self.setWindowTitle("Compile Programs - BeatBar Suite")
        try:
            from icon_utils import get_suite_icon
            s_ico = get_suite_icon("beatbar-main", size=32)
            if s_ico and not s_ico.isNull():
                self.setWindowIcon(s_ico)
        except Exception:
            pass
        # Compact dimensions for 1366x768 screens
        self.resize(580, 430)
        self.setMinimumSize(500, 370)
        self.setStyleSheet("""
            QDialog {
                background-color: #0d1117;
                color: #c9d1d9;
            }
            QLabel {
                color: #c9d1d9;
            }
            QGroupBox {
                border: 1px solid #30363d;
                border-radius: 6px;
                margin-top: 8px;
                padding-top: 10px;
                font-size: 11px;
                font-weight: bold;
                color: #58a6ff;
            }
            QGroupBox::title {
                subcontrol-origin: margin;
                left: 10px;
                padding: 0 4px;
            }
            QCheckBox {
                color: #e6edf3;
                spacing: 6px;
                font-size: 11px;
            }
            QCheckBox::indicator {
                width: 15px;
                height: 15px;
                border: 1px solid #30363d;
                border-radius: 3px;
                background-color: #161b22;
            }
            QCheckBox::indicator:checked {
                background-color: #238636;
                border-color: #2ea043;
            }
            QProgressBar {
                border: 1px solid #30363d;
                border-radius: 3px;
                background-color: #161b22;
                text-align: center;
                color: #ffffff;
                font-size: 10px;
                font-weight: bold;
            }
            QProgressBar::chunk {
                background-color: #238636;
                border-radius: 2px;
            }
            QTextEdit {
                background-color: #0b0e14;
                border: 1px solid #21262d;
                border-radius: 4px;
                color: #8b949e;
                font-family: 'Consolas', 'Courier New', monospace;
                font-size: 10px;
                padding: 4px;
            }
        """)

        self._build_ui()
        self._check_pyinstaller_status()

    def _build_ui(self):
        layout = QVBoxLayout(self)
        layout.setSpacing(8)
        layout.setContentsMargins(14, 12, 14, 12)

        # Header
        header_layout = QHBoxLayout()
        header_text = QVBoxLayout()
        header_text.setSpacing(1)

        title = QLabel("Compile Executables")
        title.setStyleSheet("font-size: 14px; font-weight: bold; color: #ffffff;")
        header_text.addWidget(title)

        subtitle = QLabel("Package desktop programs into standalone Windows binaries stored in /launcher/compiled/")
        subtitle.setStyleSheet("font-size: 10px; color: #8b949e;")
        header_text.addWidget(subtitle)
        header_layout.addLayout(header_text)
        layout.addLayout(header_layout)

        # PyInstaller banner (if missing)
        self.pyinstaller_banner = QFrame()
        self.pyinstaller_banner.setStyleSheet("""
            QFrame {
                background-color: #2c1a06;
                border: 1px solid #9e6a03;
                border-radius: 5px;
                padding: 4px 8px;
            }
        """)
        banner_layout = QHBoxLayout(self.pyinstaller_banner)
        banner_layout.setContentsMargins(4, 2, 4, 2)
        banner_layout.setSpacing(8)

        self.banner_icon = QLabel()
        warn_ico = get_feather_icon("alert-triangle", color="#d29922", size=14)
        if warn_ico and not warn_ico.isNull():
            self.banner_icon.setPixmap(warn_ico.pixmap(14, 14))
        banner_layout.addWidget(self.banner_icon)

        self.banner_label = QLabel("PyInstaller is not detected in your Python environment.")
        self.banner_label.setStyleSheet("color: #d29922; font-size: 11px; font-weight: bold;")
        banner_layout.addWidget(self.banner_label)

        banner_layout.addStretch()

        self.btn_install_pyinstaller = QPushButton("Install PyInstaller")
        self.btn_install_pyinstaller.setCursor(QCursor(Qt.CursorShape.PointingHandCursor))
        dl_ico = get_feather_icon("download", color="#ffffff", size=12)
        if dl_ico and not dl_ico.isNull():
            self.btn_install_pyinstaller.setIcon(dl_ico)
            self.btn_install_pyinstaller.setIconSize(QSize(12, 12))
        self.btn_install_pyinstaller.setStyleSheet("""
            QPushButton {
                background-color: #b08800;
                color: #ffffff;
                border: none;
                border-radius: 4px;
                padding: 4px 10px;
                font-weight: bold;
                font-size: 10.5px;
            }
            QPushButton:hover { background-color: #d29922; }
        """)
        self.btn_install_pyinstaller.clicked.connect(self._install_pyinstaller)
        banner_layout.addWidget(self.btn_install_pyinstaller)
        self.pyinstaller_banner.setVisible(False)
        layout.addWidget(self.pyinstaller_banner)

        # Program Selection Group
        prog_group = QGroupBox("Select Programs to Compile")
        prog_layout = QVBoxLayout(prog_group)
        prog_layout.setSpacing(6)
        prog_layout.setContentsMargins(10, 8, 10, 8)

        for pid, prog in PROGRAM_REGISTRY.items():
            if prog.is_web or not prog.can_compile:
                continue

            comp = compare_program_version(prog)
            cb = QCheckBox(f"{prog.name} (Source: v{comp.source_version})  ->  {prog.target_exe_name}")

            if self.target_prog_id:
                cb.setChecked(pid == self.target_prog_id)
            else:
                cb.setChecked(True)

            self.checkboxes[pid] = cb
            prog_layout.addWidget(cb)

        # Web note
        web_prog = PROGRAM_REGISTRY.get("beatbar_web")
        if web_prog:
            web_note = QLabel(f"• {web_prog.name} (v{read_source_version(web_prog)}): Dynamic web service — runs natively via Python (no compilation needed).")
            web_note.setStyleSheet("color: #2ed573; font-size: 10.5px; font-style: italic; margin-top: 2px;")
            prog_layout.addWidget(web_note)

        layout.addWidget(prog_group)

        # Clean option
        self.cb_clean = QCheckBox("Remove previous versions from /launcher/compiled/ before new compile")
        self.cb_clean.setChecked(True)
        self.cb_clean.setStyleSheet("font-size: 11px;")
        layout.addWidget(self.cb_clean)

        # Progress bar & status
        self.status_label = QLabel("Ready to compile.")
        self.status_label.setStyleSheet("color: #8b949e; font-size: 11px;")
        layout.addWidget(self.status_label)

        self.progress_bar = QProgressBar()
        self.progress_bar.setValue(0)
        self.progress_bar.setFixedHeight(8)
        layout.addWidget(self.progress_bar)

        # Compilation log
        self.log_view = QTextEdit()
        self.log_view.setReadOnly(True)
        self.log_view.setPlaceholderText("PyInstaller build output will stream here...")
        layout.addWidget(self.log_view)

        # Action Buttons
        btn_layout = QHBoxLayout()
        btn_layout.setSpacing(8)

        self.btn_compile = QPushButton("Start Compilation")
        self.btn_compile.setCursor(QCursor(Qt.CursorShape.PointingHandCursor))
        pkg_ico = get_feather_icon("package", color="#ffffff", size=13)
        if pkg_ico and not pkg_ico.isNull():
            self.btn_compile.setIcon(pkg_ico)
            self.btn_compile.setIconSize(QSize(13, 13))
        self.btn_compile.setStyleSheet("""
            QPushButton {
                background-color: #238636;
                color: #ffffff;
                border: none;
                border-radius: 5px;
                padding: 6px 14px;
                font-weight: bold;
                font-size: 11.5px;
            }
            QPushButton:hover { background-color: #2ea043; }
            QPushButton:disabled { background-color: #21262d; color: #484f58; }
        """)
        self.btn_compile.clicked.connect(self._start_compilation)
        btn_layout.addWidget(self.btn_compile)

        self.btn_cancel = QPushButton("Cancel")
        self.btn_cancel.setCursor(QCursor(Qt.CursorShape.PointingHandCursor))
        cancel_ico = get_feather_icon("x", color="#ffffff", size=13)
        if cancel_ico and not cancel_ico.isNull():
            self.btn_cancel.setIcon(cancel_ico)
            self.btn_cancel.setIconSize(QSize(13, 13))
        self.btn_cancel.setStyleSheet("""
            QPushButton {
                background-color: #da3633;
                color: #ffffff;
                border: none;
                border-radius: 5px;
                padding: 6px 14px;
                font-weight: bold;
                font-size: 11.5px;
            }
            QPushButton:hover { background-color: #f85149; }
        """)
        self.btn_cancel.setEnabled(False)
        self.btn_cancel.clicked.connect(self._cancel_compilation)
        btn_layout.addWidget(self.btn_cancel)

        btn_layout.addStretch()

        self.btn_close = QPushButton("Close")
        self.btn_close.setCursor(QCursor(Qt.CursorShape.PointingHandCursor))
        self.btn_close.setStyleSheet("""
            QPushButton {
                background-color: #21262d;
                color: #c9d1d9;
                border: 1px solid #30363d;
                border-radius: 5px;
                padding: 6px 14px;
                font-size: 11.5px;
            }
            QPushButton:hover { background-color: #30363d; }
        """)
        self.btn_close.clicked.connect(self.accept)
        btn_layout.addWidget(self.btn_close)

        layout.addLayout(btn_layout)

    def _check_pyinstaller_status(self):
        installed = is_pyinstaller_installed()
        self.pyinstaller_banner.setVisible(not installed)
        if not installed:
            self.status_label.setText("Notice: PyInstaller is required to compile standalone executables.")
            self.status_label.setStyleSheet("color: #d29922; font-size: 11px;")

    def _install_pyinstaller(self):
        self.btn_install_pyinstaller.setEnabled(False)
        self.log_view.append("[Action] Installing PyInstaller via pip...")
        self.pip_worker = PipInstallWorker(self)
        self.pip_worker.log_signal.connect(self._append_log)
        self.pip_worker.finished_signal.connect(self._on_pip_finished)
        self.pip_worker.start()

    def _on_pip_finished(self, success: bool, msg: str):
        self.btn_install_pyinstaller.setEnabled(True)
        self._check_pyinstaller_status()
        if success:
            QMessageBox.information(self, "Success", "PyInstaller installed successfully!")
        else:
            QMessageBox.warning(self, "Failed", f"Failed to install PyInstaller:\n{msg}")

    def _start_compilation(self):
        selected_ids = [pid for pid, cb in self.checkboxes.items() if cb.isChecked()]
        if not selected_ids:
            QMessageBox.information(self, "Select Program", "Please select at least one program to compile.")
            return

        if not is_pyinstaller_installed():
            reply = QMessageBox.question(
                self,
                "PyInstaller Not Found",
                "PyInstaller is not detected in your Python environment.\nWould you like to install it now via pip?",
                QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No
            )
            if reply == QMessageBox.StandardButton.Yes:
                self._install_pyinstaller()
            return

        self.btn_compile.setEnabled(False)
        self.btn_cancel.setEnabled(True)
        self.btn_close.setEnabled(False)
        self.log_view.clear()
        self.progress_bar.setValue(0)
        self.status_label.setText("Starting compilation...")
        self.status_label.setStyleSheet("color: #58a6ff; font-size: 11px;")

        self.worker = CompilationWorker(selected_ids, self)
        self.worker.log_signal.connect(self._append_log)
        self.worker.status_signal.connect(self._update_status)
        self.worker.prog_finished.connect(self._on_prog_finished)
        self.worker.all_finished.connect(self._on_all_finished)
        self.worker.start()

    def _cancel_compilation(self):
        if self.worker:
            self.worker.cancel()
            self.btn_cancel.setEnabled(False)
            self.status_label.setText("Cancelling compilation...")

    def _append_log(self, text: str):
        self.log_view.append(text)
        sb = self.log_view.verticalScrollBar()
        if sb:
            sb.setValue(sb.maximum())

    def _update_status(self, msg: str, percent: int):
        self.status_label.setText(msg)
        self.progress_bar.setValue(percent)

    def _on_prog_finished(self, prog_id: str, success: bool, msg: str):
        prog = PROGRAM_REGISTRY.get(prog_id)
        name = prog.name if prog else prog_id
        if success:
            self.log_view.append(f"Finished {name}: {msg}")
        else:
            self.log_view.append(f"Failed {name}: {msg}")

    def _on_all_finished(self):
        self.btn_compile.setEnabled(True)
        self.btn_cancel.setEnabled(False)
        self.btn_close.setEnabled(True)
        self.progress_bar.setValue(100)
        self.status_label.setText("Compilation completed.")
        self.status_label.setStyleSheet("color: #2ea043; font-size: 11px; font-weight: bold;")
        self.compilation_completed.emit()

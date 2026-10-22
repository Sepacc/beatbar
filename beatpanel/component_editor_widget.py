"""
component_editor_widget.py - Dedicated Editor View for Individual Beatbar Components.

Provides:
- Isolated high-res component preview
- Template selector dropdown
- File Import/Export and Clipboard actions
- Mirror wing symmetry action
- Automatic SVG color extraction with interactive palette swatches
- Direct SVG XML source editor with live validation and error reporting.
"""

from PyQt6.QtCore import Qt, pyqtSignal, QTimer, QEvent
from PyQt6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QLabel, QPushButton, QComboBox,
    QPlainTextEdit, QFileDialog, QColorDialog, QFrame, QScrollArea,
    QSplitter, QMessageBox, QApplication, QSlider, QCheckBox
)
from PyQt6.QtGui import QColor, QFont, QKeySequence, QShortcut

from beatpanel.component_preview import ComponentPreviewWidget
from beatpanel.templates import get_template_library
from beatpanel.svg_utils import (
    extract_colors, replace_color, validate_svg, format_svg, mirror_svg_horizontally
)
try:
    from icon_utils import get_feather_icon
except (ImportError, ValueError):
    import os, sys
    _p = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    for _d in [_p, os.path.join(_p, "main")]:
        if _d not in sys.path:
            sys.path.insert(0, _d)
    from icon_utils import get_feather_icon


class ColorSwatchButton(QPushButton):
    """Clickable color swatch with hex label."""
    color_clicked = pyqtSignal(str)

    def __init__(self, hex_color: str, parent=None):
        super().__init__(parent)
        self.hex_color = hex_color.lower()
        self.setText(self.hex_color.upper())
        self.setFixedHeight(30)
        self.setCursor(Qt.CursorShape.PointingHandCursor)
        self._update_style()
        self.clicked.connect(lambda: self.color_clicked.emit(self.hex_color))

    def _update_style(self):
        # Choose text color (black or white) based on brightness
        c = QColor(self.hex_color)
        lum = 0.299 * c.red() + 0.587 * c.green() + 0.114 * c.blue()
        text_col = "#000000" if lum > 130 else "#ffffff"

        self.setStyleSheet(f"""
            QPushButton {{
                background-color: {self.hex_color};
                color: {text_col};
                border: 1px solid #444458;
                border-radius: 6px;
                font-family: monospace;
                font-size: 11px;
                font-weight: bold;
                padding: 4px 8px;
            }}
            QPushButton:hover {{
                border: 2px solid #ffffff;
            }}
        """)


class ComponentEditorWidget(QWidget):
    """
    Editor tab for a single Beatbar SVG component.
    """
    svg_modified = pyqtSignal(str, str)  # component_key, new_svg_content
    request_mirror_to_opposite = pyqtSignal(str, str)  # target_component_key, mirrored_svg
    layout_modified = pyqtSignal(str, dict)  # component_key, layout_dict
    beat_flip_modified = pyqtSignal(bool, bool)  # flip_left, flip_right
    trigger_hit_modified = pyqtSignal(dict)  # trigger_hit_dict

    def __init__(self, component_key: str, parent=None):
        super().__init__(parent)
        self.component_key = component_key
        self.current_svg = ""
        self.current_ind_color = "#ffffff"
        self._suppress_events = False
        # Undo / Redo history stacks
        self._undo_stack = []
        self._redo_stack = []
        self._max_history = 50

        # Debounce timer for live source typing
        self.typing_timer = QTimer(self)
        self.typing_timer.setSingleShot(True)
        self.typing_timer.setInterval(400)
        self.typing_timer.timeout.connect(self._on_typing_timeout)

        self._build_ui()

    def _build_ui(self):
        layout = QHBoxLayout(self)
        layout.setContentsMargins(8, 8, 8, 8)
        layout.setSpacing(12)

        splitter = QSplitter(Qt.Orientation.Horizontal, self)

        # ----------------------------------------------------------------------
        # LEFT COLUMN: Isolated Preview & Template / File Actions
        # ----------------------------------------------------------------------
        left_widget = QWidget(self)
        left_layout = QVBoxLayout(left_widget)
        left_layout.setContentsMargins(0, 0, 0, 0)
        left_layout.setSpacing(8)

        # Isolated Preview
        self.preview_box = ComponentPreviewWidget(self)
        left_layout.addWidget(self.preview_box, stretch=1)

        # Template Selector
        tpl_layout = QHBoxLayout()
        tpl_layout.addWidget(QLabel("Template:"))
        self.combo_tpl = QComboBox()
        self._populate_templates()
        self.combo_tpl.currentIndexChanged.connect(self._on_template_selected)
        tpl_layout.addWidget(self.combo_tpl, stretch=1)
        left_layout.addLayout(tpl_layout)

        # Action Buttons Row
        actions_row = QHBoxLayout()
        actions_row.setSpacing(6)

        self.btn_import = QPushButton(" Import SVG")
        self.btn_import.setIcon(get_feather_icon("folder", "#00d2ff", 14))
        self.btn_import.clicked.connect(self._import_svg_file)
        actions_row.addWidget(self.btn_import)

        self.btn_export = QPushButton(" Export SVG")
        self.btn_export.setIcon(get_feather_icon("download", "#00d2ff", 14))
        self.btn_export.clicked.connect(self._export_svg_file)
        actions_row.addWidget(self.btn_export)

        left_layout.addLayout(actions_row)

        # Wing Mirroring Action (for wing_left and wing_right)
        if self.component_key in ("wing_left", "wing_right"):
            target_key = "wing_right" if self.component_key == "wing_left" else "wing_left"
            target_name = "Right Wing" if self.component_key == "wing_left" else "Left Wing"
            self.btn_mirror = QPushButton(f" Mirror to {target_name}")
            self.btn_mirror.setIcon(get_feather_icon("repeat", "#e0b0ff", 14))
            self.btn_mirror.setStyleSheet("""
                QPushButton {
                    background: #281a38;
                    border: 1px solid #7d449e;
                    color: #e0b0ff;
                    font-weight: bold;
                    border-radius: 6px;
                    padding: 5px;
                }
                QPushButton:hover {
                    background: #3c2456;
                    border-color: #be2edd;
                }
            """)
            self.btn_mirror.clicked.connect(lambda: self._mirror_to_opposite(target_key))
            left_layout.addWidget(self.btn_mirror)

        # Context-sensitive layout / flip / trigger hit controls
        if self.component_key in ("wing_left", "wing_right", "target"):
            self._build_geometry_controls(left_layout)
        elif self.component_key == "beat":
            self._build_beat_flip_controls(left_layout)
        elif self.component_key == "target_hit":
            self._build_trigger_hit_controls(left_layout)

        left_scroll = QScrollArea()
        left_scroll.setWidgetResizable(True)
        left_scroll.setFrameShape(QFrame.Shape.NoFrame)
        left_scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        left_scroll.setStyleSheet("background: transparent;")
        left_scroll.setWidget(left_widget)
        left_scroll.setMinimumWidth(250)
        splitter.addWidget(left_scroll)

        # ----------------------------------------------------------------------
        # RIGHT COLUMN: Detected Color Swatches & SVG XML Code Editor
        # ----------------------------------------------------------------------
        right_widget = QWidget(self)
        right_layout = QVBoxLayout(right_widget)
        right_layout.setContentsMargins(0, 0, 0, 0)
        right_layout.setSpacing(6)

        # Color Swatches Box
        swatch_group = QFrame(self)
        swatch_group.setStyleSheet("""
            QFrame {
                background: #15151e;
                border: none;
                border-radius: 8px;
            }
        """)
        sg_layout = QVBoxLayout(swatch_group)
        sg_layout.setContentsMargins(8, 4, 8, 4)
        sg_layout.setSpacing(4)

        swatch_header = QHBoxLayout()
        swatch_header.addWidget(QLabel("Detected Colors in SVG (Click to Replace):"))
        swatch_header.addStretch(1)
        sg_layout.addLayout(swatch_header)

        self.swatches_layout = QHBoxLayout()
        self.swatches_layout.setSpacing(6)
        self.swatches_container = QWidget()
        self.swatches_container.setLayout(self.swatches_layout)

        scroll_swatches = QScrollArea()
        scroll_swatches.setWidgetResizable(True)
        scroll_swatches.setFixedHeight(42)
        scroll_swatches.setFrameShape(QFrame.Shape.NoFrame)
        scroll_swatches.setStyleSheet("background: transparent;")
        scroll_swatches.setWidget(self.swatches_container)
        sg_layout.addWidget(scroll_swatches)

        right_layout.addWidget(swatch_group)

        # SVG XML Code Editor
        editor_frame = QFrame(self)
        editor_frame.setStyleSheet("""
            QFrame {
                background: #14141d;
                border: none;
                border-radius: 8px;
            }
        """)
        ef_layout = QVBoxLayout(editor_frame)
        ef_layout.setContentsMargins(8, 6, 8, 6)
        ef_layout.setSpacing(6)

        # Editor Header
        ed_header = QHBoxLayout()
        ed_header.addWidget(QLabel("SVG Source XML:"))
        self.lbl_valid = QLabel("Valid SVG")
        self.lbl_valid.setStyleSheet("color: #2ed573; font-size: 11px; font-weight: bold;")
        ed_header.addWidget(self.lbl_valid)
        ed_header.addStretch(1)

        btn_format = QPushButton("Prettify")
        btn_format.setFixedWidth(70)
        btn_format.clicked.connect(self._format_code)
        ed_header.addWidget(btn_format)

        btn_apply = QPushButton("Apply")
        btn_apply.setFixedWidth(70)
        btn_apply.setStyleSheet("background: #9b51e0; color: #ffffff; font-weight: bold;")
        btn_apply.clicked.connect(self._apply_code)
        ed_header.addWidget(btn_apply)

        self.btn_undo = QPushButton("Undo")
        self.btn_undo.setFixedWidth(60)
        self.btn_undo.setToolTip("Undo SVG changes (Ctrl+Z)")
        self.btn_undo.setEnabled(False)
        self.btn_undo.clicked.connect(self.undo)
        ed_header.addWidget(self.btn_undo)

        self.btn_redo = QPushButton("Redo")
        self.btn_redo.setFixedWidth(60)
        self.btn_redo.setToolTip("Redo SVG changes (Ctrl+Y / Ctrl+Shift+Z)")
        self.btn_redo.setEnabled(False)
        self.btn_redo.clicked.connect(self.redo)
        ed_header.addWidget(self.btn_redo)

        ef_layout.addLayout(ed_header)

        # Code Editor Text Box
        self.code_edit = QPlainTextEdit(self)
        self.code_edit.setFont(QFont("Consolas", 10))
        self.code_edit.setLineWrapMode(QPlainTextEdit.LineWrapMode.NoWrap)
        self.code_edit.setStyleSheet("""
            QPlainTextEdit {
                background: #0f0f15;
                color: #e0e0ec;
                border: 1px solid #242432;
                border-radius: 6px;
                padding: 6px;
                font-family: 'Consolas', monospace;
            }
        """)
        self.code_edit.textChanged.connect(self._on_code_text_changed)
        self.code_edit.installEventFilter(self)
        QShortcut(QKeySequence.StandardKey.Undo, self, self.undo)
        QShortcut(QKeySequence.StandardKey.Redo, self, self.redo)
        QShortcut(QKeySequence("Ctrl+Shift+Z"), self, self.redo)
        ef_layout.addWidget(self.code_edit, stretch=1)

        right_layout.addWidget(editor_frame, stretch=1)

        splitter.addWidget(right_widget)
        splitter.setStretchFactor(0, 1)
        splitter.setStretchFactor(1, 2)
        splitter.setSizes([220, 600])

        layout.addWidget(splitter)

    def _populate_templates(self):
        """Populates template dropdown from template library."""
        tpl_lib = get_template_library()
        options = tpl_lib.get(self.component_key, {})
        self.combo_tpl.clear()
        for name, svg in options.items():
            self.combo_tpl.addItem(name, svg)

    def _push_undo_state(self, svg: str):
        """Pushes an SVG state onto the undo stack and clears redo stack."""
        if not svg or not svg.strip():
            return
        if self._undo_stack and self._undo_stack[-1] == svg:
            return
        self._undo_stack.append(svg)
        if len(self._undo_stack) > self._max_history:
            self._undo_stack.pop(0)
        self._redo_stack.clear()
        self._update_undo_redo_buttons()

    def _update_undo_redo_buttons(self):
        """Updates the enabled state of the Undo and Redo toolbar buttons."""
        if hasattr(self, 'btn_undo'):
            self.btn_undo.setEnabled(len(self._undo_stack) > 0)
        if hasattr(self, 'btn_redo'):
            self.btn_redo.setEnabled(len(self._redo_stack) > 0)

    def undo(self):
        """Restores previous SVG state from undo stack."""
        if not self._undo_stack:
            return
        cur_text = self.code_edit.toPlainText().strip() or self.current_svg
        self._redo_stack.append(cur_text)
        prev_svg = self._undo_stack.pop()
        self._apply_history_svg(prev_svg)
        self._update_undo_redo_buttons()

    def redo(self):
        """Restores next SVG state from redo stack."""
        if not self._redo_stack:
            return
        cur_text = self.code_edit.toPlainText().strip() or self.current_svg
        self._undo_stack.append(cur_text)
        next_svg = self._redo_stack.pop()
        self._apply_history_svg(next_svg)
        self._update_undo_redo_buttons()

    def _apply_history_svg(self, svg_content: str):
        """Applies an SVG snapshot without clearing undo/redo stacks."""
        self.current_svg = svg_content
        self.preview_box.set_svg_content(svg_content)
        self._suppress_events = True
        self.code_edit.setPlainText(svg_content)
        self._suppress_events = False
        self._refresh_swatches()
        self._validate_syntax(svg_content)
        self.svg_modified.emit(self.component_key, svg_content)

    def eventFilter(self, obj, event):
        """Handles Undo/Redo key events inside code_edit when local buffer is exhausted."""
        if obj == self.code_edit and event.type() == QEvent.Type.KeyPress:
            if event.matches(QKeySequence.StandardKey.Undo):
                if not self.code_edit.document().isUndoAvailable() and self._undo_stack:
                    self.undo()
                    return True
            elif event.matches(QKeySequence.StandardKey.Redo) or (
                event.modifiers() == (Qt.KeyboardModifier.ControlModifier | Qt.KeyboardModifier.ShiftModifier)
                and event.key() == Qt.Key.Key_Z
            ):
                if not self.code_edit.document().isRedoAvailable() and self._redo_stack:
                    self.redo()
                    return True
        return super().eventFilter(obj, event)

    def set_svg_content(self, svg_content: str, push_undo: bool = True):
        """Updates editor with given SVG content."""
        if push_undo and self.current_svg and self.current_svg != svg_content:
            self._push_undo_state(self.current_svg)

        self.current_svg = svg_content
        self.preview_box.set_svg_content(svg_content)

        self._suppress_events = True
        self.code_edit.setPlainText(svg_content)
        self._suppress_events = False

        self._refresh_swatches()
        self._validate_syntax(svg_content)

    def _refresh_swatches(self):
        """Rebuilds color swatches from current SVG."""
        # Clear existing
        while self.swatches_layout.count():
            item = self.swatches_layout.takeAt(0)
            if item.widget():
                item.widget().deleteLater()

        colors = extract_colors(self.current_svg)
        if not colors:
            lbl = QLabel("No hex colors detected in this SVG.")
            lbl.setStyleSheet("color: #707080; font-size: 11px;")
            self.swatches_layout.addWidget(lbl)
        else:
            for c in colors:
                btn = ColorSwatchButton(c, self)
                btn.color_clicked.connect(self._on_swatch_clicked)
                self.swatches_layout.addWidget(btn)

        self.swatches_layout.addStretch(1)

    def _on_swatch_clicked(self, old_color: str):
        """Opens QColorDialog to replace the selected color."""
        new_qcol = QColorDialog.getColor(QColor(old_color), self, f"Replace Color {old_color.upper()}")
        if new_qcol.isValid():
            new_hex = new_qcol.name()
            updated_svg = replace_color(self.current_svg, old_color, new_hex)
            self.set_svg_content(updated_svg, push_undo=True)
            self.svg_modified.emit(self.component_key, updated_svg)

    def _on_template_selected(self, index: int):
        if self._suppress_events or index < 0:
            return
        tpl_svg = self.combo_tpl.currentData()
        if tpl_svg:
            self.set_svg_content(tpl_svg, push_undo=True)
            self.svg_modified.emit(self.component_key, tpl_svg)

    def _on_code_text_changed(self):
        if self._suppress_events:
            return
        self.typing_timer.start()

    def _on_typing_timeout(self):
        text = self.code_edit.toPlainText()
        is_valid, err = validate_svg(text)
        if is_valid:
            self.lbl_valid.setText("Valid SVG")
            self.lbl_valid.setStyleSheet("color: #2ed573; font-size: 11px; font-weight: bold;")
            if self.current_svg and self.current_svg != text:
                self._push_undo_state(self.current_svg)
            self.current_svg = text
            self.preview_box.set_svg_content(text)
            self._refresh_swatches()
            self.svg_modified.emit(self.component_key, text)
        else:
            self.lbl_valid.setText(f"Error: {err[:45]}...")
            self.lbl_valid.setStyleSheet("color: #ff4757; font-size: 11px; font-weight: bold;")

    def _apply_code(self):
        text = self.code_edit.toPlainText()
        is_valid, err = validate_svg(text)
        if not is_valid:
            QMessageBox.warning(self, "Invalid SVG XML", f"Cannot apply SVG:\n{err}")
            return
        if self.current_svg and self.current_svg != text:
            self._push_undo_state(self.current_svg)
        self.set_svg_content(text, push_undo=False)
        self.svg_modified.emit(self.component_key, text)

    def _format_code(self):
        cur = self.code_edit.toPlainText()
        formatted = format_svg(cur)
        if formatted != cur:
            self._push_undo_state(cur)
            self._suppress_events = True
            self.code_edit.setPlainText(formatted)
            self._suppress_events = False
            self.current_svg = formatted
            self.preview_box.set_svg_content(formatted)
            self.svg_modified.emit(self.component_key, formatted)

    def _validate_syntax(self, svg_str: str):
        is_valid, err = validate_svg(svg_str)
        if is_valid:
            self.lbl_valid.setText("Valid SVG")
            self.lbl_valid.setStyleSheet("color: #2ed573; font-size: 11px; font-weight: bold;")
        else:
            self.lbl_valid.setText(f"Error: {err[:40]}")
            self.lbl_valid.setStyleSheet("color: #ff4757; font-size: 11px; font-weight: bold;")

    def _import_svg_file(self):
        path, _ = QFileDialog.getOpenFileName(self, "Import SVG File", "", "SVG Files (*.svg)")
        if path:
            try:
                with open(path, "r", encoding="utf-8") as f:
                    content = f.read()
                is_valid, err = validate_svg(content)
                if not is_valid:
                    QMessageBox.warning(self, "Invalid SVG", f"Selected file is not valid SVG:\n{err}")
                    return
                self.set_svg_content(content, push_undo=True)
                self.svg_modified.emit(self.component_key, content)
            except Exception as e:
                QMessageBox.critical(self, "Import Error", f"Failed to read file:\n{e}")

    def _export_svg_file(self):
        path, _ = QFileDialog.getSaveFileName(self, "Export SVG File", f"{self.component_key}.svg", "SVG Files (*.svg)")
        if path:
            try:
                with open(path, "w", encoding="utf-8") as f:
                    f.write(format_svg(self.current_svg))
                QMessageBox.information(self, "Export Successful", f"Saved SVG to:\n{path}")
            except Exception as e:
                QMessageBox.critical(self, "Export Error", f"Failed to save file:\n{e}")

    def _mirror_to_opposite(self, target_key: str):
        """Mirrors current wing horizontally and sends to the opposite wing."""
        mirrored = mirror_svg_horizontally(self.current_svg)
        self.request_mirror_to_opposite.emit(target_key, mirrored)

    # ----------------------------------------------------------------------
    # GEOMETRY / BEAT FLIP / TRIGGER HIT UI BUILDERS
    # ----------------------------------------------------------------------

    def _build_geometry_controls(self, parent_layout):
        box = QFrame(self)
        box.setStyleSheet("""
            QFrame {
                background: #15151e;
                border: none;
                border-radius: 6px;
                padding: 4px;
            }
            QLabel {
                font-size: 11px;
                color: #a0a0b8;
            }
            QSlider::groove:horizontal {
                height: 4px;
                background: #282836;
                border-radius: 2px;
            }
            QSlider::sub-page:horizontal {
                background: #9b51e0;
                border-radius: 2px;
            }
            QSlider::handle:horizontal {
                background: #ffffff;
                width: 12px;
                margin-top: -4px;
                margin-bottom: -4px;
                border-radius: 6px;
            }
        """)
        b_layout = QVBoxLayout(box)
        b_layout.setContentsMargins(6, 6, 6, 6)
        b_layout.setSpacing(4)

        b_header = QHBoxLayout()
        lbl_title = QLabel("Position & Scaling")
        lbl_title.setStyleSheet("font-weight: bold; color: #ffffff; font-size: 11px;")
        b_header.addWidget(lbl_title)
        b_header.addStretch(1)
        btn_rst = QPushButton("Reset")
        btn_rst.setStyleSheet("padding: 2px 6px; font-size: 10px; background: #222230;")
        btn_rst.clicked.connect(self._on_geom_reset)
        b_header.addWidget(btn_rst)
        b_layout.addLayout(b_header)

        # Offset X
        row_x = QHBoxLayout()
        row_x.addWidget(QLabel("Offset X:"))
        self.lbl_off_x_val = QLabel("+0 px")
        self.lbl_off_x_val.setStyleSheet("color: #00f3ff; font-weight: bold; font-family: monospace;")
        row_x.addWidget(self.lbl_off_x_val)
        b_layout.addLayout(row_x)

        self.slider_off_x = QSlider(Qt.Orientation.Horizontal)
        self.slider_off_x.setRange(-200, 200)
        self.slider_off_x.setValue(0)
        self.slider_off_x.valueChanged.connect(self._on_geom_slider_changed)
        b_layout.addWidget(self.slider_off_x)

        # Offset Y
        row_y = QHBoxLayout()
        row_y.addWidget(QLabel("Offset Y:"))
        self.lbl_off_y_val = QLabel("+0 px")
        self.lbl_off_y_val.setStyleSheet("color: #00f3ff; font-weight: bold; font-family: monospace;")
        row_y.addWidget(self.lbl_off_y_val)
        b_layout.addLayout(row_y)

        self.slider_off_y = QSlider(Qt.Orientation.Horizontal)
        self.slider_off_y.setRange(-100, 100)
        self.slider_off_y.setValue(0)
        self.slider_off_y.valueChanged.connect(self._on_geom_slider_changed)
        b_layout.addWidget(self.slider_off_y)

        # Scale
        row_s = QHBoxLayout()
        row_s.addWidget(QLabel("Scale:"))
        self.lbl_scale_val = QLabel("1.00x")
        self.lbl_scale_val.setStyleSheet("color: #00f3ff; font-weight: bold; font-family: monospace;")
        row_s.addWidget(self.lbl_scale_val)
        b_layout.addLayout(row_s)

        self.slider_scale = QSlider(Qt.Orientation.Horizontal)
        self.slider_scale.setRange(20, 300)
        self.slider_scale.setValue(100)
        self.slider_scale.valueChanged.connect(self._on_geom_slider_changed)
        b_layout.addWidget(self.slider_scale)

        parent_layout.addWidget(box)

    def _build_beat_flip_controls(self, parent_layout):
        box = QFrame(self)
        box.setStyleSheet("""
            QFrame {
                background: #15151e;
                border: none;
                border-radius: 6px;
                padding: 4px;
            }
            QLabel {
                font-size: 11px;
                color: #a0a0b8;
            }
            QCheckBox {
                color: #d0d0e0;
                font-size: 11px;
                spacing: 6px;
            }
        """)
        b_layout = QVBoxLayout(box)
        b_layout.setContentsMargins(8, 8, 8, 8)
        b_layout.setSpacing(8)

        lbl_title = QLabel("Beat Directional Flipping")
        lbl_title.setStyleSheet("font-weight: bold; color: #ffffff; font-size: 11px;")
        b_layout.addWidget(lbl_title)

        self.chk_flip_left = QCheckBox("Flip Beats on Left Side")
        self.chk_flip_left.setToolTip("Flips beats approaching target from the left horizontally")
        self.chk_flip_left.toggled.connect(self._on_beat_flip_changed)
        b_layout.addWidget(self.chk_flip_left)

        self.chk_flip_right = QCheckBox("Flip Beats on Right Side")
        self.chk_flip_right.setToolTip("Flips beats approaching target from the right horizontally")
        self.chk_flip_right.toggled.connect(self._on_beat_flip_changed)
        b_layout.addWidget(self.chk_flip_right)

        parent_layout.addWidget(box)

    def _build_trigger_hit_controls(self, parent_layout):
        box = QFrame(self)
        box.setStyleSheet("""
            QFrame {
                background: #15151e;
                border: none;
                border-radius: 6px;
                padding: 4px;
            }
            QLabel {
                font-size: 11px;
                color: #a0a0b8;
            }
            QSlider::groove:horizontal {
                height: 4px;
                background: #282836;
                border-radius: 2px;
            }
            QSlider::sub-page:horizontal {
                background: #9b51e0;
                border-radius: 2px;
            }
            QSlider::handle:horizontal {
                background: #ffffff;
                width: 12px;
                margin-top: -4px;
                margin-bottom: -4px;
                border-radius: 6px;
            }
        """)
        b_layout = QVBoxLayout(box)
        b_layout.setContentsMargins(6, 6, 6, 6)
        b_layout.setSpacing(6)

        lbl_title = QLabel("Hit Trigger & Indicator")
        lbl_title.setStyleSheet("font-weight: bold; color: #ffffff; font-size: 11px;")
        b_layout.addWidget(lbl_title)

        # Indicator Style
        row_style = QHBoxLayout()
        row_style.addWidget(QLabel("Indicator:"))
        self.combo_ind_style = QComboBox()
        self.combo_ind_style.addItem("▲ Triangle", "triangle")
        self.combo_ind_style.addItem("◆ Diamond", "diamond")
        self.combo_ind_style.addItem("━ Glow Bar", "glow_bar")
        self.combo_ind_style.addItem("Hidden", "hidden")
        self.combo_ind_style.currentIndexChanged.connect(self._on_trigger_hit_changed)
        row_style.addWidget(self.combo_ind_style)
        b_layout.addLayout(row_style)

        # Indicator Color
        row_col = QHBoxLayout()
        row_col.addWidget(QLabel("Color:"))
        self.btn_ind_color = QPushButton("#FFFFFF")
        self.btn_ind_color.setFixedHeight(24)
        self.btn_ind_color.setCursor(Qt.CursorShape.PointingHandCursor)
        self.btn_ind_color.clicked.connect(self._on_pick_ind_color)
        row_col.addWidget(self.btn_ind_color)
        b_layout.addLayout(row_col)
        self._update_ind_col_btn()

        # Hit State Duration
        row_d = QHBoxLayout()
        row_d.addWidget(QLabel("Hit Duration:"))
        self.lbl_hit_dur_val = QLabel("180 ms")
        self.lbl_hit_dur_val.setStyleSheet("color: #00f3ff; font-weight: bold; font-family: monospace;")
        row_d.addWidget(self.lbl_hit_dur_val)
        b_layout.addLayout(row_d)

        self.slider_hit_dur = QSlider(Qt.Orientation.Horizontal)
        self.slider_hit_dur.setRange(50, 500)
        self.slider_hit_dur.setValue(180)
        self.slider_hit_dur.valueChanged.connect(self._on_trigger_hit_changed)
        b_layout.addWidget(self.slider_hit_dur)

        # Target Pop Scale
        row_p = QHBoxLayout()
        row_p.addWidget(QLabel("Pop Scale:"))
        self.lbl_pop_scale_val = QLabel("1.35x")
        self.lbl_pop_scale_val.setStyleSheet("color: #00f3ff; font-weight: bold; font-family: monospace;")
        row_p.addWidget(self.lbl_pop_scale_val)
        b_layout.addLayout(row_p)

        self.slider_pop_scale = QSlider(Qt.Orientation.Horizontal)
        self.slider_pop_scale.setRange(100, 250)
        self.slider_pop_scale.setValue(135)
        self.slider_pop_scale.valueChanged.connect(self._on_trigger_hit_changed)
        b_layout.addWidget(self.slider_pop_scale)

        parent_layout.addWidget(box)

    def _update_ind_col_btn(self):
        c = QColor(self.current_ind_color)
        lum = 0.299 * c.red() + 0.587 * c.green() + 0.114 * c.blue()
        txt_col = "#000000" if lum > 130 else "#ffffff"
        self.btn_ind_color.setText(self.current_ind_color.upper())
        self.btn_ind_color.setStyleSheet(f"""
            QPushButton {{
                background-color: {self.current_ind_color};
                color: {txt_col};
                border: 1px solid #444458;
                border-radius: 4px;
                font-family: monospace;
                font-size: 11px;
                font-weight: bold;
            }}
        """)

    def _on_geom_slider_changed(self):
        if self._suppress_events or not hasattr(self, "slider_off_x"):
            return
        ox = self.slider_off_x.value()
        oy = self.slider_off_y.value()
        sc = self.slider_scale.value() / 100.0
        self.lbl_off_x_val.setText(f"{ox:+d} px")
        self.lbl_off_y_val.setText(f"{oy:+d} px")
        self.lbl_scale_val.setText(f"{sc:.2f}x")
        self.layout_modified.emit(self.component_key, {
            "offset_x": float(ox),
            "offset_y": float(oy),
            "scale": float(sc)
        })

    def _on_geom_reset(self):
        self._suppress_events = True
        self.slider_off_x.setValue(0)
        self.slider_off_y.setValue(0)
        self.slider_scale.setValue(100)
        self.lbl_off_x_val.setText("+0 px")
        self.lbl_off_y_val.setText("+0 px")
        self.lbl_scale_val.setText("1.00x")
        self._suppress_events = False
        self.layout_modified.emit(self.component_key, {
            "offset_x": 0.0,
            "offset_y": 0.0,
            "scale": 1.0
        })

    def _on_beat_flip_changed(self):
        if self._suppress_events or not hasattr(self, "chk_flip_left"):
            return
        fl = self.chk_flip_left.isChecked()
        fr = self.chk_flip_right.isChecked()
        self.beat_flip_modified.emit(fl, fr)

    def _on_pick_ind_color(self):
        c = QColorDialog.getColor(QColor(self.current_ind_color), self, "Select Hit Indicator Color")
        if c.isValid():
            self.current_ind_color = c.name()
            self._update_ind_col_btn()
            self._on_trigger_hit_changed()

    def _on_trigger_hit_changed(self):
        if self._suppress_events or not hasattr(self, "combo_ind_style"):
            return
        style = self.combo_ind_style.currentData()
        dur = self.slider_hit_dur.value()
        pop = self.slider_pop_scale.value() / 100.0
        self.lbl_hit_dur_val.setText(f"{dur} ms")
        self.lbl_pop_scale_val.setText(f"{pop:.2f}x")
        self.trigger_hit_modified.emit({
            "indicator_style": style,
            "indicator_color": self.current_ind_color,
            "duration_ms": float(dur),
            "pop_scale": float(pop)
        })

    def set_layout_data(self, cfg: dict):
        if not hasattr(self, "slider_off_x"):
            return
        self._suppress_events = True
        ox = int(cfg.get("offset_x", 0.0))
        oy = int(cfg.get("offset_y", 0.0))
        sc = int(float(cfg.get("scale", 1.0)) * 100)
        self.slider_off_x.setValue(ox)
        self.slider_off_y.setValue(oy)
        self.slider_scale.setValue(sc)
        self.lbl_off_x_val.setText(f"{ox:+d} px")
        self.lbl_off_y_val.setText(f"{oy:+d} px")
        self.lbl_scale_val.setText(f"{sc/100.0:.2f}x")
        self._suppress_events = False

    def set_beat_flip_data(self, flip_l: bool, flip_r: bool):
        if not hasattr(self, "chk_flip_left"):
            return
        self._suppress_events = True
        self.chk_flip_left.setChecked(bool(flip_l))
        self.chk_flip_right.setChecked(bool(flip_r))
        self._suppress_events = False

    def set_trigger_hit_data(self, cfg: dict):
        if not hasattr(self, "combo_ind_style"):
            return
        self._suppress_events = True
        style = cfg.get("indicator_style", "triangle")
        for i in range(self.combo_ind_style.count()):
            if self.combo_ind_style.itemData(i) == style:
                self.combo_ind_style.setCurrentIndex(i)
                break
        self.current_ind_color = cfg.get("indicator_color", "#ffffff")
        self._update_ind_col_btn()
        dur = int(cfg.get("duration_ms", 180))
        pop = int(float(cfg.get("pop_scale", 1.35)) * 100)
        self.slider_hit_dur.setValue(dur)
        self.slider_pop_scale.setValue(pop)
        self.lbl_hit_dur_val.setText(f"{dur} ms")
        self.lbl_pop_scale_val.setText(f"{pop/100.0:.2f}x")
        self._suppress_events = False

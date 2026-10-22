import sys
import os
import json
import subprocess
import numpy as np
from PIL import Image, ImageDraw, ImageOps

from PyQt6.QtCore import Qt, QThread, pyqtSignal
from PyQt6.QtWidgets import (
    QApplication, QMainWindow, QWidget, QVBoxLayout, QHBoxLayout,
    QPushButton, QSlider, QComboBox, QLabel, QLineEdit, QFileDialog,
    QMessageBox, QDialog, QFormLayout, QDoubleSpinBox, QCheckBox,
    QProgressDialog, QGroupBox, QColorDialog, QSpinBox, QScrollArea
)
from PyQt6.QtGui import QColor, QFont

class RenderThread(QThread):
    """Background thread to render video frames, write to FFmpeg, and merge audio."""
    progress = pyqtSignal(int, int, str)  # current_frame, total_frames, stage_name
    finished = pyqtSignal(str)
    error = pyqtSignal(str)

    def __init__(self, settings):
        super().__init__()
        self.s = settings

    def run(self):
        try:
            # 1. Parse beatmap
            beats = self.load_beatmap(self.s['beatmap_path'])
            if not beats:
                raise Exception("No beats found in the selected beatmap file.")
                
            # Filter beats based on active lanes
            active_lanes = [i for i, active in enumerate(self.s['active_lanes']) if active]
            beats = [b for b in beats if b['lane'] in active_lanes]
            if not beats:
                raise Exception("No beats exist on the selected active lanes.")
                
            # Sort beats chronologically
            beats.sort(key=lambda x: x['time'])
            
            # Determine audio duration
            max_beat_time = beats[-1]['time']
            audio_duration = max_beat_time + 3.0  # pad 3 seconds after last beat
            
            if os.path.exists(self.s['audio_path']):
                try:
                    audio_duration = self.get_audio_duration(self.s['audio_path'])
                except Exception as e:
                    print("Could not retrieve precise audio duration, using beat padding:", e)
                    
            # Render parameters
            fps = self.s['fps']
            
            # Resolution selection
            if self.s['resolution'] == "1080p":
                w, h = 1920, 1080
            else:
                w, h = 1280, 720
                
            total_frames = int(audio_duration * fps)
            
            # Setup layout heights for lanes
            layout = self.s['layout'] # "Unified" or "Stacked"
            bottom_offset = self.s['bottom_offset']
            target_x = self.s['target_x']
            travel_time = self.s['travel_time']
            fade_duration = self.s['fade_duration']
            max_scale = self.s['max_scale']
            
            # Base sizes based on resolution
            scale_factor = h / 720.0
            base_note_size = int(50 * scale_factor)
            base_target_size = int(60 * scale_factor)
            
            # Pre-load custom skins (Target & Lane 0-4 beats)
            skins = {}
            target_skin = None
            
            # Load target skin
            if self.s['target_skin_path'] and os.path.exists(self.s['target_skin_path']):
                try:
                    target_skin = Image.open(self.s['target_skin_path']).convert("RGBA")
                    target_skin = target_skin.resize((base_target_size, base_target_size), Image.Resampling.LANCZOS)
                except Exception as e:
                    print("Failed to load target skin:", e)
            
            # Load lane beat skins
            for lane in range(5):
                path_key = f"lane_{lane}_skin_path"
                if self.s[path_key] and os.path.exists(self.s[path_key]):
                    try:
                        img = Image.open(self.s[path_key]).convert("RGBA")
                        img = img.resize((base_note_size, base_note_size), Image.Resampling.LANCZOS)
                        skins[lane] = img
                    except Exception as e:
                        print(f"Failed to load lane {lane} skin:", e)
                        
            # Default colors
            lane_colors = [
                "#FF4136",  # Red
                "#2ECC40",  # Green
                "#0074D9",  # Blue/Cyan
                "#FFDC00",  # Yellow
                "#B10DC9"   # Purple
            ]
            
            # Compute Y coordinates for lanes
            lane_y_coords = {}
            if layout == "Unified":
                for lane in active_lanes:
                    lane_y_coords[lane] = h - bottom_offset
            else:
                # Stacked lanes
                N = len(active_lanes)
                spacing = int(65 * scale_factor)
                for i, lane in enumerate(active_lanes):
                    lane_y_coords[lane] = int((h - bottom_offset) - ((N - 1) / 2.0) * spacing + i * spacing)
                    
            # 2. Setup FFmpeg video writer pipe
            temp_silent_video = "temp_silent_video.mp4"
            cmd = [
                "ffmpeg", "-y",
                "-f", "rawvideo",
                "-vcodec", "rawvideo",
                "-pix_fmt", "rgb24",
                "-s", f"{w}x{h}",
                "-r", str(fps),
                "-i", "-",  # input from stdin
                "-c:v", "libx264",
                "-pix_fmt", "yuv420p",
                "-crf", "18",  # High quality
                temp_silent_video
            ]
            
            creationflags = getattr(subprocess, 'CREATE_NO_WINDOW', 0x08000000) if sys.platform == 'win32' else 0
            proc = subprocess.Popen(cmd, stdin=subprocess.PIPE, stdout=subprocess.PIPE, stderr=subprocess.PIPE, creationflags=creationflags)
            
            # 3. Render frames
            bg_color = self.s['greenscreen_color']
            bar_color = self.s['bar_color']
            bar_thickness = max(1, int(4 * scale_factor))
            
            # Loop through all frames
            for frame_idx in range(total_frames):
                if self.isInterruptionRequested():
                    proc.kill()
                    return
                    
                t = frame_idx / float(fps)
                
                # Base frame background
                frame_img = Image.new("RGB", (w, h), bg_color)
                draw = ImageDraw.Draw(frame_img, "RGBA")
                
                # Draw bar lines
                for lane in active_lanes:
                    y = lane_y_coords[lane]
                    draw.line([(0, y), (w, y)], fill=bar_color, width=bar_thickness)
                    
                # Draw target hit zones
                for lane in active_lanes:
                    y = lane_y_coords[lane]
                    if target_skin:
                        x_min = target_x - base_target_size // 2
                        y_min = y - base_target_size // 2
                        frame_img.paste(target_skin, (x_min, y_min), mask=target_skin)
                    else:
                        draw.ellipse(
                            [target_x - base_target_size//2, y - base_target_size//2, 
                             target_x + base_target_size//2, y + base_target_size//2],
                            outline="#FFFFFF", width=int(2.5 * scale_factor)
                        )
                
                # Find beats active in this frame
                for beat in beats:
                    beat_t = beat['time']
                    lane = beat['lane']
                    y = lane_y_coords[lane]
                    
                    # 1) Note scrolling from right to left
                    if (beat_t - travel_time) <= t <= beat_t:
                        # Calculate position
                        progress = (t - (beat_t - travel_time)) / travel_time
                        cx = int(w - (w - target_x) * progress)
                        
                        # Draw note
                        if lane in skins:
                            skin_img = skins[lane]
                            x_min = cx - base_note_size // 2
                            y_min = y - base_note_size // 2
                            frame_img.paste(skin_img, (x_min, y_min), mask=skin_img)
                        else:
                            color = lane_colors[lane]
                            draw.ellipse(
                                [cx - base_note_size//2, y - base_note_size//2, 
                                 cx + base_note_size//2, y + base_note_size//2],
                                fill=color, outline="#FFFFFF", width=int(1.5 * scale_factor)
                            )
                            
                    # 2) Note hit: expanding and fading
                    elif beat_t < t <= (beat_t + fade_duration):
                        progress = (t - beat_t) / fade_duration
                        alpha = 1.0 - progress
                        current_scale = 1.0 + (max_scale - 1.0) * progress
                        current_size = int(base_note_size * current_scale)
                        
                        if lane in skins:
                            skin_img = skins[lane]
                            resized_skin = skin_img.resize((current_size, current_size), Image.Resampling.BILINEAR)
                            faded_skin = self.apply_alpha_to_img(resized_skin, alpha)
                            x_min = target_x - current_size // 2
                            y_min = y - current_size // 2
                            frame_img.paste(faded_skin, (x_min, y_min), mask=faded_skin)
                        else:
                            color = QColor(lane_colors[lane])
                            color.setAlpha(int(alpha * 255))
                            rgba_tuple = (color.red(), color.green(), color.blue(), color.alpha())
                            
                            overlay = Image.new("RGBA", (w, h), (0, 0, 0, 0))
                            overlay_draw = ImageDraw.Draw(overlay)
                            overlay_draw.ellipse(
                                [target_x - current_size//2, y - current_size//2,
                                 target_x + current_size//2, y + current_size//2],
                                fill=rgba_tuple, outline=(255, 255, 255, int(alpha * 255)), width=int(1.5 * scale_factor)
                            )
                            frame_img = Image.alpha_composite(frame_img.convert("RGBA"), overlay).convert("RGB")
                            draw = ImageDraw.Draw(frame_img, "RGBA")
                
                # Write frame to pipe
                proc.stdin.write(frame_img.tobytes())
                
                if frame_idx % 30 == 0:
                    self.progress.emit(frame_idx, total_frames, "Rendering Video Frames")
                    
            proc.stdin.close()
            stdout, stderr = proc.communicate()
            if proc.returncode != 0:
                raise Exception(f"FFmpeg render failed:\n{stderr.decode('utf-8')}")
                
            # 4. Merge audio with the silent video
            self.progress.emit(total_frames, total_frames, "Merging Audio Stream")
            
            output_video_path = self.s['output_video_path']
            audio_path = self.s['audio_path']
            
            merge_cmd = [
                "ffmpeg", "-y",
                "-i", temp_silent_video,
                "-i", audio_path,
                "-c:v", "copy",
                "-c:a", "aac",
                "-map", "0:v:0",
                "-map", "1:a:0",
                "-shortest",
                output_video_path
            ]
            
            merge_proc = subprocess.run(merge_cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE, creationflags=creationflags)
            
            if os.path.exists(temp_silent_video):
                os.remove(temp_silent_video)
                
            if merge_proc.returncode != 0:
                raise Exception(f"FFmpeg audio merge failed:\n{merge_proc.stderr.decode('utf-8')}")
                
            self.finished.emit(output_video_path)
            
        except Exception as e:
            self.error.emit(str(e))

    def apply_alpha_to_img(self, img, alpha):
        r, g, b, a = img.split()
        a = a.point(lambda p: int(p * alpha))
        return Image.merge("RGBA", (r, g, b, a))

    def load_beatmap(self, path):
        if path.lower().endswith(".json"):
            with open(path, 'r', encoding='utf-8') as f:
                data = json.load(f)
                return data.get("beats", [])
        else:
            beats = []
            with open(path, 'r', encoding='utf-8') as f:
                for line in f:
                    line = line.strip()
                    if not line or line.startswith('#'):
                        continue
                    tokens = line.split()
                    if len(tokens) >= 2:
                        try:
                            t = float(tokens[0])
                            lane = int(tokens[1])
                            beats.append({'time': t, 'lane': lane})
                        except ValueError:
                            continue
            return beats

    def get_audio_duration(self, file_path):
        cmd = [
            "ffprobe", "-v", "error",
            "-show_entries", "format=duration",
            "-of", "default=noprint_wrappers=1:nokey=1",
            file_path
        ]
        creationflags = getattr(subprocess, 'CREATE_NO_WINDOW', 0x08000000) if sys.platform == 'win32' else 0
        result = subprocess.run(cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True, creationflags=creationflags)
        if result.returncode == 0:
            return float(result.stdout.strip())
        else:
            raise Exception(result.stderr)


class VideoGeneratorApp(QMainWindow):
    """Desktop GUI interface to customize and generate beatbar greenscreen overlays."""
    def __init__(self):
        super().__init__()
        self.setWindowTitle("Beatbar Greenscreen Video Generator")
        self.resize(540, 580)  # Resize window to fit 1366x768 display comfortably
        self.setStyleSheet(self.get_stylesheet())
        
        self.greenscreen_hex = "#00FF00"  # Default greenscreen
        self.bar_line_hex = "#3d3d42"     # Default line color
        
        self.setup_ui()

    def get_stylesheet(self):
        return """
        QMainWindow {
            background-color: #0c0c0e;
        }
        QWidget {
            font-family: 'Segoe UI', Arial, sans-serif;
            color: #d1d1d6;
        }
        QPushButton {
            background: qlineargradient(x1:0, y1:0, x2:0, y2:1, stop:0 #242429, stop:1 #1a1a1f);
            border: 1px solid #3c3c44;
            border-radius: 6px;
            padding: 6px 12px;
            font-weight: bold;
            font-size: 11px;
            min-height: 18px;
        }
        QPushButton:hover {
            background: qlineargradient(x1:0, y1:0, x2:0, y2:1, stop:0 #32323b, stop:1 #24242a);
            border-color: #555562;
        }
        QPushButton:pressed {
            background: #141417;
            border-color: #00ffff;
        }
        QPushButton#render_btn {
            background: qlineargradient(x1:0, y1:0, x2:0, y2:1, stop:0 #00ffcc, stop:1 #009977);
            border: 1px solid #00ffaa;
            color: #000000;
            font-size: 13px;
            min-height: 28px;
        }
        QPushButton#render_btn:hover {
            background: qlineargradient(x1:0, y1:0, x2:0, y2:1, stop:0 #40ffd4, stop:1 #00b38c);
            border-color: #80ffea;
        }
        QPushButton#render_btn:pressed {
            background: #008064;
            border-color: #00ffaa;
        }
        QLineEdit {
            background-color: #121214;
            border: 1px solid #2d2d35;
            border-radius: 6px;
            padding: 5px 8px;
            font-size: 11px;
        }
        QComboBox, QSpinBox, QDoubleSpinBox {
            background-color: #121214;
            border: 1px solid #2d2d35;
            border-radius: 6px;
            padding: 4px 8px;
            min-width: 80px;
        }
        QGroupBox {
            border: 1px solid #2d2d35;
            border-radius: 8px;
            margin-top: 12px;
            padding-top: 15px;
            font-weight: bold;
            font-size: 11px;
        }
        QGroupBox::title {
            subcontrol-origin: margin;
            left: 10px;
            padding: 0 5px;
            color: #00e5ff;
        }
        QCheckBox {
            font-size: 11px;
        }
        QScrollArea {
            border: none;
            background: transparent;
        }
        """

    def setup_ui(self):
        main_widget = QWidget()
        main_layout = QVBoxLayout(main_widget)
        main_layout.setContentsMargins(10, 10, 10, 10)
        
        # Create settings scroll area for high responsiveness on small screens
        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        scroll.setVerticalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAsNeeded)
        
        scroll_content = QWidget()
        scroll_layout = QVBoxLayout(scroll_content)
        scroll_layout.setContentsMargins(0, 0, 5, 0)
        scroll_layout.setSpacing(10)
        
        # Files Group Box
        files_group = QGroupBox("1. File Configurations")
        files_form = QFormLayout(files_group)
        
        self.txt_beatmap = QLineEdit()
        btn_browse_beatmap = QPushButton("Browse")
        btn_browse_beatmap.clicked.connect(self.browse_beatmap)
        beatmap_row = QHBoxLayout()
        beatmap_row.addWidget(self.txt_beatmap)
        beatmap_row.addWidget(btn_browse_beatmap)
        files_form.addRow("Beatmap File:", beatmap_row)
        
        self.txt_audio = QLineEdit()
        btn_browse_audio = QPushButton("Browse")
        btn_browse_audio.clicked.connect(self.browse_audio)
        audio_row = QHBoxLayout()
        audio_row.addWidget(self.txt_audio)
        audio_row.addWidget(btn_browse_audio)
        files_form.addRow("Audio File:", audio_row)
        
        self.txt_output = QLineEdit()
        btn_browse_output = QPushButton("Browse")
        btn_browse_output.clicked.connect(self.browse_output)
        output_row = QHBoxLayout()
        output_row.addWidget(self.txt_output)
        output_row.addWidget(btn_browse_output)
        files_form.addRow("Output Video:", output_row)
        
        scroll_layout.addWidget(files_group)
        
        # Rendering settings
        settings_group = QGroupBox("2. Render Settings")
        settings_form = QFormLayout(settings_group)
        
        self.cb_resolution = QComboBox()
        self.cb_resolution.addItems(["1080p (1920x1080)", "720p (1280x720)"])
        self.cb_resolution.setCurrentText("720p (1280x720)")
        settings_form.addRow("Resolution:", self.cb_resolution)
        
        self.cb_fps = QComboBox()
        self.cb_fps.addItems(["30", "48", "60"])  # Added 48 FPS option for target video
        self.cb_fps.setEditable(True)             # Allow user to type custom values
        self.cb_fps.setCurrentText("48")          # Set 48 FPS as default
        settings_form.addRow("Framerate (FPS):", self.cb_fps)
        
        self.cb_layout = QComboBox()
        self.cb_layout.addItems(["Stacked Lanes (Multi-track)", "Unified Lane (Single-track)"])
        self.cb_layout.setCurrentText("Stacked Lanes (Multi-track)")
        settings_form.addRow("Timeline Layout:", self.cb_layout)
        
        # Active Lanes Checkboxes
        lane_row = QHBoxLayout()
        self.chk_bass = QCheckBox("Bass")
        self.chk_bass.setChecked(True)
        self.chk_lowmid = QCheckBox("Low-Mid")
        self.chk_lowmid.setChecked(True)
        self.chk_highmid = QCheckBox("High-Mid")
        self.chk_highmid.setChecked(True)
        self.chk_treble = QCheckBox("Treble")
        self.chk_treble.setChecked(True)
        self.chk_beats = QCheckBox("Beats")
        self.chk_beats.setChecked(True)
        
        lane_row.addWidget(self.chk_bass)
        lane_row.addWidget(self.chk_lowmid)
        lane_row.addWidget(self.chk_highmid)
        lane_row.addWidget(self.chk_treble)
        lane_row.addWidget(self.chk_beats)
        settings_form.addRow("Active Tracks:", lane_row)
        
        scroll_layout.addWidget(settings_group)
        
        # Animation and placement controls
        anim_group = QGroupBox("3. Placement & Animation Customizations")
        anim_form = QFormLayout(anim_group)
        
        self.spin_bottom_offset = QSpinBox()
        self.spin_bottom_offset.setRange(50, 600)
        self.spin_bottom_offset.setValue(150)
        anim_form.addRow("Bottom Offset (px):", self.spin_bottom_offset)
        
        self.spin_target_x = QSpinBox()
        self.spin_target_x.setRange(50, 1000)
        self.spin_target_x.setValue(200)
        anim_form.addRow("Target hit X (px):", self.spin_target_x)
        
        self.spin_travel_time = QDoubleSpinBox()
        self.spin_travel_time.setRange(0.5, 8.0)
        self.spin_travel_time.setValue(2.0)
        self.spin_travel_time.setSingleStep(0.2)
        anim_form.addRow("Travel scroll duration (sec):", self.spin_travel_time)
        
        self.spin_fade_duration = QDoubleSpinBox()
        self.spin_fade_duration.setRange(0.05, 2.0)
        self.spin_fade_duration.setValue(0.3)
        self.spin_fade_duration.setSingleStep(0.05)
        anim_form.addRow("Hit Fadeout duration (sec):", self.spin_fade_duration)
        
        self.spin_max_scale = QDoubleSpinBox()
        self.spin_max_scale.setRange(1.0, 5.0)
        self.spin_max_scale.setValue(2.0)
        self.spin_max_scale.setSingleStep(0.1)
        anim_form.addRow("Max hit expansion scale:", self.spin_max_scale)
        
        color_row = QHBoxLayout()
        self.btn_greenscreen_color = QPushButton("Green Screen")
        self.btn_greenscreen_color.clicked.connect(self.select_greenscreen_color)
        self.lbl_greenscreen_color = QLabel("#00FF00")
        self.lbl_greenscreen_color.setFixedWidth(60)
        self.lbl_greenscreen_color.setStyleSheet("background-color: #00FF00; color: #000000; border: 1px solid white; border-radius: 4px; font-weight: bold; text-align: center; padding: 2px;")
        
        self.btn_bar_color = QPushButton("Bar Line")
        self.btn_bar_color.clicked.connect(self.select_bar_color)
        self.lbl_bar_color = QLabel("#3D3D42")
        self.lbl_bar_color.setFixedWidth(60)
        self.lbl_bar_color.setStyleSheet("background-color: #3D3D42; color: #FFFFFF; border: 1px solid white; border-radius: 4px; font-weight: bold; text-align: center; padding: 2px;")
        
        color_row.addWidget(self.btn_greenscreen_color)
        color_row.addWidget(self.lbl_greenscreen_color)
        color_row.addSpacing(20)
        color_row.addWidget(self.btn_bar_color)
        color_row.addWidget(self.lbl_bar_color)
        anim_form.addRow("Color Customization:", color_row)
        
        scroll_layout.addWidget(anim_group)
        
        # Custom skins PNG group
        skins_group = QGroupBox("4. Customizable Skins (PNG PNGs)")
        skins_form = QFormLayout(skins_group)
        
        self.txt_target_skin = QLineEdit()
        btn_browse_target_skin = QPushButton("Browse")
        btn_browse_target_skin.clicked.connect(lambda: self.browse_skin(self.txt_target_skin))
        row = QHBoxLayout()
        row.addWidget(self.txt_target_skin)
        row.addWidget(btn_browse_target_skin)
        skins_form.addRow("Target PNG:", row)
        
        self.txt_bass_skin = QLineEdit()
        btn_browse_bass = QPushButton("Browse")
        btn_browse_bass.clicked.connect(lambda: self.browse_skin(self.txt_bass_skin))
        row = QHBoxLayout()
        row.addWidget(self.txt_bass_skin)
        row.addWidget(btn_browse_bass)
        skins_form.addRow("Bass Beat PNG:", row)
        
        self.txt_lowmid_skin = QLineEdit()
        btn_browse_lowmid = QPushButton("Browse")
        btn_browse_lowmid.clicked.connect(lambda: self.browse_skin(self.txt_lowmid_skin))
        row = QHBoxLayout()
        row.addWidget(self.txt_lowmid_skin)
        row.addWidget(btn_browse_lowmid)
        skins_form.addRow("Low-Mid Beat PNG:", row)
        
        self.txt_highmid_skin = QLineEdit()
        btn_browse_highmid = QPushButton("Browse")
        btn_browse_highmid.clicked.connect(lambda: self.browse_skin(self.txt_highmid_skin))
        row = QHBoxLayout()
        row.addWidget(self.txt_highmid_skin)
        row.addWidget(btn_browse_highmid)
        skins_form.addRow("High-Mid Beat PNG:", row)
        
        self.txt_treble_skin = QLineEdit()
        btn_browse_treble = QPushButton("Browse")
        btn_browse_treble.clicked.connect(lambda: self.browse_skin(self.txt_treble_skin))
        row = QHBoxLayout()
        row.addWidget(self.txt_treble_skin)
        row.addWidget(btn_browse_treble)
        skins_form.addRow("Treble Beat PNG:", row)
        
        self.txt_beats_skin = QLineEdit()
        btn_browse_beats = QPushButton("Browse")
        btn_browse_beats.clicked.connect(lambda: self.browse_skin(self.txt_beats_skin))
        row = QHBoxLayout()
        row.addWidget(self.txt_beats_skin)
        row.addWidget(btn_browse_beats)
        skins_form.addRow("Beats Beat PNG:", row)
        
        scroll_layout.addWidget(skins_group)
        
        scroll.setWidget(scroll_content)
        main_layout.addWidget(scroll)
        
        # 5. Generate button (Fixed at the bottom outside the scrollable view)
        self.btn_render = QPushButton("GENERATE VIDEO")
        self.btn_render.setObjectName("render_btn")
        self.btn_render.clicked.connect(self.start_rendering)
        main_layout.addWidget(self.btn_render)
        
        self.setCentralWidget(main_widget)
        self.autoload_default_paths()

    def autoload_default_paths(self):
        if os.path.exists("demoness-overwatch-fap-hero_beats.json"):
            self.txt_beatmap.setText(os.path.abspath("demoness-overwatch-fap-hero_beats.json"))
        elif os.path.exists("demoness-overwatch-fap-hero_beats.txt"):
            self.txt_beatmap.setText(os.path.abspath("demoness-overwatch-fap-hero_beats.txt"))
            
        if os.path.exists("demoness-overwatch-fap-hero.mp3"):
            self.txt_audio.setText(os.path.abspath("demoness-overwatch-fap-hero.mp3"))
            self.txt_output.setText(os.path.abspath("demoness-overwatch-fap-hero_overlay.mp4"))

    def browse_beatmap(self):
        path, _ = QFileDialog.getOpenFileName(self, "Select Beatmap File", "", "Beatmap Files (*_beats.json *.json *.txt);;All Files (*)")
        if path:
            self.txt_beatmap.setText(path)
            if not self.txt_output.text():
                base = os.path.splitext(path)[0]
                self.txt_output.setText(base + "_overlay.mp4")

    def browse_audio(self):
        path, _ = QFileDialog.getOpenFileName(self, "Select Audio File", "", "Audio Files (*.mp3 *.wav *.mp4);;All Files (*)")
        if path:
            self.txt_audio.setText(path)

    def browse_output(self):
        path, _ = QFileDialog.getSaveFileName(self, "Save Video Overlay", "", "MP4 Video (*.mp4);;All Files (*)")
        if path:
            self.txt_output.setText(path)

    def browse_skin(self, line_edit):
        path, _ = QFileDialog.getOpenFileName(self, "Select Skin Image (PNG)", "", "PNG Images (*.png);;All Files (*)")
        if path:
            line_edit.setText(path)

    def select_greenscreen_color(self):
        color = QColorDialog.getColor(QColor(self.greenscreen_hex), self, "Select Greenscreen Color")
        if color.isValid():
            self.greenscreen_hex = color.name().upper()
            self.lbl_greenscreen_color.setText(self.greenscreen_hex)
            text_color = "#000000" if color.lightness() > 128 else "#FFFFFF"
            self.lbl_greenscreen_color.setStyleSheet(f"background-color: {self.greenscreen_hex}; color: {text_color}; border: 1px solid white; border-radius: 4px; font-weight: bold; text-align: center; padding: 2px;")

    def select_bar_color(self):
        color = QColorDialog.getColor(QColor(self.bar_line_hex), self, "Select Bar Line Color")
        if color.isValid():
            self.bar_line_hex = color.name().upper()
            self.lbl_bar_color.setText(self.bar_line_hex)
            text_color = "#000000" if color.lightness() > 128 else "#FFFFFF"
            self.lbl_bar_color.setStyleSheet(f"background-color: {self.bar_line_hex}; color: {text_color}; border: 1px solid white; border-radius: 4px; font-weight: bold; text-align: center; padding: 2px;")

    def start_rendering(self):
        beatmap_path = self.txt_beatmap.text()
        audio_path = self.txt_audio.text()
        output_path = self.txt_output.text()
        
        if not beatmap_path or not os.path.exists(beatmap_path):
            QMessageBox.critical(self, "Validation Error", "Please select a valid beatmap file.")
            return
        if not audio_path or not os.path.exists(audio_path):
            QMessageBox.critical(self, "Validation Error", "Please select a valid audio file.")
            return
        if not output_path:
            QMessageBox.critical(self, "Validation Error", "Please select an output video file destination.")
            return
            
        # Parse framerate from editable combobox
        try:
            fps_val = int(self.cb_fps.currentText().strip())
            if fps_val < 5 or fps_val > 240:
                raise ValueError()
        except ValueError:
            QMessageBox.critical(self, "Validation Error", "Please provide a valid Framerate between 5 and 240 FPS.")
            return
            
        settings = {
            'beatmap_path': beatmap_path,
            'audio_path': audio_path,
            'output_video_path': output_path,
            'resolution': "1080p" if "1080p" in self.cb_resolution.currentText() else "720p",
            'fps': fps_val,
            'layout': "Unified" if "Unified" in self.cb_layout.currentText() else "Stacked",
            'active_lanes': [
                self.chk_bass.isChecked(),
                self.chk_lowmid.isChecked(),
                self.chk_highmid.isChecked(),
                self.chk_treble.isChecked(),
                self.chk_beats.isChecked()
            ],
            'bottom_offset': self.spin_bottom_offset.value(),
            'target_x': self.spin_target_x.value(),
            'travel_time': self.spin_travel_time.value(),
            'fade_duration': self.spin_fade_duration.value(),
            'max_scale': self.spin_max_scale.value(),
            'greenscreen_color': self.greenscreen_hex,
            'bar_color': self.bar_line_hex,
            
            'target_skin_path': self.txt_target_skin.text(),
            'lane_0_skin_path': self.txt_bass_skin.text(),
            'lane_1_skin_path': self.txt_lowmid_skin.text(),
            'lane_2_skin_path': self.txt_highmid_skin.text(),
            'lane_3_skin_path': self.txt_treble_skin.text(),
            'lane_4_skin_path': self.txt_beats_skin.text()
        }
        
        if sum(1 for v in settings['active_lanes'] if v) == 0:
            QMessageBox.critical(self, "Validation Error", "Please check at least one active track under Active Tracks.")
            return
            
        self.progress_dlg = QProgressDialog("Starting render pipeline...", "Cancel", 0, 100, self)
        self.progress_dlg.setWindowTitle("Rendering Video Overlay")
        self.progress_dlg.setWindowModality(Qt.WindowModality.WindowModal)
        self.progress_dlg.setMinimumDuration(0)
        self.progress_dlg.show()
        
        self.render_thread = RenderThread(settings)
        self.render_thread.progress.connect(self.on_render_progress)
        self.render_thread.finished.connect(self.on_render_finished)
        self.render_thread.error.connect(self.on_render_error)
        
        self.progress_dlg.canceled.connect(self.render_thread.requestInterruption)
        
        self.btn_render.setEnabled(False)
        self.render_thread.start()

    def on_render_progress(self, frame_idx, total_frames, stage):
        pct = int((frame_idx / float(max(1, total_frames))) * 100)
        self.progress_dlg.setValue(pct)
        self.progress_dlg.setLabelText(f"Stage: {stage}\nProcessing: {pct}% ({frame_idx} / {total_frames} frames)")

    def on_render_finished(self, out_path):
        self.progress_dlg.close()
        self.btn_render.setEnabled(True)
        QMessageBox.information(
            self, "Render Complete", 
            f"Beatbar overlay video successfully generated!\nSaved to: {os.path.basename(out_path)}"
        )

    def on_render_error(self, err_msg):
        self.progress_dlg.close()
        self.btn_render.setEnabled(True)
        QMessageBox.critical(self, "Render Error", f"An error occurred during video rendering:\n{err_msg}")


if __name__ == "__main__":
    app = QApplication(sys.argv)
    window = VideoGeneratorApp()
    window.show()
    sys.exit(app.exec())

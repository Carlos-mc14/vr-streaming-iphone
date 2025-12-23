"""
VR Streaming - GUI Module
==========================
Modern graphical user interface using CustomTkinter.
Provides controls for video streaming, sensor processing, and connection management.

Author: VR Streaming Project
License: MIT
"""

import threading
import time
import json
import os
from typing import Optional, Callable
from pathlib import Path
import logging
import io

import customtkinter as ctk
from tkinter import messagebox
from PIL import Image, ImageTk
import numpy as np

logger = logging.getLogger(__name__)

# Set appearance mode
ctk.set_appearance_mode("dark")
ctk.set_default_color_theme("blue")


class StatusIndicator(ctk.CTkFrame):
    """Status indicator widget with colored dot and label."""
    
    COLORS = {
        "connected": "#22c55e",      # Green
        "connecting": "#eab308",     # Yellow
        "disconnected": "#ef4444",   # Red
        "error": "#ef4444",          # Red
        "running": "#22c55e",        # Green
        "stopped": "#6b7280",        # Gray
    }
    
    def __init__(self, master, label: str, initial_status: str = "disconnected"):
        super().__init__(master)
        
        self.configure(fg_color="transparent")
        
        # Status dot
        self.dot = ctk.CTkLabel(
            self,
            text="●",
            font=ctk.CTkFont(size=16),
            text_color=self.COLORS.get(initial_status, "#6b7280")
        )
        self.dot.pack(side="left", padx=(0, 5))
        
        # Label
        self.label = ctk.CTkLabel(
            self,
            text=label,
            font=ctk.CTkFont(size=12)
        )
        self.label.pack(side="left")
        
        # Status text
        self.status_label = ctk.CTkLabel(
            self,
            text=initial_status.capitalize(),
            font=ctk.CTkFont(size=12),
            text_color="#9ca3af"
        )
        self.status_label.pack(side="left", padx=(10, 0))
    
    def set_status(self, status: str):
        """Update status display."""
        color = self.COLORS.get(status.lower(), "#6b7280")
        self.dot.configure(text_color=color)
        self.status_label.configure(text=status.capitalize())


class MetricsPanel(ctk.CTkFrame):
    """Panel showing real-time metrics."""
    
    def __init__(self, master):
        super().__init__(master)
        
        self.configure(fg_color=("#e5e7eb", "#1f2937"))
        
        # Title
        title = ctk.CTkLabel(
            self,
            text="📊 Performance Metrics",
            font=ctk.CTkFont(size=14, weight="bold")
        )
        title.pack(pady=(10, 5), padx=10, anchor="w")
        
        # Metrics grid
        self.metrics_frame = ctk.CTkFrame(self, fg_color="transparent")
        self.metrics_frame.pack(fill="x", padx=10, pady=5)
        
        # Create metric labels
        self.metric_labels = {}
        metrics = [
            ("capture_fps", "Capture FPS"),
            ("encode_fps", "Encode FPS"),
            ("latency_ms", "Latency"),
            ("bandwidth", "Bandwidth"),
            ("frames_sent", "Frames Sent"),
            ("sensor_hz", "Sensor Rate")
        ]
        
        for i, (key, label) in enumerate(metrics):
            row = i // 2
            col = i % 2
            
            frame = ctk.CTkFrame(self.metrics_frame, fg_color="transparent")
            frame.grid(row=row, column=col, padx=10, pady=2, sticky="w")
            
            lbl = ctk.CTkLabel(
                frame,
                text=f"{label}:",
                font=ctk.CTkFont(size=11),
                text_color="#9ca3af"
            )
            lbl.pack(side="left")
            
            val = ctk.CTkLabel(
                frame,
                text="--",
                font=ctk.CTkFont(size=11, weight="bold")
            )
            val.pack(side="left", padx=(5, 0))
            
            self.metric_labels[key] = val
    
    def update_metrics(self, metrics: dict):
        """Update metric displays."""
        mapping = {
            "capture_fps": f"{metrics.get('capture_fps', 0):.1f}",
            "encode_fps": f"{metrics.get('encode_fps', 0):.1f}",
            "latency_ms": f"{metrics.get('latency_ms', 0):.1f} ms",
            "bandwidth": f"{metrics.get('bandwidth_mbps', 0):.2f} Mbps",
            "frames_sent": str(metrics.get('frames_sent', 0)),
            "sensor_hz": f"{metrics.get('sensor_hz', 0):.0f} Hz"
        }
        
        for key, value in mapping.items():
            if key in self.metric_labels:
                self.metric_labels[key].configure(text=value)


class SettingsPanel(ctk.CTkFrame):
    """Panel for configuring streaming settings."""
    
    def __init__(self, master, config: dict, on_config_change: Optional[Callable] = None):
        super().__init__(master)
        
        self.config = config
        self.on_config_change = on_config_change
        
        self.configure(fg_color=("#e5e7eb", "#1f2937"))
        
        # Title
        title = ctk.CTkLabel(
            self,
            text="⚙️ Settings",
            font=ctk.CTkFont(size=14, weight="bold")
        )
        title.pack(pady=(10, 5), padx=10, anchor="w")
        
        # Settings container
        container = ctk.CTkFrame(self, fg_color="transparent")
        container.pack(fill="x", padx=10, pady=5)
        
        # Video Quality
        self._create_slider(
            container,
            "Video Quality",
            "quality",
            1, 100,
            config.get('video', {}).get('quality', 85),
            row=0
        )
        
        # Target FPS
        self._create_slider(
            container,
            "Target FPS",
            "fps",
            30, 120,
            config.get('video', {}).get('capture_fps', 60),
            row=1
        )
        
        # Sensitivity
        self._create_slider(
            container,
            "Mouse Sensitivity",
            "sensitivity",
            0.5, 5.0,
            config.get('sensor_processing', {}).get('sensitivity', {}).get('yaw', 2.0),
            row=2
        )
        
        # Smoothing
        self._create_slider(
            container,
            "Smoothing",
            "smoothing",
            0.0, 1.0,
            config.get('sensor_processing', {}).get('smoothing', 0.3),
            row=3
        )
        
        # Connection mode
        mode_label = ctk.CTkLabel(
            container,
            text="Connection Mode:",
            font=ctk.CTkFont(size=11)
        )
        mode_label.grid(row=4, column=0, padx=5, pady=5, sticky="w")
        
        self.mode_var = ctk.StringVar(value=config.get('connection', {}).get('mode', 'wifi'))
        mode_menu = ctk.CTkOptionMenu(
            container,
            values=["usb", "wifi", "auto"],
            variable=self.mode_var,
            command=self._on_mode_change
        )
        mode_menu.grid(row=4, column=1, padx=5, pady=5, sticky="ew")
        
        # Barrel distortion toggle
        self.barrel_var = ctk.BooleanVar(
            value=config.get('stereoscopic', {}).get('barrel_distortion', {}).get('enabled', True)
        )
        barrel_check = ctk.CTkCheckBox(
            container,
            text="Barrel Distortion",
            variable=self.barrel_var,
            command=self._on_setting_change
        )
        barrel_check.grid(row=5, column=0, columnspan=2, padx=5, pady=5, sticky="w")
    
    def _create_slider(self, parent, label: str, key: str, 
                       min_val: float, max_val: float, initial: float, row: int):
        """Create a labeled slider."""
        lbl = ctk.CTkLabel(
            parent,
            text=f"{label}:",
            font=ctk.CTkFont(size=11)
        )
        lbl.grid(row=row, column=0, padx=5, pady=5, sticky="w")
        
        frame = ctk.CTkFrame(parent, fg_color="transparent")
        frame.grid(row=row, column=1, padx=5, pady=5, sticky="ew")
        
        value_label = ctk.CTkLabel(
            frame,
            text=f"{initial:.1f}",
            font=ctk.CTkFont(size=11),
            width=40
        )
        value_label.pack(side="right")
        
        slider = ctk.CTkSlider(
            frame,
            from_=min_val,
            to=max_val,
            command=lambda v: self._on_slider_change(key, v, value_label)
        )
        slider.set(initial)
        slider.pack(side="left", fill="x", expand=True, padx=(0, 5))
        
        setattr(self, f"slider_{key}", slider)
        setattr(self, f"value_{key}", value_label)
    
    def _on_slider_change(self, key: str, value: float, label: ctk.CTkLabel):
        """Handle slider change."""
        label.configure(text=f"{value:.1f}")
        self._on_setting_change()
    
    def _on_mode_change(self, value: str):
        """Handle connection mode change."""
        self._on_setting_change()
    
    def _on_setting_change(self):
        """Notify of setting changes."""
        if self.on_config_change:
            settings = self.get_settings()
            self.on_config_change(settings)
    
    def get_settings(self) -> dict:
        """Get current settings."""
        quality = self.slider_quality.get() if hasattr(self, 'slider_quality') and self.slider_quality else 85
        fps = self.slider_fps.get() if hasattr(self, 'slider_fps') and self.slider_fps else 60
        sensitivity = self.slider_sensitivity.get() if hasattr(self, 'slider_sensitivity') and self.slider_sensitivity else 2.0
        smoothing = self.slider_smoothing.get() if hasattr(self, 'slider_smoothing') and self.slider_smoothing else 0.3
        return {
            'quality': int(quality),
            'fps': int(fps),
            'sensitivity': sensitivity,
            'smoothing': smoothing,
            'mode': self.mode_var.get(),
            'barrel_distortion': self.barrel_var.get()
        }


class VRStreamingGUI(ctk.CTk):
    """Main application window."""
    
    def __init__(self, config_path: str = "config.json"):
        super().__init__()
        
        self.title("VR Streaming - PC to iPhone")
        self.geometry("800x600")
        self.minsize(700, 500)
        
        # Load config
        self.config_path = config_path
        self.config = self._load_config()
        
        # Callbacks
        self._on_start_callback: Optional[Callable] = None
        self._on_stop_callback: Optional[Callable] = None
        self._on_settings_change_callback: Optional[Callable] = None
        
        # State
        self.is_streaming = False
        
        # Create UI
        self._create_widgets()
        
        # Start metrics update timer
        self._update_id = None
        self._start_metrics_timer()
    
    def _load_config(self) -> dict:
        """Load configuration from file."""
        try:
            config_file = Path(self.config_path)
            if config_file.exists():
                with open(config_file, 'r') as f:
                    return json.load(f)
        except Exception as e:
            logger.error(f"Failed to load config: {e}")
        
        # Return default config
        return {
            "video": {"quality": 85, "capture_fps": 60},
            "stereoscopic": {"barrel_distortion": {"enabled": True}},
            "connection": {"mode": "wifi"},
            "sensor_processing": {"sensitivity": {"yaw": 2.0}, "smoothing": 0.3}
        }
    
    def _save_config(self):
        """Save configuration to file."""
        try:
            with open(self.config_path, 'w') as f:
                json.dump(self.config, f, indent=4)
        except Exception as e:
            logger.error(f"Failed to save config: {e}")
    
    def _create_widgets(self):
        """Create all UI widgets."""
        # Main container with grid layout
        self.grid_columnconfigure(0, weight=1)
        self.grid_rowconfigure(1, weight=1)
        
        # Header
        self._create_header()
        
        # Main content area
        content = ctk.CTkFrame(self, fg_color="transparent")
        content.grid(row=1, column=0, sticky="nsew", padx=10, pady=5)
        content.grid_columnconfigure(0, weight=2)
        content.grid_columnconfigure(1, weight=1)
        content.grid_rowconfigure(0, weight=1)
        
        # Left panel - Preview and controls
        left_panel = ctk.CTkFrame(content, fg_color="transparent")
        left_panel.grid(row=0, column=0, sticky="nsew", padx=(0, 5))
        left_panel.grid_rowconfigure(0, weight=1)
        left_panel.grid_columnconfigure(0, weight=1)
        
        # Preview area
        self._create_preview_area(left_panel)
        
        # Control buttons
        self._create_controls(left_panel)
        
        # Right panel - Settings and metrics
        right_panel = ctk.CTkFrame(content, fg_color="transparent")
        right_panel.grid(row=0, column=1, sticky="nsew", padx=(5, 0))
        right_panel.grid_columnconfigure(0, weight=1)
        
        # Status indicators
        self._create_status_panel(right_panel)
        
        # Metrics panel
        self.metrics_panel = MetricsPanel(right_panel)
        self.metrics_panel.pack(fill="x", pady=(10, 0))
        
        # Settings panel
        self.settings_panel = SettingsPanel(
            right_panel,
            self.config,
            on_config_change=self._on_settings_changed
        )
        self.settings_panel.pack(fill="x", pady=(10, 0))
        
        # Footer with log
        self._create_footer()
    
    def _create_header(self):
        """Create header section."""
        header = ctk.CTkFrame(self, fg_color=("#d1d5db", "#374151"), corner_radius=0)
        header.grid(row=0, column=0, sticky="ew")
        
        # Logo/Title
        title = ctk.CTkLabel(
            header,
            text="🥽 VR Streaming",
            font=ctk.CTkFont(size=20, weight="bold")
        )
        title.pack(side="left", padx=15, pady=10)
        
        # Version
        version = ctk.CTkLabel(
            header,
            text="v1.0.0",
            font=ctk.CTkFont(size=11),
            text_color="#9ca3af"
        )
        version.pack(side="left", pady=10)
        
        # Theme toggle
        theme_btn = ctk.CTkButton(
            header,
            text="🌙",
            width=30,
            height=30,
            command=self._toggle_theme
        )
        theme_btn.pack(side="right", padx=15, pady=10)
    
    def _create_preview_area(self, parent):
        """Create video preview area."""
        preview_frame = ctk.CTkFrame(parent, fg_color=("#1f2937", "#111827"))
        preview_frame.grid(row=0, column=0, sticky="nsew", pady=(0, 10))
        preview_frame.grid_columnconfigure(0, weight=1)
        preview_frame.grid_rowconfigure(0, weight=1)
        
        # Preview canvas for displaying images
        self.preview_canvas = ctk.CTkLabel(
            preview_frame,
            text="📺 Video Preview\n(Start streaming to see preview)",
            font=ctk.CTkFont(size=14),
            text_color="#6b7280"
        )
        self.preview_canvas.grid(row=0, column=0, sticky="nsew", padx=10, pady=10)
        
        # Store reference to photo to prevent garbage collection
        self._preview_photo = None
        self._last_preview_update = 0
    
    def _create_controls(self, parent):
        """Create control buttons."""
        controls = ctk.CTkFrame(parent, fg_color="transparent")
        controls.grid(row=1, column=0, sticky="ew")
        
        # Start/Stop button
        self.start_btn = ctk.CTkButton(
            controls,
            text="▶ Start Streaming",
            font=ctk.CTkFont(size=14, weight="bold"),
            height=40,
            fg_color="#22c55e",
            hover_color="#16a34a",
            command=self._toggle_streaming
        )
        self.start_btn.pack(side="left", padx=(0, 10))
        
        # Recenter button
        self.recenter_btn = ctk.CTkButton(
            controls,
            text="🎯 Recenter",
            height=40,
            command=self._recenter
        )
        self.recenter_btn.pack(side="left", padx=(0, 10))
        
        # Settings button
        settings_btn = ctk.CTkButton(
            controls,
            text="💾 Save Settings",
            height=40,
            fg_color="#6366f1",
            hover_color="#4f46e5",
            command=self._save_settings
        )
        settings_btn.pack(side="right")
    
    def _create_status_panel(self, parent):
        """Create status indicators panel."""
        status_frame = ctk.CTkFrame(parent, fg_color=("#e5e7eb", "#1f2937"))
        status_frame.pack(fill="x")
        
        # Title
        title = ctk.CTkLabel(
            status_frame,
            text="📡 Status",
            font=ctk.CTkFont(size=14, weight="bold")
        )
        title.pack(pady=(10, 5), padx=10, anchor="w")
        
        # Status indicators
        self.capture_status = StatusIndicator(status_frame, "Screen Capture", "stopped")
        self.capture_status.pack(pady=2, padx=10, anchor="w")
        
        self.connection_status = StatusIndicator(status_frame, "Connection", "disconnected")
        self.connection_status.pack(pady=2, padx=10, anchor="w")
        
        self.sensor_status = StatusIndicator(status_frame, "Sensors", "disconnected")
        self.sensor_status.pack(pady=(2, 10), padx=10, anchor="w")
    
    def _create_footer(self):
        """Create footer with log output."""
        footer = ctk.CTkFrame(self, fg_color=("#e5e7eb", "#1f2937"))
        footer.grid(row=2, column=0, sticky="ew", padx=10, pady=10)
        
        # Log label
        log_label = ctk.CTkLabel(
            footer,
            text="📋 Log",
            font=ctk.CTkFont(size=12, weight="bold")
        )
        log_label.pack(anchor="w", padx=10, pady=(5, 0))
        
        # Log text box
        self.log_text = ctk.CTkTextbox(
            footer,
            height=80,
            font=ctk.CTkFont(family="Consolas", size=10)
        )
        self.log_text.pack(fill="x", padx=10, pady=5)
        
        self.log("VR Streaming ready. Click 'Start Streaming' to begin.")
    
    def _toggle_theme(self):
        """Toggle between light and dark theme."""
        current = ctk.get_appearance_mode()
        new_mode = "Light" if current == "Dark" else "Dark"
        ctk.set_appearance_mode(new_mode)
    
    def _toggle_streaming(self):
        """Start or stop streaming."""
        if self.is_streaming:
            self._stop_streaming()
        else:
            self._start_streaming()
    
    def _start_streaming(self):
        """Start streaming."""
        self.is_streaming = True
        self.start_btn.configure(
            text="⏹ Stop Streaming",
            fg_color="#ef4444",
            hover_color="#dc2626"
        )
        self.capture_status.set_status("running")
        self.connection_status.set_status("connecting")
        self.log("Starting streaming...")
        
        if self._on_start_callback:
            self._on_start_callback()
    
    def _stop_streaming(self):
        """Stop streaming."""
        self.is_streaming = False
        self.start_btn.configure(
            text="▶ Start Streaming",
            fg_color="#22c55e",
            hover_color="#16a34a"
        )
        self.capture_status.set_status("stopped")
        self.connection_status.set_status("disconnected")
        self.sensor_status.set_status("disconnected")
        self.log("Streaming stopped.")
        
        if self._on_stop_callback:
            self._on_stop_callback()
    
    def _recenter(self):
        """Recenter head tracking."""
        self.log("Recentering head tracking...")
        # This would call the sensor processor's reset
    
    def _save_settings(self):
        """Save current settings."""
        settings = self.settings_panel.get_settings()
        
        # Update config
        self.config['video']['quality'] = settings['quality']
        self.config['video']['capture_fps'] = settings['fps']
        self.config['sensor_processing']['sensitivity']['yaw'] = settings['sensitivity']
        self.config['sensor_processing']['smoothing'] = settings['smoothing']
        self.config['connection']['mode'] = settings['mode']
        self.config['stereoscopic']['barrel_distortion']['enabled'] = settings['barrel_distortion']
        
        self._save_config()
        self.log("Settings saved successfully.")
        messagebox.showinfo("Settings", "Settings saved successfully!")
    
    def _on_settings_changed(self, settings: dict):
        """Handle settings change."""
        if self._on_settings_change_callback:
            self._on_settings_change_callback(settings)
    
    def _start_metrics_timer(self):
        """Start timer for updating metrics."""
        self._update_metrics()
    
    def _update_metrics(self):
        """Update metrics display periodically."""
        # This would normally get real metrics from the streaming components
        # For now, show placeholder values when streaming
        if self.is_streaming:
            # Placeholder metrics - would be replaced with real values
            self.metrics_panel.update_metrics({
                'capture_fps': 60.0,
                'encode_fps': 60.0,
                'latency_ms': 16.5,
                'bandwidth_mbps': 25.4,
                'frames_sent': 1234,
                'sensor_hz': 60
            })
        
        # Schedule next update
        self._update_id = self.after(500, self._update_metrics)
    
    def log(self, message: str):
        """Add message to log."""
        timestamp = time.strftime("%H:%M:%S")
        self.log_text.insert("end", f"[{timestamp}] {message}\n")
        self.log_text.see("end")
    
    def update_metrics(self, metrics: dict):
        """Update metrics display with real data."""
        self.metrics_panel.update_metrics(metrics)
    
    def update_preview(self, frame: np.ndarray):
        """Update preview with a new frame (numpy array in BGR format)."""
        try:
            current_time = time.time()
            # Limit preview updates to 15 FPS to save CPU
            if current_time - self._last_preview_update < 0.066:
                return
            self._last_preview_update = current_time
            
            # Convert BGR to RGB
            if len(frame.shape) == 3 and frame.shape[2] == 3:
                frame_rgb = frame[:, :, ::-1]  # BGR to RGB
            else:
                frame_rgb = frame
            
            # Resize to fit preview (max 400px width)
            h, w = frame_rgb.shape[:2]
            max_width = 400
            if w > max_width:
                scale = max_width / w
                new_w = int(w * scale)
                new_h = int(h * scale)
                pil_image = Image.fromarray(frame_rgb)
                pil_image = pil_image.resize((new_w, new_h), Image.Resampling.LANCZOS)
            else:
                pil_image = Image.fromarray(frame_rgb)
            
            # Create PhotoImage and update label
            self._preview_photo = ImageTk.PhotoImage(pil_image)
            self.preview_canvas.configure(image=self._preview_photo, text="")
        except Exception as e:
            logger.error(f"Preview update error: {e}")
    
    def set_connection_status(self, status: str):
        """Update connection status indicator."""
        self.connection_status.set_status(status)
        if status == "connected":
            self.sensor_status.set_status("running")
    
    def set_on_start(self, callback: Callable):
        """Set callback for start button."""
        self._on_start_callback = callback
    
    def set_on_stop(self, callback: Callable):
        """Set callback for stop button."""
        self._on_stop_callback = callback
    
    def set_on_settings_change(self, callback: Callable):
        """Set callback for settings changes."""
        self._on_settings_change_callback = callback
    
    def destroy(self):
        """Clean up on window close."""
        if self._update_id:
            self.after_cancel(self._update_id)
        super().destroy()


# Test function
if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO)
    
    app = VRStreamingGUI()
    
    def on_start():
        print("Streaming started!")
    
    def on_stop():
        print("Streaming stopped!")
    
    def on_settings(settings):
        print(f"Settings changed: {settings}")
    
    app.set_on_start(on_start)
    app.set_on_stop(on_stop)
    app.set_on_settings_change(on_settings)
    
    app.mainloop()

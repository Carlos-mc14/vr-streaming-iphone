"""
VR Streaming - Main Application
================================
Main entry point that integrates all modules:
- Screen capture
- Video encoding
- USB/WiFi server
- Sensor processing
- GUI

Author: VR Streaming Project
License: MIT
"""

import sys
import os
import json
import time
import threading
import logging
from pathlib import Path
from typing import Optional
import signal

# Add current directory to path
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

# Import modules
from screen_capture import ScreenCapture, StereoConverter
from video_encoder import VideoEncoder, EncoderType
from usb_server import USBServer, ConnectionMode, ConnectionState
from sensor_processor import SensorProcessor, HeadTracker
from gui import VRStreamingGUI
from http_server import HTTPStreamServer
from usb_tunnel import USBTunnel, get_local_ip, check_usb_dependencies

# Configure logging
def setup_logging(log_level: str = "INFO", save_logs: bool = True):
    """Configure application logging."""
    log_format = "%(asctime)s [%(levelname)s] %(name)s: %(message)s"
    date_format = "%Y-%m-%d %H:%M:%S"
    
    handlers: list[logging.Handler] = [logging.StreamHandler()]
    
    if save_logs:
        log_dir = Path("logs")
        log_dir.mkdir(exist_ok=True)
        log_file = log_dir / f"vr_streaming_{time.strftime('%Y%m%d_%H%M%S')}.log"
        handlers.append(logging.FileHandler(log_file))
    
    logging.basicConfig(
        level=getattr(logging, log_level.upper(), logging.INFO),
        format=log_format,
        datefmt=date_format,
        handlers=handlers
    )
    
    # Reduce noise from third-party libraries
    logging.getLogger("PIL").setLevel(logging.WARNING)
    logging.getLogger("urllib3").setLevel(logging.WARNING)

logger = logging.getLogger(__name__)


def get_app_path() -> Path:
    """Get the path to the application directory (works with PyInstaller)."""
    if getattr(sys, 'frozen', False):
        # Running as compiled executable
        return Path(sys.executable).parent
    else:
        # Running as script
        return Path(__file__).parent


class VRStreamingApp:
    """
    Main VR Streaming Application.
    Coordinates all components and manages the streaming pipeline.
    """
    
    def __init__(self, config_path: str = "config.json"):
        """
        Initialize the VR Streaming application.
        
        Args:
            config_path: Path to configuration file
        """
        # Look for config in the app directory (not the bundled resources)
        app_dir = get_app_path()
        self.config_path = app_dir / config_path
        self.config = self._load_config()
        
        # Setup logging
        debug_config = self.config.get('debug', {})
        setup_logging(
            log_level=debug_config.get('log_level', 'INFO'),
            save_logs=debug_config.get('save_logs', True)
        )
        
        logger.info("=" * 50)
        logger.info("VR Streaming Application Starting")
        logger.info("=" * 50)
        
        # Components (initialized lazily)
        self.screen_capture: Optional[ScreenCapture] = None
        self.stereo_converter: Optional[StereoConverter] = None
        self.video_encoder: Optional[VideoEncoder] = None
        self.usb_server: Optional[USBServer] = None
        self.usb_tunnel: Optional[USBTunnel] = None
        self.sensor_processor: Optional[SensorProcessor] = None
        self.head_tracker: Optional[HeadTracker] = None
        self.gui: Optional[VRStreamingGUI] = None
        self.http_server: Optional[HTTPStreamServer] = None
        
        # State
        self.is_running = False
        self._streaming_thread: Optional[threading.Thread] = None
        self._stop_event = threading.Event()
        
        # Metrics
        self._metrics_lock = threading.Lock()
        self._metrics = {
            'capture_fps': 0,
            'encode_fps': 0,
            'latency_ms': 0,
            'bandwidth_mbps': 0,
            'frames_sent': 0,
            'sensor_hz': 0
        }
        self._last_sensor_time = time.time()
        self._sensor_count = 0
    
    def _load_config(self) -> dict:
        """Load configuration from file."""
        default_config = {
            "video": {
                "capture_fps": 60,
                "output_resolution": {"width": 1920, "height": 1080},
                "quality": 85,
                "encoder": "jpeg",
                "use_dxcam": True,
                "monitor_index": 0
            },
            "stereoscopic": {
                "enabled": True,
                "eye_separation": 63.0,
                "fov": 100,
                "barrel_distortion": {
                    "enabled": True,
                    "k1": 0.22,
                    "k2": 0.24
                }
            },
            "connection": {
                "mode": "wifi",
                "usb_port": 8889,
                "wifi_host": "0.0.0.0",
                "wifi_port": 8889,
                "buffer_size": 65536,
                "enable_usb_tunnel": False
            },
            "sensor_processing": {
                "sensitivity": {"yaw": 2.0, "pitch": 1.5, "roll": 1.0},
                "smoothing": 0.3,
                "deadzone": 0.02,
                "invert_x": False,
                "invert_y": False
            },
            "performance": {
                "capture_threads": 2,
                "encode_threads": 2,
                "max_queue_size": 5,
                "target_latency_ms": 16
            },
            "debug": {
                "show_fps": True,
                "show_latency": True,
                "log_level": "INFO",
                "save_logs": True
            }
        }
        
        try:
            if self.config_path.exists():
                with open(self.config_path, 'r', encoding='utf-8') as f:
                    config = json.load(f)
                    logger.info(f"Configuration loaded from {self.config_path}")
                    return config
            else:
                # Create default config file if it doesn't exist
                logger.info(f"Creating default config at {self.config_path}")
                with open(self.config_path, 'w', encoding='utf-8') as f:
                    json.dump(default_config, f, indent=4)
                return default_config
        except Exception as e:
            logger.error(f"Failed to load config: {e}")
        
        return default_config
    
    def _save_config(self):
        """Save current configuration."""
        try:
            with open(self.config_path, 'w', encoding='utf-8') as f:
                json.dump(self.config, f, indent=4)
            logger.info(f"Configuration saved to {self.config_path}")
        except Exception as e:
            logger.error(f"Failed to save config: {e}")
    
    def _initialize_components(self):
        """Initialize all streaming components."""
        video_config = self.config.get('video', {})
        stereo_config = self.config.get('stereoscopic', {})
        conn_config = self.config.get('connection', {})
        sensor_config = self.config.get('sensor_processing', {})
        perf_config = self.config.get('performance', {})
        
        resolution = (
            video_config.get('output_resolution', {}).get('width', 1920),
            video_config.get('output_resolution', {}).get('height', 1080)
        )
        
        # Screen capture
        logger.info("Initializing screen capture...")
        self.screen_capture = ScreenCapture(
            target_fps=video_config.get('capture_fps', 60),
            resolution=resolution,
            monitor_index=video_config.get('monitor_index', 0),
            use_dxcam=video_config.get('use_dxcam', True),
            max_queue_size=perf_config.get('max_queue_size', 5)
        )
        
        # Stereo converter
        logger.info("Initializing stereo converter...")
        barrel_config = stereo_config.get('barrel_distortion', {})
        self.stereo_converter = StereoConverter(
            output_resolution=resolution,
            eye_separation=stereo_config.get('eye_separation', 63.0),
            fov=stereo_config.get('fov', 100),
            barrel_distortion=barrel_config.get('enabled', True),
            k1=barrel_config.get('k1', 0.22),
            k2=barrel_config.get('k2', 0.24)
        )
        
        # Video encoder
        logger.info("Initializing video encoder...")
        encoder_type = EncoderType.JPEG if video_config.get('encoder', 'jpeg') == 'jpeg' else EncoderType.H264
        self.video_encoder = VideoEncoder(
            encoder_type=encoder_type,
            quality=video_config.get('quality', 85),
            resolution=resolution,
            fps=video_config.get('capture_fps', 60),
            max_queue_size=perf_config.get('max_queue_size', 5)
        )
        
        # USB/WiFi server
        logger.info("Initializing server...")
        mode_str = conn_config.get('mode', 'usb')
        mode = ConnectionMode.USB if mode_str == 'usb' else (
            ConnectionMode.WIFI if mode_str == 'wifi' else ConnectionMode.AUTO
        )
        self.usb_server = USBServer(
            mode=mode,
            usb_port=conn_config.get('usb_port', 8889),
            wifi_host=conn_config.get('wifi_host', '0.0.0.0'),
            wifi_port=conn_config.get('wifi_port', 8889),
            buffer_size=conn_config.get('buffer_size', 65536)
        )
        
        # USB Tunnel for direct USB cable connection
        if conn_config.get('enable_usb_tunnel', True):
            logger.info("Initializing USB tunnel...")
            self.usb_tunnel = USBTunnel(
                local_port=conn_config.get('wifi_port', 8889),
                on_device_connected=self._on_usb_device_connected,
                on_device_disconnected=self._on_usb_device_disconnected,
                on_tunnel_ready=self._on_usb_tunnel_ready
            )
        
        # Sensor processor
        logger.info("Initializing sensor processor...")
        self.sensor_processor = SensorProcessor(
            sensitivity=sensor_config.get('sensitivity', {'yaw': 2.0, 'pitch': 1.5, 'roll': 1.0}),
            smoothing=sensor_config.get('smoothing', 0.3),
            deadzone=sensor_config.get('deadzone', 0.02),
            invert_x=sensor_config.get('invert_x', False),
            invert_y=sensor_config.get('invert_y', False)
        )
        
        # Head tracker
        self.head_tracker = HeadTracker(
            processor=self.sensor_processor,
            update_rate=60
        )
        
        # HTTP Server for web preview
        logger.info("Initializing HTTP server...")
        self.http_server = HTTPStreamServer(port=conn_config.get('wifi_port', 8889))
        
        # Set up callbacks
        self._setup_callbacks()
        
        logger.info("All components initialized")
    
    def _setup_callbacks(self):
        """Set up inter-component callbacks."""
        # Server connection callbacks
        def on_connect():
            logger.info("Client connected")
            if self.gui:
                self.gui.set_connection_status("connected")
                self.gui.log("iOS device connected!")
        
        def on_disconnect():
            logger.info("Client disconnected")
            if self.gui:
                self.gui.set_connection_status("disconnected")
                self.gui.log("iOS device disconnected")
        
        def on_state_change(state: ConnectionState):
            if self.gui:
                self.gui.set_connection_status(state.value)
        
        def on_sensor_data(sensor_data):
            # Process sensor data
            self.sensor_processor.process_sensor_data(sensor_data)
            
            # Update sensor rate metric
            self._sensor_count += 1
            current_time = time.time()
            if current_time - self._last_sensor_time >= 1.0:
                with self._metrics_lock:
                    self._metrics['sensor_hz'] = self._sensor_count
                self._sensor_count = 0
                self._last_sensor_time = current_time
        
        self.usb_server.set_on_connect(on_connect)
        self.usb_server.set_on_disconnect(on_disconnect)
        self.usb_server.set_on_state_change(on_state_change)
        self.usb_server.set_on_sensor_data(on_sensor_data)
    
    def _on_usb_device_connected(self, device):
        """Called when iOS device is connected via USB."""
        logger.info(f"USB device connected: {device.name} ({device.model})")
        if self.gui:
            self.gui.log(f"📱 USB device detected: {device.name}")
            self.gui.log(f"   Model: {device.model}, iOS: {device.ios_version}")
    
    def _on_usb_device_disconnected(self):
        """Called when iOS device is disconnected."""
        logger.info("USB device disconnected")
        if self.gui:
            self.gui.log("📱 USB device disconnected")
    
    def _on_usb_tunnel_ready(self, host: str, port: int):
        """Called when USB tunnel is established."""
        logger.info(f"USB tunnel ready at {host}:{port}")
        if self.gui:
            self.gui.log(f"✅ USB tunnel active!")
            self.gui.log(f"   iPhone should connect to: 127.0.0.1:{port}")
    
    def _streaming_loop(self):
        """Main streaming loop running in background thread."""
        logger.info("Streaming loop started")
        
        frame_count = 0
        sent_count = 0
        start_time = time.time()
        last_metrics_update = time.time()
        last_preview_update = time.time()
        last_log_time = time.time()
        
        while not self._stop_event.is_set():
            try:
                # Get captured frame
                frame = self.screen_capture.get_frame(timeout=0.05)
                
                if frame is not None:
                    frame_count += 1
                    
                    # Convert to stereoscopic
                    if self.config.get('stereoscopic', {}).get('enabled', True):
                        stereo_frame = self.stereo_converter.convert_to_stereo(frame)
                    else:
                        stereo_frame = frame
                    
                    # Encode frame
                    encoded = self.video_encoder.encode_immediate(stereo_frame)
                    
                    if encoded:
                        # Send to client - send only the JPEG data, not the full frame header
                        # The usb_server.send_frame() adds its own VRVI header
                        if self.usb_server.is_connected:
                            if self.usb_server.send_frame(encoded.data):
                                sent_count += 1
                        
                        # Update HTTP server with latest frame
                        if self.http_server:
                            self.http_server.set_frame(encoded.data)
                    
                    # Update GUI preview (throttled to ~15 FPS)
                    current_time = time.time()
                    if current_time - last_preview_update >= 0.066:
                        if self.gui:
                            try:
                                self.gui.update_preview(stereo_frame)
                            except Exception:
                                pass  # GUI might be closed
                        last_preview_update = current_time
                
                # Log stats every 5 seconds
                current_time = time.time()
                if current_time - last_log_time >= 5.0:
                    elapsed = current_time - start_time
                    logger.info(f"Streaming stats: {frame_count} frames captured, {sent_count} sent, {frame_count/elapsed:.1f} FPS avg")
                    last_log_time = current_time
                
                # Update metrics periodically
                if current_time - last_metrics_update >= 0.5:
                    self._update_metrics(frame_count, start_time)
                    last_metrics_update = current_time
                    
                    # Update GUI and HTTP server metrics
                    if self.gui:
                        self.gui.update_metrics(self._metrics.copy())
                    if self.http_server:
                        self.http_server.set_metrics(self._metrics.copy())
                
            except Exception as e:
                logger.error(f"Streaming loop error: {e}", exc_info=True)
                time.sleep(0.01)
        
        logger.info(f"Streaming loop stopped. Total: {frame_count} frames captured, {sent_count} sent")
    
    def _update_metrics(self, frame_count: int, start_time: float):
        """Update performance metrics."""
        with self._metrics_lock:
            # Get metrics from components
            if self.screen_capture:
                capture_metrics = self.screen_capture.get_metrics()
                self._metrics['capture_fps'] = capture_metrics.get('fps', 0)
            
            if self.video_encoder:
                encoder_metrics = self.video_encoder.get_metrics()
                self._metrics['encode_fps'] = encoder_metrics.get('encode_fps', 0)
            
            if self.usb_server:
                server_metrics = self.usb_server.get_metrics()
                self._metrics['frames_sent'] = server_metrics.get('frames_sent', 0)
                self._metrics['bandwidth_mbps'] = server_metrics.get('send_mbps', 0)
            
            # Estimate latency (capture to send)
            encode_fps = self._metrics.get('encode_fps', 1)
            if isinstance(encode_fps, (int, float)) and encode_fps > 0:
                self._metrics['latency_ms'] = 1000.0 / encode_fps
            else:
                self._metrics['latency_ms'] = 1000.0
    
    def start_streaming(self):
        """Start the streaming pipeline."""
        if self.is_running:
            logger.warning("Streaming already running")
            return
        
        logger.info("Starting streaming pipeline...")
        
        try:
            # Initialize components if needed
            if not self.screen_capture:
                self._initialize_components()
            
            # Start all components
            self.screen_capture.start()
            self.video_encoder.start()
            self.usb_server.start()
            self.head_tracker.start()
            if self.http_server:
                self.http_server.start()
            
            # Start USB tunnel for direct cable connection
            if self.usb_tunnel:
                self.usb_tunnel.start()
                logger.info("USB tunnel monitoring started")
            
            # Start streaming loop
            self._stop_event.clear()
            self._streaming_thread = threading.Thread(
                target=self._streaming_loop,
                name="StreamingThread",
                daemon=True
            )
            self._streaming_thread.start()
            
            self.is_running = True
            logger.info("Streaming pipeline started")
            
            if self.gui:
                port = self.config['connection'].get('wifi_port', 8889)
                local_ip = get_local_ip()
                self.gui.log(f"Server listening on port {port}")
                self.gui.log(f"")
                self.gui.log(f"📡 Connection Options:")
                self.gui.log(f"   USB: Connect iPhone via USB-C, use 127.0.0.1:{port}")
                self.gui.log(f"   WiFi: Use {local_ip}:{port}")
                self.gui.log(f"")
                self.gui.log(f"🌐 Web preview: http://localhost:{port}")
                self.gui.log(f"   VR mode: http://localhost:{port}/vr")
            
        except Exception as e:
            logger.error(f"Failed to start streaming: {e}")
            self.stop_streaming()
            raise
    
    def stop_streaming(self):
        """Stop the streaming pipeline."""
        if not self.is_running:
            return
        
        logger.info("Stopping streaming pipeline...")
        
        # Signal stop
        self._stop_event.set()
        
        # Wait for streaming thread
        if self._streaming_thread:
            self._streaming_thread.join(timeout=2.0)
            self._streaming_thread = None
        
        # Stop components
        if self.usb_tunnel:
            self.usb_tunnel.stop()
        
        if self.http_server:
            self.http_server.stop()
        
        if self.head_tracker:
            self.head_tracker.stop()
        
        if self.usb_server:
            self.usb_server.stop()
        
        if self.video_encoder:
            self.video_encoder.stop()
        
        if self.screen_capture:
            self.screen_capture.stop()
        
        self.is_running = False
        logger.info("Streaming pipeline stopped")
    
    def update_settings(self, settings: dict):
        """Update settings during runtime."""
        logger.info(f"Updating settings: {settings}")
        
        # Update config
        if 'quality' in settings:
            self.config['video']['quality'] = settings['quality']
            if self.video_encoder:
                self.video_encoder.set_quality(settings['quality'])
        
        if 'sensitivity' in settings:
            self.config['sensor_processing']['sensitivity']['yaw'] = settings['sensitivity']
            if self.sensor_processor:
                self.sensor_processor.set_sensitivity(yaw=settings['sensitivity'])
        
        if 'smoothing' in settings:
            self.config['sensor_processing']['smoothing'] = settings['smoothing']
            if self.sensor_processor:
                self.sensor_processor.set_smoothing(settings['smoothing'])
        
        if 'barrel_distortion' in settings:
            self.config['stereoscopic']['barrel_distortion']['enabled'] = settings['barrel_distortion']
            # Would need to reinitialize stereo converter
    
    def recenter_tracking(self):
        """Recenter head tracking."""
        if self.sensor_processor:
            self.sensor_processor.reset_reference()
            logger.info("Head tracking recentered")
    
    def run_gui(self):
        """Run the application with GUI."""
        logger.info("Starting GUI...")
        
        self.gui = VRStreamingGUI(config_path=str(self.config_path))
        
        # Set up GUI callbacks
        self.gui.set_on_start(self.start_streaming)
        self.gui.set_on_stop(self.stop_streaming)
        self.gui.set_on_settings_change(self.update_settings)
        
        # Handle window close
        def on_closing():
            self.stop_streaming()
            self.gui.destroy()
        
        self.gui.protocol("WM_DELETE_WINDOW", on_closing)
        
        # Run GUI main loop
        self.gui.mainloop()
    
    def run_headless(self):
        """Run the application without GUI (headless mode)."""
        logger.info("Starting in headless mode...")
        
        # Initialize and start streaming
        self._initialize_components()
        self.start_streaming()
        
        # Set up signal handlers
        def signal_handler(signum, frame):
            logger.info("Received signal, stopping...")
            self.stop_streaming()
            sys.exit(0)
        
        signal.signal(signal.SIGINT, signal_handler)
        signal.signal(signal.SIGTERM, signal_handler)
        
        # Keep running
        logger.info("Running... Press Ctrl+C to stop")
        
        try:
            while self.is_running:
                time.sleep(1)
                
                # Print status periodically
                with self._metrics_lock:
                    status = (
                        f"FPS: {self._metrics['capture_fps']:.1f} | "
                        f"Sent: {self._metrics['frames_sent']} | "
                        f"BW: {self._metrics['bandwidth_mbps']:.2f} Mbps | "
                        f"Sensors: {self._metrics['sensor_hz']} Hz"
                    )
                    print(f"\r{status}", end="", flush=True)
        except KeyboardInterrupt:
            pass
        finally:
            self.stop_streaming()


def main():
    """Main entry point."""
    import argparse
    
    parser = argparse.ArgumentParser(description="VR Streaming - PC to iPhone")
    parser.add_argument(
        '--headless', '-H',
        action='store_true',
        help='Run without GUI'
    )
    parser.add_argument(
        '--config', '-c',
        type=str,
        default='config.json',
        help='Path to configuration file'
    )
    parser.add_argument(
        '--port', '-p',
        type=int,
        help='Override server port'
    )
    parser.add_argument(
        '--mode', '-m',
        choices=['usb', 'wifi', 'auto'],
        help='Connection mode'
    )
    
    args = parser.parse_args()
    
    # Create application
    app = VRStreamingApp(config_path=args.config)
    
    # Apply command line overrides
    if args.port:
        app.config['connection']['wifi_port'] = args.port
        app.config['connection']['usb_port'] = args.port
    
    if args.mode:
        app.config['connection']['mode'] = args.mode
    
    # Run application
    try:
        if args.headless:
            app.run_headless()
        else:
            app.run_gui()
    except Exception as e:
        logger.error(f"Application error: {e}")
        raise


if __name__ == "__main__":
    main()

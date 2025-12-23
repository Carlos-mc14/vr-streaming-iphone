"""
VR Streaming - HTTP Server Module
===================================
Provides HTTP server for web-based preview and mobile browser access.

Author: VR Streaming Project
License: MIT
"""

import threading
import time
import io
import logging
from http.server import HTTPServer, BaseHTTPRequestHandler
from typing import Optional, Callable
import json

logger = logging.getLogger(__name__)


class StreamingHTTPHandler(BaseHTTPRequestHandler):
    """HTTP handler for streaming video and serving web interface."""
    
    # Class-level variables set by HTTPStreamServer
    get_frame_callback: Optional[Callable] = None
    get_metrics_callback: Optional[Callable] = None
    
    def log_message(self, format, *args):
        """Suppress default logging."""
        pass
    
    def do_GET(self):
        """Handle GET requests."""
        if self.path == '/' or self.path == '/index.html':
            self._serve_index()
        elif self.path == '/stream':
            self._serve_mjpeg_stream()
        elif self.path == '/frame':
            self._serve_single_frame()
        elif self.path == '/metrics':
            self._serve_metrics()
        elif self.path == '/vr':
            self._serve_vr_page()
        else:
            self.send_error(404, 'Not Found')
    
    def _serve_index(self):
        """Serve the main index page."""
        html = '''<!DOCTYPE html>
<html lang="en">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>VR Streaming - Preview</title>
    <style>
        * { margin: 0; padding: 0; box-sizing: border-box; }
        body { 
            font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, sans-serif;
            background: linear-gradient(135deg, #1a1a2e 0%, #16213e 100%);
            color: #fff;
            min-height: 100vh;
            padding: 20px;
        }
        .container { max-width: 1200px; margin: 0 auto; }
        h1 { 
            text-align: center; 
            margin-bottom: 20px;
            font-size: 2em;
        }
        .preview-container {
            background: #0f0f23;
            border-radius: 16px;
            padding: 20px;
            margin-bottom: 20px;
            box-shadow: 0 10px 40px rgba(0,0,0,0.3);
        }
        #preview {
            width: 100%;
            max-width: 960px;
            height: auto;
            border-radius: 8px;
            display: block;
            margin: 0 auto;
            background: #000;
        }
        .metrics {
            display: grid;
            grid-template-columns: repeat(auto-fit, minmax(150px, 1fr));
            gap: 15px;
            margin-top: 20px;
        }
        .metric-card {
            background: rgba(255,255,255,0.1);
            padding: 15px;
            border-radius: 10px;
            text-align: center;
        }
        .metric-value {
            font-size: 2em;
            font-weight: bold;
            color: #4ade80;
        }
        .metric-label {
            font-size: 0.9em;
            color: #9ca3af;
            margin-top: 5px;
        }
        .buttons {
            text-align: center;
            margin-top: 20px;
        }
        .btn {
            background: #4f46e5;
            color: white;
            border: none;
            padding: 12px 24px;
            border-radius: 8px;
            font-size: 1em;
            cursor: pointer;
            margin: 5px;
            text-decoration: none;
            display: inline-block;
        }
        .btn:hover { background: #4338ca; }
        .btn-vr { background: #22c55e; }
        .btn-vr:hover { background: #16a34a; }
    </style>
</head>
<body>
    <div class="container">
        <h1>🥽 VR Streaming Preview</h1>
        
        <div class="preview-container">
            <img id="preview" src="/frame" alt="Stream Preview">
            
            <div class="metrics">
                <div class="metric-card">
                    <div class="metric-value" id="fps">--</div>
                    <div class="metric-label">Capture FPS</div>
                </div>
                <div class="metric-card">
                    <div class="metric-value" id="encode-fps">--</div>
                    <div class="metric-label">Encode FPS</div>
                </div>
                <div class="metric-card">
                    <div class="metric-value" id="latency">--</div>
                    <div class="metric-label">Latency (ms)</div>
                </div>
                <div class="metric-card">
                    <div class="metric-value" id="bandwidth">--</div>
                    <div class="metric-label">Bandwidth (Mbps)</div>
                </div>
            </div>
        </div>
        
        <div class="buttons">
            <a href="/vr" class="btn btn-vr">🥽 Open VR Mode</a>
            <a href="/stream" class="btn">📺 MJPEG Stream</a>
        </div>
    </div>
    
    <script>
        // Update preview image every 100ms
        setInterval(() => {
            document.getElementById('preview').src = '/frame?' + Date.now();
        }, 100);
        
        // Update metrics every second
        setInterval(async () => {
            try {
                const res = await fetch('/metrics');
                const data = await res.json();
                document.getElementById('fps').textContent = data.capture_fps?.toFixed(1) || '--';
                document.getElementById('encode-fps').textContent = data.encode_fps?.toFixed(1) || '--';
                document.getElementById('latency').textContent = data.latency_ms?.toFixed(1) || '--';
                document.getElementById('bandwidth').textContent = data.bandwidth_mbps?.toFixed(2) || '--';
            } catch (e) {}
        }, 1000);
    </script>
</body>
</html>'''
        
        self.send_response(200)
        self.send_header('Content-Type', 'text/html')
        self.send_header('Content-Length', len(html))
        self.end_headers()
        self.wfile.write(html.encode())
    
    def _serve_vr_page(self):
        """Serve the VR stereoscopic view page."""
        html = '''<!DOCTYPE html>
<html lang="en">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0, user-scalable=no">
    <title>VR Streaming - VR Mode</title>
    <style>
        * { margin: 0; padding: 0; }
        html, body { 
            width: 100%; 
            height: 100%; 
            overflow: hidden; 
            background: #000;
        }
        #vr-view {
            width: 100%;
            height: 100%;
            object-fit: contain;
        }
        .exit-btn {
            position: fixed;
            top: 10px;
            right: 10px;
            background: rgba(255,255,255,0.2);
            color: white;
            border: none;
            padding: 10px 15px;
            border-radius: 5px;
            font-size: 14px;
            cursor: pointer;
            z-index: 1000;
        }
        .fullscreen-hint {
            position: fixed;
            bottom: 20px;
            left: 50%;
            transform: translateX(-50%);
            background: rgba(0,0,0,0.7);
            color: white;
            padding: 10px 20px;
            border-radius: 20px;
            font-size: 14px;
            z-index: 1000;
        }
    </style>
</head>
<body>
    <img id="vr-view" src="/frame" alt="VR Stream">
    <button class="exit-btn" onclick="window.location='/'">✕ Exit VR</button>
    <div class="fullscreen-hint" id="hint">Tap anywhere for fullscreen</div>
    
    <script>
        const img = document.getElementById('vr-view');
        const hint = document.getElementById('hint');
        
        // Update frame
        setInterval(() => {
            img.src = '/frame?' + Date.now();
        }, 16); // ~60fps
        
        // Request fullscreen on tap
        document.body.addEventListener('click', () => {
            if (!document.fullscreenElement) {
                document.body.requestFullscreen().catch(e => {});
                hint.style.display = 'none';
            }
        });
        
        // Lock screen orientation if supported
        if (screen.orientation && screen.orientation.lock) {
            screen.orientation.lock('landscape').catch(e => {});
        }
        
        // Hide hint after 3 seconds
        setTimeout(() => { hint.style.display = 'none'; }, 3000);
    </script>
</body>
</html>'''
        
        self.send_response(200)
        self.send_header('Content-Type', 'text/html')
        self.send_header('Content-Length', len(html))
        self.end_headers()
        self.wfile.write(html.encode())
    
    def _serve_single_frame(self):
        """Serve a single JPEG frame."""
        if not StreamingHTTPHandler.get_frame_callback:
            self.send_error(503, 'No frame available')
            return
        
        try:
            frame_data = StreamingHTTPHandler.get_frame_callback()
            if frame_data is None:
                # Send placeholder image
                self.send_response(204)
                self.end_headers()
                return
            
            self.send_response(200)
            self.send_header('Content-Type', 'image/jpeg')
            self.send_header('Content-Length', len(frame_data))
            self.send_header('Cache-Control', 'no-cache, no-store, must-revalidate')
            self.send_header('Access-Control-Allow-Origin', '*')
            self.end_headers()
            self.wfile.write(frame_data)
        except Exception as e:
            logger.error(f"Frame serve error: {e}")
            self.send_error(500, str(e))
    
    def _serve_mjpeg_stream(self):
        """Serve MJPEG stream."""
        self.send_response(200)
        self.send_header('Content-Type', 'multipart/x-mixed-replace; boundary=frame')
        self.send_header('Cache-Control', 'no-cache')
        self.send_header('Access-Control-Allow-Origin', '*')
        self.end_headers()
        
        try:
            while True:
                if StreamingHTTPHandler.get_frame_callback:
                    frame_data = StreamingHTTPHandler.get_frame_callback()
                    if frame_data:
                        self.wfile.write(b'--frame\r\n')
                        self.wfile.write(b'Content-Type: image/jpeg\r\n')
                        self.wfile.write(f'Content-Length: {len(frame_data)}\r\n\r\n'.encode())
                        self.wfile.write(frame_data)
                        self.wfile.write(b'\r\n')
                time.sleep(0.033)  # ~30fps
        except (BrokenPipeError, ConnectionResetError):
            pass
    
    def _serve_metrics(self):
        """Serve metrics as JSON."""
        metrics = {}
        if StreamingHTTPHandler.get_metrics_callback:
            metrics = StreamingHTTPHandler.get_metrics_callback()
        
        data = json.dumps(metrics)
        self.send_response(200)
        self.send_header('Content-Type', 'application/json')
        self.send_header('Content-Length', len(data))
        self.send_header('Access-Control-Allow-Origin', '*')
        self.end_headers()
        self.wfile.write(data.encode())


class HTTPStreamServer:
    """HTTP server for streaming video preview."""
    
    def __init__(self, port: int = 8889):
        self.port = port
        self.server: Optional[HTTPServer] = None
        self._thread: Optional[threading.Thread] = None
        self._running = False
        
        # Frame buffer
        self._frame_lock = threading.Lock()
        self._current_frame: Optional[bytes] = None
        self._metrics: dict = {}
    
    def set_frame(self, jpeg_data: bytes):
        """Update the current frame."""
        with self._frame_lock:
            self._current_frame = jpeg_data
    
    def set_metrics(self, metrics: dict):
        """Update metrics."""
        self._metrics = metrics.copy()
    
    def _get_frame(self) -> Optional[bytes]:
        """Get current frame (callback for handler)."""
        with self._frame_lock:
            return self._current_frame
    
    def _get_metrics(self) -> dict:
        """Get current metrics (callback for handler)."""
        return self._metrics
    
    def start(self):
        """Start the HTTP server."""
        if self._running:
            return
        
        # Set handler callbacks
        StreamingHTTPHandler.get_frame_callback = self._get_frame
        StreamingHTTPHandler.get_metrics_callback = self._get_metrics
        
        try:
            self.server = HTTPServer(('0.0.0.0', self.port), StreamingHTTPHandler)
            self._running = True
            
            self._thread = threading.Thread(target=self._serve_forever, daemon=True)
            self._thread.start()
            
            logger.info(f"HTTP server started on http://localhost:{self.port}")
        except Exception as e:
            logger.error(f"Failed to start HTTP server: {e}")
    
    def _serve_forever(self):
        """Server loop."""
        while self._running and self.server:
            try:
                self.server.handle_request()
            except Exception as e:
                if self._running:
                    logger.error(f"HTTP server error: {e}")
    
    def stop(self):
        """Stop the HTTP server."""
        self._running = False
        if self.server:
            self.server.shutdown()
            self.server = None
        logger.info("HTTP server stopped")
    
    def get_url(self) -> str:
        """Get the server URL."""
        return f"http://localhost:{self.port}"


if __name__ == "__main__":
    # Test server
    logging.basicConfig(level=logging.INFO)
    
    server = HTTPStreamServer(8889)
    server.start()
    
    print(f"Server running at {server.get_url()}")
    print("Press Ctrl+C to stop")
    
    try:
        while True:
            time.sleep(1)
    except KeyboardInterrupt:
        server.stop()

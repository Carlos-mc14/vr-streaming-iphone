"""
VR Streaming - Screen Capture Module
=====================================
High-performance screen capture using dxcam (DirectX) or mss (fallback).
Optimized for 60+ FPS capture with minimal latency.

Author: VR Streaming Project
License: MIT
"""

import threading
import time
from queue import Queue, Full
from typing import Optional, Tuple, Callable
import logging

import numpy as np
import cv2

# Try to import dxcam for high-performance capture
try:
    import dxcam
    DXCAM_AVAILABLE = True
except ImportError:
    DXCAM_AVAILABLE = False
    logging.warning("dxcam not available, falling back to mss")

import mss

logger = logging.getLogger(__name__)


class ScreenCapture:
        def set_virtual_camera_orientation(self, quat):
            """Stub: Recibe orientación de cámara (cuaternion) desde el iPhone para tracking de cabeza."""
            # Aquí deberías integrar con tu motor de renderizado 3D si tienes uno.
            # Si solo capturas la pantalla, ignora esto o implementa integración con OBS/Unity/etc.
            pass
    """
    High-performance screen capture class.
    Uses dxcam on Windows for best performance, falls back to mss.
    """
    
    def __init__(
        self,
        target_fps: int = 60,
        resolution: Tuple[int, int] = (1920, 1080),
        monitor_index: int = 0,
        use_dxcam: bool = True,
        max_queue_size: int = 5
    ):
        """
        Initialize screen capture.
        
        Args:
            target_fps: Target frames per second
            resolution: Output resolution (width, height)
            monitor_index: Which monitor to capture
            use_dxcam: Whether to use dxcam (Windows only)
            max_queue_size: Maximum frames to buffer
        """
        self.target_fps = target_fps
        self.resolution = resolution
        self.monitor_index = monitor_index
        self.use_dxcam = use_dxcam and DXCAM_AVAILABLE
        self.max_queue_size = max_queue_size
        
        # Frame buffer queue
        self.frame_queue: Queue = Queue(maxsize=max_queue_size)
        
        # Capture state
        self._running = False
        self._capture_thread: Optional[threading.Thread] = None
        self._camera = None
        self._sct = None
        
        # Performance metrics
        self.fps = 0.0
        self.frame_count = 0
        self.last_fps_update = time.time()
        self._frame_times = []
        
        # Callbacks
        self._on_frame_callback: Optional[Callable] = None
        
        logger.info(f"ScreenCapture initialized: {resolution[0]}x{resolution[1]} @ {target_fps}fps")
        logger.info(f"Using {'dxcam' if self.use_dxcam else 'mss'} for capture")
    
    def start(self) -> bool:
        """
        Start screen capture in background thread.
        
        Returns:
            True if started successfully
        """
        if self._running:
            logger.warning("Capture already running")
            return False
        
        try:
            if self.use_dxcam:
                self._init_dxcam()
            else:
                self._init_mss()
            
            self._running = True
            self._capture_thread = threading.Thread(
                target=self._capture_loop,
                name="ScreenCaptureThread",
                daemon=True
            )
            self._capture_thread.start()
            
            logger.info("Screen capture started")
            return True
            
        except Exception as e:
            logger.error(f"Failed to start capture: {e}")
            return False
    
    def stop(self):
        """Stop screen capture."""
        self._running = False
        
        if self._capture_thread:
            self._capture_thread.join(timeout=2.0)
            self._capture_thread = None
        
        if self._camera:
            try:
                self._camera.stop()
            except:
                pass
            self._camera = None
        
        if self._sct:
            self._sct.close()
            self._sct = None
        
        # Clear queue
        while not self.frame_queue.empty():
            try:
                self.frame_queue.get_nowait()
            except:
                break
        
        logger.info("Screen capture stopped")
    
    def _init_dxcam(self):
        """Initialize dxcam for DirectX capture."""
        self._camera = dxcam.create(
            device_idx=0,
            output_idx=self.monitor_index,
            output_color="BGR"
        )
        self._camera.start(
            target_fps=self.target_fps,
            video_mode=True
        )
        logger.info(f"dxcam initialized for monitor {self.monitor_index}")
    
    def _init_mss(self):
        """Initialize mss for cross-platform capture."""
        self._sct = mss.mss()
        logger.info(f"mss initialized for monitor {self.monitor_index}")
    
    def _capture_loop(self):
        """Main capture loop running in background thread."""
        frame_interval = 1.0 / self.target_fps
        last_frame_time = time.time()
        
        while self._running:
            try:
                current_time = time.time()
                elapsed = current_time - last_frame_time
                
                # Rate limiting
                if elapsed < frame_interval:
                    time.sleep(frame_interval - elapsed)
                    continue
                
                # Capture frame
                frame = self._capture_frame()
                
                if frame is not None:
                    # Resize if needed
                    if frame.shape[:2] != (self.resolution[1], self.resolution[0]):
                        frame = cv2.resize(
                            frame, 
                            self.resolution, 
                            interpolation=cv2.INTER_LINEAR
                        )
                    
                    # Add to queue (drop oldest if full)
                    try:
                        self.frame_queue.put_nowait(frame)
                    except Full:
                        # Remove oldest frame and add new one
                        try:
                            self.frame_queue.get_nowait()
                            self.frame_queue.put_nowait(frame)
                        except:
                            pass
                    
                    # Update metrics
                    self._update_fps()
                    
                    # Callback
                    if self._on_frame_callback:
                        self._on_frame_callback(frame)
                
                last_frame_time = time.time()
                
            except Exception as e:
                logger.error(f"Capture error: {e}")
                time.sleep(0.01)
    
    def _capture_frame(self) -> Optional[np.ndarray]:
        """
        Capture a single frame.
        
        Returns:
            Frame as numpy array (BGR format) or None
        """
        try:
            if self.use_dxcam and self._camera:
                frame = self._camera.get_latest_frame()
                return frame
            
            elif self._sct:
                monitors = self._sct.monitors
                if self.monitor_index + 1 < len(monitors):
                    monitor = monitors[self.monitor_index + 1]  # +1 because 0 is "all"
                else:
                    monitor = monitors[1]  # Default to primary
                
                screenshot = self._sct.grab(monitor)
                frame = np.array(screenshot)
                # Convert BGRA to BGR
                frame = cv2.cvtColor(frame, cv2.COLOR_BGRA2BGR)
                return frame
            
            return None
            
        except Exception as e:
            logger.error(f"Frame capture error: {e}")
            return None
    
    def _update_fps(self):
        """Update FPS calculation."""
        current_time = time.time()
        self._frame_times.append(current_time)
        
        # Keep only last second of frame times
        self._frame_times = [t for t in self._frame_times if current_time - t < 1.0]
        
        # Update FPS every 0.5 seconds
        if current_time - self.last_fps_update > 0.5:
            self.fps = len(self._frame_times)
            self.last_fps_update = current_time
            self.frame_count += 1
    
    def get_frame(self, timeout: float = 0.1) -> Optional[np.ndarray]:
        """
        Get the next frame from the queue.
        
        Args:
            timeout: Maximum time to wait for a frame
            
        Returns:
            Frame as numpy array or None if timeout
        """
        try:
            return self.frame_queue.get(timeout=timeout)
        except:
            return None
    
    def get_latest_frame(self) -> Optional[np.ndarray]:
        """
        Get the most recent frame, discarding older ones.
        
        Returns:
            Most recent frame or None
        """
        frame = None
        while not self.frame_queue.empty():
            try:
                frame = self.frame_queue.get_nowait()
            except:
                break
        return frame
    
    def set_on_frame_callback(self, callback: Callable):
        """Set callback function to be called on each new frame."""
        self._on_frame_callback = callback
    
    def get_metrics(self) -> dict:
        """
        Get performance metrics.
        
        Returns:
            Dictionary with FPS, frame count, queue size
        """
        return {
            "fps": round(self.fps, 1),
            "frame_count": self.frame_count,
            "queue_size": self.frame_queue.qsize(),
            "max_queue_size": self.max_queue_size,
            "backend": "dxcam" if self.use_dxcam else "mss"
        }
    
    @property
    def is_running(self) -> bool:
        """Check if capture is running."""
        return self._running


class StereoConverter:
    """
    Converts single frames to stereoscopic side-by-side format.
    Includes optional barrel distortion for VR lens correction.
    """
    
    def __init__(
        self,
        output_resolution: Tuple[int, int] = (1920, 1080),
        eye_separation: float = 63.0,
        fov: float = 100.0,
        barrel_distortion: bool = True,
        k1: float = 0.22,
        k2: float = 0.24
    ):
        """
        Initialize stereo converter.
        
        Args:
            output_resolution: Output resolution (width, height)
            eye_separation: Eye separation in mm
            fov: Field of view in degrees
            barrel_distortion: Enable barrel distortion correction
            k1, k2: Barrel distortion coefficients
        """
        self.output_resolution = output_resolution
        self.eye_separation = eye_separation
        self.fov = fov
        self.barrel_distortion = barrel_distortion
        self.k1 = k1
        self.k2 = k2
        
        # Pre-calculate distortion maps for performance
        self._left_map_x = None
        self._left_map_y = None
        self._right_map_x = None
        self._right_map_y = None
        
        if barrel_distortion:
            self._generate_distortion_maps()
        
        logger.info(f"StereoConverter initialized: {output_resolution}")
    
    def _generate_distortion_maps(self):
        """Pre-generate barrel distortion maps for both eyes."""
        half_width = self.output_resolution[0] // 2
        height = self.output_resolution[1]
        
        # Create coordinate grids
        x = np.linspace(-1, 1, half_width)
        y = np.linspace(-1, 1, height)
        xv, yv = np.meshgrid(x, y)
        
        # Calculate radius from center
        r = np.sqrt(xv**2 + yv**2)
        
        # Apply barrel distortion formula
        # r' = r * (1 + k1*r^2 + k2*r^4)
        factor = 1 + self.k1 * r**2 + self.k2 * r**4
        
        # Calculate distorted coordinates
        xd = xv * factor
        yd = yv * factor
        
        # Convert back to pixel coordinates
        map_x = ((xd + 1) * 0.5 * half_width).astype(np.float32)
        map_y = ((yd + 1) * 0.5 * height).astype(np.float32)
        
        self._left_map_x = map_x
        self._left_map_y = map_y
        self._right_map_x = map_x
        self._right_map_y = map_y
        
        logger.info("Barrel distortion maps generated")
    
    def convert_to_stereo(self, frame: np.ndarray) -> np.ndarray:
        """
        Convert single frame to side-by-side stereoscopic format.
        
        Args:
            frame: Input frame (BGR format)
            
        Returns:
            Stereoscopic frame with left/right views side by side
        """
        height, width = frame.shape[:2]
        half_width = self.output_resolution[0] // 2
        out_height = self.output_resolution[1]
        
        # Resize to half width for each eye
        eye_frame = cv2.resize(
            frame, 
            (half_width, out_height), 
            interpolation=cv2.INTER_LINEAR
        )
        
        # Apply barrel distortion if enabled
        if self.barrel_distortion and self._left_map_x is not None and self._left_map_y is not None and self._right_map_x is not None and self._right_map_y is not None:
            left_eye = cv2.remap(
                eye_frame,
                self._left_map_x,
                self._left_map_y,
                cv2.INTER_LINEAR,
                borderMode=cv2.BORDER_CONSTANT,
                borderValue=(0, 0, 0)
            )
            right_eye = cv2.remap(
                eye_frame,
                self._right_map_x,
                self._right_map_y,
                cv2.INTER_LINEAR,
                borderMode=cv2.BORDER_CONSTANT,
                borderValue=(0, 0, 0)
            )
        else:
            left_eye = eye_frame
            right_eye = eye_frame.copy()
        
        # Create output frame with both eyes side by side
        stereo_frame = np.zeros(
            (out_height, self.output_resolution[0], 3),
            dtype=np.uint8
        )
        stereo_frame[:, :half_width] = left_eye
        stereo_frame[:, half_width:] = right_eye
        
        return stereo_frame
    
    def update_distortion(self, k1: float, k2: float):
        """Update distortion coefficients and regenerate maps."""
        self.k1 = k1
        self.k2 = k2
        self._generate_distortion_maps()
        logger.info(f"Distortion updated: k1={k1}, k2={k2}")


# Test function
if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO)
    
    print("Testing screen capture...")
    
    capture = ScreenCapture(
        target_fps=60,
        resolution=(1920, 1080),
        use_dxcam=True
    )
    
    stereo = StereoConverter(
        output_resolution=(1920, 1080),
        barrel_distortion=True
    )
    
    capture.start()
    
    try:
        start_time = time.time()
        frames = 0
        
        while time.time() - start_time < 5:
            frame = capture.get_frame(timeout=0.1)
            if frame is not None:
                stereo_frame = stereo.convert_to_stereo(frame)
                frames += 1
                
                if frames % 30 == 0:
                    metrics = capture.get_metrics()
                    print(f"FPS: {metrics['fps']}, Frames: {frames}")
        
        print(f"Captured {frames} frames in 5 seconds ({frames/5:.1f} FPS)")
        
    finally:
        capture.stop()

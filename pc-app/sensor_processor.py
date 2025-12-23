"""
VR Streaming - Sensor Processor Module
========================================
Processes sensor data from iOS device and converts to mouse/camera movement.
Handles quaternion to euler conversion, smoothing, and input simulation.

Author: VR Streaming Project
License: MIT
"""

import threading
import time
import math
from queue import Queue, Empty
from typing import Optional, Tuple, Callable, Dict
from dataclasses import dataclass
import logging

import numpy as np

# Windows input simulation
try:
    import win32api
    import win32con
    import ctypes
    WIN32_AVAILABLE = True
except ImportError:
    WIN32_AVAILABLE = False
    logging.warning("win32api not available, mouse simulation disabled")

# Cross-platform input as fallback
try:
    from pynput.mouse import Controller as MouseController
    from pynput.keyboard import Controller as KeyboardController
    PYNPUT_AVAILABLE = True
except ImportError:
    PYNPUT_AVAILABLE = False
    logging.warning("pynput not available")

logger = logging.getLogger(__name__)


@dataclass
class Quaternion:
    """Quaternion representation for 3D orientation."""
    x: float = 0.0
    y: float = 0.0
    z: float = 0.0
    w: float = 1.0
    
    @classmethod
    def from_dict(cls, d: dict) -> 'Quaternion':
        """Create from dictionary."""
        return cls(
            x=d.get('x', 0.0),
            y=d.get('y', 0.0),
            z=d.get('z', 0.0),
            w=d.get('w', 1.0)
        )
    
    def to_euler(self) -> Tuple[float, float, float]:
        """
        Convert quaternion to Euler angles (pitch, yaw, roll) in degrees.
        
        Returns:
            Tuple of (pitch, yaw, roll) in degrees
        """
        # Roll (x-axis rotation)
        sinr_cosp = 2 * (self.w * self.x + self.y * self.z)
        cosr_cosp = 1 - 2 * (self.x * self.x + self.y * self.y)
        roll = math.atan2(sinr_cosp, cosr_cosp)
        
        # Pitch (y-axis rotation)
        sinp = 2 * (self.w * self.y - self.z * self.x)
        if abs(sinp) >= 1:
            pitch = math.copysign(math.pi / 2, sinp)
        else:
            pitch = math.asin(sinp)
        
        # Yaw (z-axis rotation)
        siny_cosp = 2 * (self.w * self.z + self.x * self.y)
        cosy_cosp = 1 - 2 * (self.y * self.y + self.z * self.z)
        yaw = math.atan2(siny_cosp, cosy_cosp)
        
        # Convert to degrees
        return (
            math.degrees(pitch),
            math.degrees(yaw),
            math.degrees(roll)
        )
    
    def normalize(self) -> 'Quaternion':
        """Normalize the quaternion."""
        mag = math.sqrt(self.x**2 + self.y**2 + self.z**2 + self.w**2)
        if mag > 0:
            return Quaternion(
                x=self.x / mag,
                y=self.y / mag,
                z=self.z / mag,
                w=self.w / mag
            )
        return Quaternion()


@dataclass
class EulerAngles:
    """Euler angles representation."""
    pitch: float = 0.0  # Up/down (X)
    yaw: float = 0.0    # Left/right (Y)
    roll: float = 0.0   # Tilt (Z)
    
    def as_tuple(self) -> Tuple[float, float, float]:
        """Return as tuple."""
        return (self.pitch, self.yaw, self.roll)


class SensorProcessor:
    """
    Processes sensor data and converts to input events.
    Handles smoothing, deadzone, and sensitivity adjustment.
    """
    
    def __init__(
        self,
        sensitivity: Optional[Dict[str, float]] = None,
        smoothing: float = 0.3,
        deadzone: float = 0.02,
        invert_x: bool = False,
        invert_y: bool = False
    ):
        """
        Initialize sensor processor.
        
        Args:
            sensitivity: Dict with 'yaw', 'pitch', 'roll' sensitivity values
            smoothing: Smoothing factor (0-1, higher = more smoothing)
            deadzone: Minimum movement threshold
            invert_x: Invert horizontal movement
            invert_y: Invert vertical movement
        """
        self.sensitivity = sensitivity or {'yaw': 2.0, 'pitch': 1.5, 'roll': 1.0}
        self.smoothing = max(0.0, min(1.0, smoothing))
        self.deadzone = deadzone
        self.invert_x = invert_x
        self.invert_y = invert_y
        
        # State
        self._running = False
        self._process_thread: Optional[threading.Thread] = None
        
        # Reference orientation (for relative movement)
        self._reference_orientation: Optional[Quaternion] = None
        self._last_orientation: Optional[Quaternion] = None
        self._last_euler: Optional[EulerAngles] = None
        
        # Smoothed values
        self._smoothed_pitch = 0.0
        self._smoothed_yaw = 0.0
        self._smoothed_roll = 0.0
        
        # Mouse controller
        self._mouse: Optional[MouseController] = None
        if PYNPUT_AVAILABLE:
            self._mouse = MouseController()
        
        # Metrics
        self._samples_processed = 0
        self._last_process_time = time.time()
        
        # Mode
        self.enabled = True
        self.mode = "relative"  # "relative" or "absolute"
        
        logger.info(f"SensorProcessor initialized: sensitivity={self.sensitivity}")
    
    def reset_reference(self):
        """Reset reference orientation to current orientation."""
        self._reference_orientation = None
        self._last_euler = None
        self._smoothed_pitch = 0.0
        self._smoothed_yaw = 0.0
        logger.info("Reference orientation reset")
    
    def process_sensor_data(self, sensor_data) -> Optional[Tuple[float, float]]:
        """
        Process sensor data and optionally move mouse.
        
        Args:
            sensor_data: SensorData object with orientation info
            
        Returns:
            Tuple of (delta_x, delta_y) mouse movement or None
        """
        if not self.enabled:
            return None
        
        try:
            # Extract quaternion from sensor data
            quat = Quaternion.from_dict(sensor_data.orientation)
            quat = quat.normalize()
            
            # Set reference on first data point
            if self._reference_orientation is None:
                self._reference_orientation = quat
                self._last_orientation = quat
                pitch, yaw, roll = quat.to_euler()
                self._last_euler = EulerAngles(pitch, yaw, roll)
                return None
            
            # Convert to euler angles
            pitch, yaw, roll = quat.to_euler()
            current_euler = EulerAngles(pitch, yaw, roll)
            
            # Calculate delta from last reading
            if self._last_euler:
                delta_pitch = current_euler.pitch - self._last_euler.pitch
                delta_yaw = current_euler.yaw - self._last_euler.yaw
                delta_roll = current_euler.roll - self._last_euler.roll
                
                # Handle angle wrapping
                if delta_yaw > 180:
                    delta_yaw -= 360
                elif delta_yaw < -180:
                    delta_yaw += 360
                
                if delta_pitch > 180:
                    delta_pitch -= 360
                elif delta_pitch < -180:
                    delta_pitch += 360
            else:
                delta_pitch = 0
                delta_yaw = 0
                delta_roll = 0
            
            # Apply smoothing using exponential moving average
            self._smoothed_yaw = (
                self.smoothing * self._smoothed_yaw + 
                (1 - self.smoothing) * delta_yaw
            )
            self._smoothed_pitch = (
                self.smoothing * self._smoothed_pitch + 
                (1 - self.smoothing) * delta_pitch
            )
            
            # Apply deadzone
            if abs(self._smoothed_yaw) < self.deadzone:
                self._smoothed_yaw = 0
            if abs(self._smoothed_pitch) < self.deadzone:
                self._smoothed_pitch = 0
            
            # Calculate mouse movement
            mouse_x = self._smoothed_yaw * self.sensitivity['yaw']
            mouse_y = self._smoothed_pitch * self.sensitivity['pitch']
            
            # Apply inversion
            if self.invert_x:
                mouse_x = -mouse_x
            if self.invert_y:
                mouse_y = -mouse_y
            
            # Update state
            self._last_orientation = quat
            self._last_euler = current_euler
            self._samples_processed += 1
            
            # Move mouse if movement is significant
            if abs(mouse_x) > 0.1 or abs(mouse_y) > 0.1:
                self._move_mouse(int(mouse_x), int(mouse_y))
            
            return (mouse_x, mouse_y)
            
        except Exception as e:
            logger.error(f"Sensor processing error: {e}")
            return None
    
    def _move_mouse(self, delta_x: int, delta_y: int):
        """
        Move the mouse cursor.
        
        Args:
            delta_x: Horizontal movement in pixels
            delta_y: Vertical movement in pixels
        """
        if not self.enabled:
            return
        
        try:
            if WIN32_AVAILABLE:
                # Use win32api for more reliable mouse movement
                # Get current position
                x, y = win32api.GetCursorPos()
                # Move to new position
                win32api.SetCursorPos((x + delta_x, y + delta_y))
                
            elif PYNPUT_AVAILABLE and self._mouse:
                # Use pynput as fallback
                self._mouse.move(delta_x, delta_y)
                
        except Exception as e:
            logger.error(f"Mouse move error: {e}")
    
    def move_mouse_absolute(self, x: int, y: int):
        """Move mouse to absolute position."""
        try:
            if WIN32_AVAILABLE:
                win32api.SetCursorPos((x, y))
            elif PYNPUT_AVAILABLE and self._mouse:
                self._mouse.position = (x, y)
        except Exception as e:
            logger.error(f"Mouse absolute move error: {e}")
    
    def click(self, button: str = "left"):
        """
        Simulate mouse click.
        
        Args:
            button: "left", "right", or "middle"
        """
        try:
            if WIN32_AVAILABLE:
                if button == "left":
                    win32api.mouse_event(win32con.MOUSEEVENTF_LEFTDOWN, 0, 0, 0, 0)
                    time.sleep(0.05)
                    win32api.mouse_event(win32con.MOUSEEVENTF_LEFTUP, 0, 0, 0, 0)
                elif button == "right":
                    win32api.mouse_event(win32con.MOUSEEVENTF_RIGHTDOWN, 0, 0, 0, 0)
                    time.sleep(0.05)
                    win32api.mouse_event(win32con.MOUSEEVENTF_RIGHTUP, 0, 0, 0, 0)
                    
            elif PYNPUT_AVAILABLE and self._mouse:
                from pynput.mouse import Button
                btn = Button.left if button == "left" else Button.right
                self._mouse.click(btn)
                
        except Exception as e:
            logger.error(f"Click error: {e}")
    
    def set_sensitivity(self, yaw: Optional[float] = None, pitch: Optional[float] = None, roll: Optional[float] = None):
        """Update sensitivity values."""
        if yaw is not None:
            self.sensitivity['yaw'] = yaw
        if pitch is not None:
            self.sensitivity['pitch'] = pitch
        if roll is not None:
            self.sensitivity['roll'] = roll
        logger.info(f"Sensitivity updated: {self.sensitivity}")
    
    def set_smoothing(self, smoothing: float):
        """Update smoothing factor."""
        self.smoothing = max(0.0, min(1.0, smoothing))
        logger.info(f"Smoothing set to {self.smoothing}")
    
    def set_deadzone(self, deadzone: float):
        """Update deadzone threshold."""
        self.deadzone = max(0.0, deadzone)
        logger.info(f"Deadzone set to {self.deadzone}")
    
    def get_current_euler(self) -> Optional[EulerAngles]:
        """Get current euler angles."""
        return self._last_euler
    
    def get_metrics(self) -> dict:
        """Get processing metrics."""
        current_time = time.time()
        elapsed = current_time - self._last_process_time
        
        return {
            "enabled": self.enabled,
            "mode": self.mode,
            "samples_processed": self._samples_processed,
            "current_euler": self._last_euler.as_tuple() if self._last_euler else None,
            "smoothed_values": {
                "pitch": round(self._smoothed_pitch, 3),
                "yaw": round(self._smoothed_yaw, 3)
            },
            "sensitivity": self.sensitivity,
            "smoothing": self.smoothing,
            "deadzone": self.deadzone
        }


class HeadTracker:
    """
    Higher-level head tracking that combines sensor processing
    with game/application-specific logic.
    """
    
    def __init__(
        self,
        processor: Optional[SensorProcessor] = None,
        update_rate: int = 60
    ):
        """
        Initialize head tracker.
        
        Args:
            processor: SensorProcessor instance
            update_rate: Target updates per second
        """
        self.processor = processor or SensorProcessor()
        self.update_rate = update_rate
        
        # Tracking state
        self.is_tracking = False
        self._track_thread: Optional[threading.Thread] = None
        
        # Data queue
        self._sensor_queue: Queue = Queue(maxsize=100)
        
        # Position tracking
        self.position = {'x': 0.0, 'y': 0.0, 'z': 0.0}
        self.rotation = {'pitch': 0.0, 'yaw': 0.0, 'roll': 0.0}
        
        # Callbacks
        self._on_update_callback: Optional[Callable] = None
    
    def start(self) -> bool:
        """Start head tracking."""
        if self.is_tracking:
            return False
        
        self.is_tracking = True
        self._track_thread = threading.Thread(
            target=self._track_loop,
            name="HeadTrackerThread",
            daemon=True
        )
        self._track_thread.start()
        
        logger.info("Head tracking started")
        return True
    
    def stop(self):
        """Stop head tracking."""
        self.is_tracking = False
        
        if self._track_thread:
            self._track_thread.join(timeout=2.0)
            self._track_thread = None
        
        logger.info("Head tracking stopped")
    
    def _track_loop(self):
        """Main tracking loop."""
        interval = 1.0 / self.update_rate
        
        while self.is_tracking:
            start_time = time.time()
            
            try:
                # Get sensor data
                sensor_data = self._sensor_queue.get(timeout=interval)
                
                # Process data
                result = self.processor.process_sensor_data(sensor_data)
                
                if result:
                    delta_x, delta_y = result
                    
                    # Update rotation state
                    if self.processor._last_euler:
                        self.rotation['pitch'] = self.processor._last_euler.pitch
                        self.rotation['yaw'] = self.processor._last_euler.yaw
                        self.rotation['roll'] = self.processor._last_euler.roll
                    
                    # Call update callback
                    if self._on_update_callback:
                        self._on_update_callback(self.rotation, (delta_x, delta_y))
                
            except Empty:
                continue
            except Exception as e:
                logger.error(f"Track loop error: {e}")
            
            # Rate limiting
            elapsed = time.time() - start_time
            if elapsed < interval:
                time.sleep(interval - elapsed)
    
    def add_sensor_data(self, sensor_data):
        """Add sensor data to processing queue."""
        try:
            self._sensor_queue.put_nowait(sensor_data)
        except:
            # Queue full, drop oldest
            try:
                self._sensor_queue.get_nowait()
                self._sensor_queue.put_nowait(sensor_data)
            except:
                pass
    
    def set_on_update(self, callback: Callable):
        """Set callback for rotation updates."""
        self._on_update_callback = callback
    
    def recenter(self):
        """Recenter head tracking."""
        self.processor.reset_reference()
        self.rotation = {'pitch': 0.0, 'yaw': 0.0, 'roll': 0.0}
        logger.info("Head tracking recentered")
    
    def get_state(self) -> dict:
        """Get current tracking state."""
        return {
            "is_tracking": self.is_tracking,
            "position": self.position,
            "rotation": self.rotation,
            "processor_metrics": self.processor.get_metrics()
        }


# Test function
if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO)
    
    print("Testing sensor processor...")
    
    processor = SensorProcessor(
        sensitivity={'yaw': 3.0, 'pitch': 2.0, 'roll': 1.0},
        smoothing=0.3,
        deadzone=0.02
    )
    
    # Simulate some sensor data
    class MockSensorData:
        def __init__(self, pitch=0, yaw=0, roll=0):
            self.orientation = {
                'x': 0.0,
                'y': math.sin(math.radians(pitch/2)),
                'z': 0.0,
                'w': math.cos(math.radians(pitch/2))
            }
    
    print("Simulating head movement...")
    
    # Simulate looking up and down
    for angle in range(-30, 31, 5):
        mock_data = MockSensorData(pitch=angle)
        result = processor.process_sensor_data(mock_data)
        
        euler = processor.get_current_euler()
        if euler:
            print(f"Angle: {angle:+3d}° -> Euler: {euler.pitch:+6.1f}°")
        
        time.sleep(0.05)
    
    print("\nMetrics:", processor.get_metrics())
    
    # Test head tracker
    print("\nTesting head tracker...")
    
    tracker = HeadTracker(processor=processor)
    
    def on_update(rotation, delta):
        print(f"Rotation: {rotation}, Delta: {delta}")
    
    tracker.set_on_update(on_update)
    tracker.start()
    
    # Add some test data
    for i in range(10):
        mock_data = MockSensorData(pitch=i * 5)
        tracker.add_sensor_data(mock_data)
        time.sleep(0.05)
    
    time.sleep(0.5)
    tracker.stop()
    
    print("Done!")

"""
VR Streaming - USB Server Module
=================================
Handles USB/TCP communication with iOS device.
Uses pymobiledevice3 for USB communication or TCP socket as fallback.

Author: VR Streaming Project
License: MIT
"""

import threading
import socket
import time
import struct
import json
from queue import Queue, Empty, Full
from typing import Optional, Callable, Tuple, Dict, Any
from dataclasses import dataclass, asdict
from enum import Enum
import logging
import subprocess
import sys

# Try to import pymobiledevice3 for USB communication
try:
    from pymobiledevice3.usbmux import select_devices_by_connection_type
    from pymobiledevice3.lockdown import create_using_usbmux
    from pymobiledevice3.services.installation_proxy import InstallationProxyService
    PYMOBILEDEVICE_AVAILABLE = True
except ImportError:
    PYMOBILEDEVICE_AVAILABLE = False
    logging.warning("pymobiledevice3 not available, USB mode limited")

logger = logging.getLogger(__name__)


class ConnectionMode(Enum):
    """Connection mode types."""
    USB = "usb"
    WIFI = "wifi"
    AUTO = "auto"


class ConnectionState(Enum):
    """Connection state."""
    DISCONNECTED = "disconnected"
    CONNECTING = "connecting"
    CONNECTED = "connected"
    ERROR = "error"


@dataclass
class SensorData:
    """Sensor data from iOS device."""
    timestamp: float
    orientation: Dict[str, float]  # Quaternion: x, y, z, w
    acceleration: Dict[str, float]  # x, y, z
    gyroscope: Dict[str, float]  # x, y, z (optional)
    
    @classmethod
    def from_json(cls, data: dict) -> 'SensorData':
        """Create from JSON dictionary."""
        return cls(
            timestamp=data.get('timestamp', time.time()),
            orientation=data.get('orientation', {'x': 0, 'y': 0, 'z': 0, 'w': 1}),
            acceleration=data.get('acceleration', {'x': 0, 'y': 0, 'z': 0}),
            gyroscope=data.get('gyroscope', {'x': 0, 'y': 0, 'z': 0})
        )
    
    def to_json(self) -> dict:
        """Convert to JSON dictionary."""
        return asdict(self)


class USBServer:
    """
    Server for communicating with iOS device over USB or WiFi.
    Handles video streaming out and sensor data in.
    """
    
    # Protocol constants
    MAGIC_VIDEO = b'VRVI'  # Video frame magic
    MAGIC_SENSOR = b'VRSE'  # Sensor data magic
    MAGIC_CMD = b'VRCM'  # Command magic
    HEADER_SIZE = 12  # Magic(4) + Type(4) + Length(4)
    
    def __init__(
        self,
        mode: ConnectionMode = ConnectionMode.AUTO,
        usb_port: int = 8888,
        wifi_host: str = "0.0.0.0",
        wifi_port: int = 8889,
        buffer_size: int = 65536
    ):
        """
        Initialize USB server.
        
        Args:
            mode: Connection mode (usb, wifi, or auto)
            usb_port: Port for USB forwarding
            wifi_host: Host for WiFi mode
            wifi_port: Port for WiFi mode
            buffer_size: Socket buffer size
        """
        self.mode = mode
        self.usb_port = usb_port
        self.wifi_host = wifi_host
        self.wifi_port = wifi_port
        self.buffer_size = buffer_size
        
        # Socket state
        self._server_socket: Optional[socket.socket] = None
        self._client_socket: Optional[socket.socket] = None
        self._client_address: Optional[Tuple[str, int]] = None
        
        # Thread state
        self._running = False
        self._accept_thread: Optional[threading.Thread] = None
        self._receive_thread: Optional[threading.Thread] = None
        self._send_thread: Optional[threading.Thread] = None
        
        # Connection state
        self.state = ConnectionState.DISCONNECTED
        self._state_lock = threading.Lock()
        
        # Queues
        self._send_queue: Queue = Queue(maxsize=10)
        self._sensor_queue: Queue = Queue(maxsize=100)
        
        # Callbacks
        self._on_connect_callback: Optional[Callable] = None
        self._on_disconnect_callback: Optional[Callable] = None
        self._on_sensor_data_callback: Optional[Callable[[SensorData], None]] = None
        self._on_state_change_callback: Optional[Callable[[ConnectionState], None]] = None
        
        # Metrics
        self.bytes_sent = 0
        self.bytes_received = 0
        self.frames_sent = 0
        self.sensor_packets_received = 0
        self._last_metrics_reset = time.time()
        
        # USB port forwarding process
        self._iproxy_process: Optional[subprocess.Popen] = None
        
        logger.info(f"USBServer initialized: mode={mode.value}")
    
    def _set_state(self, state: ConnectionState):
        """Update connection state and notify callback."""
        with self._state_lock:
            if self.state != state:
                self.state = state
                logger.info(f"Connection state: {state.value}")
                if self._on_state_change_callback:
                    try:
                        self._on_state_change_callback(state)
                    except Exception as e:
                        logger.error(f"State callback error: {e}")
    
    def start(self) -> bool:
        """
        Start the server.
        
        Returns:
            True if started successfully
        """
        if self._running:
            logger.warning("Server already running")
            return False
        
        try:
            # Start USB port forwarding if in USB mode
            if self.mode in [ConnectionMode.USB, ConnectionMode.AUTO]:
                self._start_usb_forwarding()
            
            # Create server socket
            self._server_socket = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
            self._server_socket.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
            self._server_socket.settimeout(1.0)
            
            # Always bind to all interfaces for flexibility
            # USB tunnel will forward iPhone's localhost to PC's port
            self._server_socket.bind((self.wifi_host, self.wifi_port))
            
            self._server_socket.listen(1)
            
            port = self.wifi_port
            logger.info(f"Server listening on port {port}")
            
            self._running = True
            self._set_state(ConnectionState.CONNECTING)
            
            # Start accept thread
            self._accept_thread = threading.Thread(
                target=self._accept_loop,
                name="USBAcceptThread",
                daemon=True
            )
            self._accept_thread.start()
            
            return True
            
        except Exception as e:
            logger.error(f"Failed to start server: {e}")
            self._set_state(ConnectionState.ERROR)
            return False
    
    def stop(self):
        """Stop the server and clean up."""
        self._running = False
        
        # Close client connection
        if self._client_socket:
            try:
                self._client_socket.close()
            except:
                pass
            self._client_socket = None
        
        # Close server socket
        if self._server_socket:
            try:
                self._server_socket.close()
            except:
                pass
            self._server_socket = None
        
        # Stop USB forwarding
        self._stop_usb_forwarding()
        
        # Wait for threads
        for thread in [self._accept_thread, self._receive_thread, self._send_thread]:
            if thread and thread.is_alive():
                thread.join(timeout=2.0)
        
        # Clear queues
        for q in [self._send_queue, self._sensor_queue]:
            while not q.empty():
                try:
                    q.get_nowait()
                except:
                    break
        
        self._set_state(ConnectionState.DISCONNECTED)
        logger.info("Server stopped")
    
    def _start_usb_forwarding(self):
        """Start iproxy for USB port forwarding."""
        try:
            # Check if iproxy is available (from libimobiledevice)
            # On Windows, this might be installed via chocolatey or manually
            
            # Try using pymobiledevice3's usbmux directly
            if PYMOBILEDEVICE_AVAILABLE:
                devices = select_devices_by_connection_type(connection_type='USB')
                if devices:
                    logger.info(f"Found {len(devices)} iOS device(s) via USB")
                else:
                    logger.warning("No iOS devices found via USB")
            
            # As fallback, try iproxy command
            try:
                # iproxy localPort:devicePort
                self._iproxy_process = subprocess.Popen(
                    ['iproxy', str(self.usb_port), str(self.usb_port)],
                    stdout=subprocess.PIPE,
                    stderr=subprocess.PIPE,
                    creationflags=subprocess.CREATE_NO_WINDOW if sys.platform == 'win32' else 0
                )
                time.sleep(0.5)
                
                if self._iproxy_process.poll() is None:
                    logger.info(f"iproxy started for port {self.usb_port}")
                else:
                    logger.warning("iproxy failed to start")
                    self._iproxy_process = None
                    
            except FileNotFoundError:
                logger.warning("iproxy not found, USB forwarding may not work")
            
        except Exception as e:
            logger.warning(f"USB forwarding setup failed: {e}")
    
    def _stop_usb_forwarding(self):
        """Stop iproxy process."""
        if self._iproxy_process:
            try:
                self._iproxy_process.terminate()
                self._iproxy_process.wait(timeout=2.0)
            except:
                pass
            self._iproxy_process = None
    
    def _accept_loop(self):
        """Accept incoming connections."""
        while self._running:
            try:
                if self._server_socket is None:
                    break
                
                try:
                    client, address = self._server_socket.accept()
                    logger.info(f"Client connected from {address}")
                    
                    # Configure client socket
                    client.setsockopt(socket.IPPROTO_TCP, socket.TCP_NODELAY, 1)
                    client.setsockopt(socket.SOL_SOCKET, socket.SO_SNDBUF, self.buffer_size)
                    client.setsockopt(socket.SOL_SOCKET, socket.SO_RCVBUF, self.buffer_size)
                    
                    # Store client info
                    self._client_socket = client
                    self._client_address = address
                    
                    self._set_state(ConnectionState.CONNECTED)
                    
                    # Notify callback
                    if self._on_connect_callback:
                        self._on_connect_callback()
                    
                    # Start receive and send threads
                    self._receive_thread = threading.Thread(
                        target=self._receive_loop,
                        name="USBReceiveThread",
                        daemon=True
                    )
                    self._receive_thread.start()
                    
                    self._send_thread = threading.Thread(
                        target=self._send_loop,
                        name="USBSendThread",
                        daemon=True
                    )
                    self._send_thread.start()
                    
                    # Wait for disconnect
                    self._receive_thread.join()
                    
                    # Client disconnected
                    self._handle_disconnect()
                    
                except socket.timeout:
                    continue
                    
            except Exception as e:
                if self._running:
                    logger.error(f"Accept error: {e}")
                    time.sleep(1.0)
    
    def _handle_disconnect(self):
        """Handle client disconnection."""
        logger.info("Client disconnected")
        
        if self._client_socket:
            try:
                self._client_socket.close()
            except:
                pass
            self._client_socket = None
        
        self._client_address = None
        
        if self._running:
            self._set_state(ConnectionState.CONNECTING)
        else:
            self._set_state(ConnectionState.DISCONNECTED)
        
        if self._on_disconnect_callback:
            self._on_disconnect_callback()
    
    def _receive_loop(self):
        """Receive data from client."""
        buffer = b''
        
        while self._running and self._client_socket:
            try:
                # Receive data
                data = self._client_socket.recv(self.buffer_size)
                
                if not data:
                    # Connection closed
                    break
                
                buffer += data
                self.bytes_received += len(data)
                
                # Process complete packets
                while len(buffer) >= self.HEADER_SIZE:
                    # Check for magic number
                    magic = buffer[:4]
                    
                    if magic == self.MAGIC_SENSOR:
                        # Sensor data packet
                        packet_type, length = struct.unpack('<II', buffer[4:12])
                        
                        if len(buffer) < self.HEADER_SIZE + length:
                            break  # Wait for more data
                        
                        # Extract packet data
                        packet_data = buffer[self.HEADER_SIZE:self.HEADER_SIZE + length]
                        buffer = buffer[self.HEADER_SIZE + length:]
                        
                        # Parse sensor data
                        self._process_sensor_packet(packet_data)
                        
                    elif magic == self.MAGIC_CMD:
                        # Command packet
                        packet_type, length = struct.unpack('<II', buffer[4:12])
                        
                        if len(buffer) < self.HEADER_SIZE + length:
                            break
                        
                        packet_data = buffer[self.HEADER_SIZE:self.HEADER_SIZE + length]
                        buffer = buffer[self.HEADER_SIZE + length:]
                        
                        self._process_command_packet(packet_data)
                        
                    else:
                        # Unknown magic, try to resync
                        logger.warning(f"Unknown magic: {magic}")
                        # Skip one byte and try again
                        buffer = buffer[1:]
                
            except socket.timeout:
                continue
            except ConnectionResetError:
                logger.warning("Connection reset by client")
                break
            except Exception as e:
                logger.error(f"Receive error: {e}")
                break
    
    def _process_sensor_packet(self, data: bytes):
        """Process received sensor data packet."""
        try:
            # Parse JSON sensor data
            json_str = data.decode('utf-8')
            sensor_dict = json.loads(json_str)
            
            sensor_data = SensorData.from_json(sensor_dict)
            self.sensor_packets_received += 1
            
            # Add to queue
            try:
                self._sensor_queue.put_nowait(sensor_data)
            except Full:
                # Drop oldest
                try:
                    self._sensor_queue.get_nowait()
                    self._sensor_queue.put_nowait(sensor_data)
                except:
                    pass
            
            # Call callback
            if self._on_sensor_data_callback:
                self._on_sensor_data_callback(sensor_data)
                
        except Exception as e:
            logger.error(f"Sensor data parse error: {e}")
    
    def _process_command_packet(self, data: bytes):
        """Process command packet from client."""
        try:
            cmd = json.loads(data.decode('utf-8'))
            cmd_type = cmd.get('type', '')
            
            logger.debug(f"Received command: {cmd_type}")
            
            if cmd_type == 'ping':
                # Respond with pong
                self.send_command({'type': 'pong', 'timestamp': time.time()})
            elif cmd_type == 'get_config':
                # Send current configuration
                pass
                
        except Exception as e:
            logger.error(f"Command parse error: {e}")
    
    def _send_loop(self):
        """Send data to client."""
        logger.info("Send loop started")
        send_count = 0
        
        while self._running and self._client_socket:
            try:
                # Get data from queue
                data = self._send_queue.get(timeout=0.1)
                
                # Send data
                if self._client_socket and data:
                    try:
                        self._client_socket.sendall(data)
                        self.bytes_sent += len(data)
                        send_count += 1
                        
                        # Log every 60 frames (about 1 second at 60fps)
                        if send_count % 60 == 0:
                            logger.debug(f"Sent {send_count} packets, {self.bytes_sent / 1024 / 1024:.1f} MB total")
                            
                    except BrokenPipeError:
                        logger.warning("Broken pipe - client disconnected")
                        break
                    except ConnectionResetError:
                        logger.warning("Connection reset - client disconnected")
                        break
                    except ConnectionAbortedError:
                        logger.warning("Connection aborted - client disconnected")
                        break
                    except Exception as e:
                        logger.error(f"Send error: {e}")
                        break
                        
            except Empty:
                continue
            except Exception as e:
                logger.error(f"Send loop error: {e}")
                break
        
        logger.info(f"Send loop ended. Total packets sent: {send_count}")
    
    def send_frame(self, frame_data: bytes) -> bool:
        """
        Send a video frame to the client.
        
        Args:
            frame_data: Encoded frame bytes (raw JPEG data)
            
        Returns:
            True if queued successfully
        """
        if self.state != ConnectionState.CONNECTED:
            return False
        
        # Validate JPEG data
        if len(frame_data) < 2 or frame_data[:2] != b'\xff\xd8':
            logger.warning(f"Invalid JPEG data: size={len(frame_data)}, magic={frame_data[:2].hex() if len(frame_data) >= 2 else 'N/A'}")
            return False
        
        try:
            # Create packet header
            header = struct.pack(
                '<4sII',
                self.MAGIC_VIDEO,
                0,  # Packet type (0 = video)
                len(frame_data)
            )
            
            packet = header + frame_data
            
            # Queue for sending - drop old frames if queue is full
            try:
                # Try to put without blocking
                self._send_queue.put_nowait(packet)
                self.frames_sent += 1
                return True
            except Full:
                # Queue is full - drop oldest frame and add new one
                dropped = 0
                while not self._send_queue.empty():
                    try:
                        self._send_queue.get_nowait()
                        dropped += 1
                    except Empty:
                        break
                
                try:
                    self._send_queue.put_nowait(packet)
                    self.frames_sent += 1
                    if dropped > 0:
                        logger.debug(f"Dropped {dropped} old frames to add new one")
                    return True
                except Full:
                    return False
                    
        except Exception as e:
            logger.error(f"Send frame error: {e}")
            return False
    
    def send_command(self, command: dict) -> bool:
        """
        Send a command to the client.
        
        Args:
            command: Command dictionary to send
            
        Returns:
            True if queued successfully
        """
        if self.state != ConnectionState.CONNECTED:
            return False
        
        try:
            cmd_data = json.dumps(command).encode('utf-8')
            
            header = struct.pack(
                '<4sII',
                self.MAGIC_CMD,
                1,  # Packet type (1 = command)
                len(cmd_data)
            )
            
            packet = header + cmd_data
            
            try:
                self._send_queue.put_nowait(packet)
                return True
            except Full:
                return False
                
        except Exception as e:
            logger.error(f"Send command error: {e}")
            return False
    
    def get_sensor_data(self, timeout: float = 0.01) -> Optional[SensorData]:
        """
        Get next sensor data from queue.
        
        Args:
            timeout: Maximum time to wait
            
        Returns:
            SensorData or None
        """
        try:
            return self._sensor_queue.get(timeout=timeout)
        except Empty:
            return None
    
    def get_latest_sensor_data(self) -> Optional[SensorData]:
        """Get the most recent sensor data, discarding older ones."""
        data = None
        while not self._sensor_queue.empty():
            try:
                data = self._sensor_queue.get_nowait()
            except:
                break
        return data
    
    def set_on_connect(self, callback: Callable):
        """Set callback for connection events."""
        self._on_connect_callback = callback
    
    def set_on_disconnect(self, callback: Callable):
        """Set callback for disconnection events."""
        self._on_disconnect_callback = callback
    
    def set_on_sensor_data(self, callback: Callable[[SensorData], None]):
        """Set callback for sensor data."""
        self._on_sensor_data_callback = callback
    
    def set_on_state_change(self, callback: Callable[[ConnectionState], None]):
        """Set callback for state changes."""
        self._on_state_change_callback = callback
    
    def get_metrics(self) -> dict:
        """Get server metrics."""
        elapsed = time.time() - self._last_metrics_reset
        
        return {
            "state": self.state.value,
            "mode": self.mode.value,
            "client_address": str(self._client_address) if self._client_address else None,
            "bytes_sent": self.bytes_sent,
            "bytes_received": self.bytes_received,
            "frames_sent": self.frames_sent,
            "sensor_packets_received": self.sensor_packets_received,
            "send_mbps": round((self.bytes_sent / 1024 / 1024) / elapsed, 2) if elapsed > 0 else 0,
            "recv_kbps": round((self.bytes_received / 1024) / elapsed, 2) if elapsed > 0 else 0,
            "send_queue_size": self._send_queue.qsize(),
            "sensor_queue_size": self._sensor_queue.qsize()
        }
    
    def reset_metrics(self):
        """Reset metrics counters."""
        self.bytes_sent = 0
        self.bytes_received = 0
        self.frames_sent = 0
        self.sensor_packets_received = 0
        self._last_metrics_reset = time.time()
    
    @property
    def is_connected(self) -> bool:
        """Check if client is connected."""
        return self.state == ConnectionState.CONNECTED


# Test function
if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO)
    
    print("Testing USB server...")
    
    server = USBServer(
        mode=ConnectionMode.WIFI,  # Use WiFi for testing
        wifi_port=8889
    )
    
    # Set up callbacks
    def on_sensor(data: SensorData):
        print(f"Sensor: {data.orientation}")
    
    server.set_on_sensor_data(on_sensor)
    
    server.start()
    
    print(f"Server started, waiting for connections on port {server.wifi_port}...")
    print("Press Ctrl+C to stop")
    
    try:
        while True:
            time.sleep(1)
            metrics = server.get_metrics()
            print(f"State: {metrics['state']}, "
                  f"Frames: {metrics['frames_sent']}, "
                  f"Sensor: {metrics['sensor_packets_received']}")
    except KeyboardInterrupt:
        print("\nStopping server...")
    finally:
        server.stop()

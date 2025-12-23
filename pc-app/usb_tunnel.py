"""
VR Streaming - USB Tunnel Module
=================================
Creates a USB tunnel for iPhone-to-PC communication.

For USB connection to work, the iPhone app connects via WiFi-style connection
to the PC's IP address. With USB cable, the connection is more stable.

Alternative approach using iproxy (if installed):
1. PC runs server on port 8889
2. iproxy creates tunnel: iPhone localhost:8889 -> PC port 8889
3. iPhone app connects to 127.0.0.1:8889
4. Traffic goes through USB cable

Author: VR Streaming Project
License: MIT
"""

import socket
import subprocess
import sys
import os
import time
import threading
import logging
import shutil
from typing import Optional, Callable, List
from dataclasses import dataclass
from enum import Enum
from pathlib import Path

logger = logging.getLogger(__name__)

# Try to import pymobiledevice3 for device detection
PYMOBILEDEVICE3_AVAILABLE = False
try:
    from pymobiledevice3.usbmux import list_devices
    from pymobiledevice3.lockdown import create_using_usbmux
    PYMOBILEDEVICE3_AVAILABLE = True
    logger.info("pymobiledevice3 available for USB device detection")
except ImportError as e:
    logger.debug(f"pymobiledevice3 not available: {e}")

# Try to import pymobiledevice3's tunnel/forwarder
TUNNEL_AVAILABLE = False
try:
    from pymobiledevice3.services.dvt.dvt_secure_socket_proxy import DvtSecureSocketProxyService
    from pymobiledevice3.tcp_forwarder import TcpForwarder
    TUNNEL_AVAILABLE = True
    logger.info("pymobiledevice3 TCP forwarder available")
except ImportError:
    try:
        # Alternative import path
        from pymobiledevice3.tcp_forwarder import TcpForwarder  
        TUNNEL_AVAILABLE = True
    except ImportError as e:
        logger.debug(f"TCP forwarder not available: {e}")


class USBDeviceState(Enum):
    """USB device connection state."""
    NOT_FOUND = "not_found"
    FOUND = "found"
    TUNNEL_ACTIVE = "tunnel_active"
    ERROR = "error"


@dataclass
class iOSDevice:
    """Represents a connected iOS device."""
    udid: str
    name: str
    model: str
    ios_version: str
    connection_type: str
    
    @classmethod
    def from_lockdown(cls, lockdown) -> 'iOSDevice':
        """Create from lockdown client."""
        try:
            return cls(
                udid=lockdown.udid,
                name=lockdown.all_values.get('DeviceName', 'Unknown'),
                model=lockdown.all_values.get('ProductType', 'Unknown'),
                ios_version=lockdown.all_values.get('ProductVersion', 'Unknown'),
                connection_type="USB"
            )
        except Exception as e:
            logger.error(f"Failed to get device info: {e}")
            return cls(
                udid=getattr(lockdown, 'udid', 'unknown'),
                name="Unknown Device",
                model="iPhone",
                ios_version="Unknown",
                connection_type="USB"
            )


def get_local_ip() -> str:
    """Get the local IP address of this machine."""
    try:
        s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        s.connect(("8.8.8.8", 80))
        ip = s.getsockname()[0]
        s.close()
        return ip
    except Exception:
        return "127.0.0.1"


def find_iproxy() -> Optional[str]:
    """Find iproxy executable."""
    # Check if iproxy is in PATH
    iproxy_path = shutil.which("iproxy")
    if iproxy_path:
        return iproxy_path
    
    # Check common installation paths on Windows
    common_paths = [
        r"C:\Program Files\libimobiledevice\iproxy.exe",
        r"C:\Program Files (x86)\libimobiledevice\iproxy.exe",
        r"C:\ProgramData\chocolatey\bin\iproxy.exe",
        os.path.join(os.path.dirname(sys.executable), "iproxy.exe"),
        os.path.join(os.path.dirname(__file__), "iproxy.exe"),
        os.path.join(os.path.dirname(__file__), "tools", "iproxy.exe"),
    ]
    
    for path in common_paths:
        if os.path.exists(path):
            return path
    
    return None


def check_usb_dependencies() -> dict:
    """Check if USB dependencies are available."""
    result = {
        'pymobiledevice3': PYMOBILEDEVICE3_AVAILABLE,
        'iproxy': find_iproxy() is not None,
        'iproxy_path': find_iproxy(),
        'itunes_drivers': False,
        'device_detected': False
    }
    
    # Check for iTunes/Apple Mobile Device drivers
    try:
        if PYMOBILEDEVICE3_AVAILABLE:
            devices = list_devices()
            result['itunes_drivers'] = True
            result['device_detected'] = len(devices) > 0
    except Exception as e:
        logger.debug(f"Driver check failed: {e}")
    
    return result


class USBTunnel:
    """
    Creates a USB tunnel for iPhone-to-PC communication.
    
    Uses iproxy to forward connections from iPhone's localhost
    to the PC's streaming server.
    """
    
    def __init__(
        self,
        local_port: int = 8889,
        device_port: int = 8889,
        on_device_connected: Optional[Callable[['iOSDevice'], None]] = None,
        on_device_disconnected: Optional[Callable[[], None]] = None,
        on_tunnel_ready: Optional[Callable[[str, int], None]] = None,
        on_tunnel_error: Optional[Callable[[str], None]] = None
    ):
        """
        Initialize USB tunnel.
        
        Args:
            local_port: Port on PC to forward to
            device_port: Port on iPhone to listen on
            on_device_connected: Callback when device connects
            on_device_disconnected: Callback when device disconnects
            on_tunnel_ready: Callback when tunnel is active
            on_tunnel_error: Callback when tunnel fails
        """
        self.local_port = local_port
        self.device_port = device_port
        self._on_device_connected = on_device_connected
        self._on_device_disconnected = on_device_disconnected
        self._on_tunnel_ready = on_tunnel_ready
        self._on_tunnel_error = on_tunnel_error
        
        self.state = USBDeviceState.NOT_FOUND
        self.current_device: Optional[iOSDevice] = None
        
        # iproxy process
        self._iproxy_process: Optional[subprocess.Popen] = None
        self._iproxy_path: Optional[str] = None
        
        # Thread state
        self._running = False
        self._monitor_thread: Optional[threading.Thread] = None
        
        logger.info(f"USBTunnel initialized: PC port {local_port} <-> iPhone port {device_port}")
    
    def start(self):
        """Start USB tunnel service."""
        if self._running:
            return
        
        # Find iproxy
        self._iproxy_path = find_iproxy()
        if not self._iproxy_path:
            logger.warning("iproxy not found - USB tunnel will not work")
            logger.warning("Install libimobiledevice: choco install libimobiledevice")
            if self._on_tunnel_error:
                self._on_tunnel_error("iproxy not found. Install: choco install libimobiledevice")
        
        self._running = True
        
        # Start device monitor
        self._monitor_thread = threading.Thread(
            target=self._device_monitor_loop,
            name="USBDeviceMonitor",
            daemon=True
        )
        self._monitor_thread.start()
        
        logger.info("USB tunnel service started")
    
    def stop(self):
        """Stop USB tunnel service."""
        self._running = False
        
        self._stop_iproxy()
        
        if self._monitor_thread and self._monitor_thread.is_alive():
            self._monitor_thread.join(timeout=2.0)
        
        logger.info("USB tunnel service stopped")
    
    def _device_monitor_loop(self):
        """Monitor for USB device connections."""
        last_device_udid = None
        
        while self._running:
            try:
                device = self._detect_usb_device()
                
                if device:
                    if last_device_udid != device.udid:
                        # New device connected
                        logger.info(f"USB device found: {device.name}")
                        self.current_device = device
                        self.state = USBDeviceState.FOUND
                        last_device_udid = device.udid
                        
                        if self._on_device_connected:
                            self._on_device_connected(device)
                        
                        # Start tunnel
                        self._start_iproxy()
                else:
                    if last_device_udid is not None:
                        # Device disconnected
                        logger.info("USB device disconnected")
                        self._stop_iproxy()
                        self.current_device = None
                        self.state = USBDeviceState.NOT_FOUND
                        last_device_udid = None
                        
                        if self._on_device_disconnected:
                            self._on_device_disconnected()
                
                time.sleep(2.0)
                
            except Exception as e:
                logger.error(f"Device monitor error: {e}")
                time.sleep(5.0)
    
    def _detect_usb_device(self) -> Optional[iOSDevice]:
        """Detect connected USB iOS device."""
        if not PYMOBILEDEVICE3_AVAILABLE:
            return None
        
        try:
            devices = list_devices()
            
            if not devices:
                return None
            
            # Get first USB device
            for dev in devices:
                try:
                    lockdown = create_using_usbmux(serial=dev.serial)
                    return iOSDevice.from_lockdown(lockdown)
                except Exception as e:
                    logger.debug(f"Could not get device info: {e}")
                    # Return basic info
                    return iOSDevice(
                        udid=dev.serial,
                        name="iPhone",
                        model="Unknown",
                        ios_version="Unknown",
                        connection_type="USB"
                    )
        except Exception as e:
            logger.error(f"Device detection error: {e}")
        
        return None
    
    def _start_iproxy(self):
        """Start tunnel for USB port forwarding (iproxy or pymobiledevice3)."""
        self._stop_iproxy()  # Stop any existing process
        
        # Try iproxy first
        if self._iproxy_path:
            self._start_iproxy_process()
            return
        
        # Fallback: If pymobiledevice3 has TcpForwarder, use that
        if TUNNEL_AVAILABLE and self.current_device:
            self._start_pymobiledevice3_tunnel()
            return
        
        # No tunnel available - notify user but continue (WiFi will work)
        logger.warning("No USB tunnel method available. Use WiFi connection.")
        logger.warning("To enable USB tunnel: choco install libimobiledevice")
        self.state = USBDeviceState.FOUND  # Device found but no tunnel
        
        # Still notify that device is connected - WiFi will work
        if self._on_tunnel_error:
            self._on_tunnel_error("No USB tunnel available. Connect via WiFi instead.")
    
    def _start_iproxy_process(self):
        """Start iproxy process for USB port forwarding."""
        try:
            # iproxy LOCAL_PORT DEVICE_PORT
            # This makes iPhone's localhost:DEVICE_PORT forward to PC's LOCAL_PORT
            cmd = [self._iproxy_path, str(self.device_port), str(self.local_port)]
            
            logger.info(f"Starting iproxy: {' '.join(cmd)}")
            
            # Start iproxy process
            creationflags = 0
            if sys.platform == 'win32':
                creationflags = subprocess.CREATE_NO_WINDOW
            
            self._iproxy_process = subprocess.Popen(
                cmd,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                creationflags=creationflags
            )
            
            # Wait a bit to see if it started successfully
            time.sleep(0.5)
            
            if self._iproxy_process.poll() is None:
                # Process is running
                logger.info(f"USB tunnel active: iPhone:{self.device_port} -> PC:{self.local_port}")
                self.state = USBDeviceState.TUNNEL_ACTIVE
                
                if self._on_tunnel_ready:
                    self._on_tunnel_ready("127.0.0.1", self.device_port)
            else:
                # Process exited
                stdout, stderr = self._iproxy_process.communicate()
                error_msg = stderr.decode() if stderr else "Unknown error"
                logger.error(f"iproxy failed: {error_msg}")
                self.state = USBDeviceState.ERROR
                
                if self._on_tunnel_error:
                    self._on_tunnel_error(f"iproxy failed: {error_msg}")
                
        except Exception as e:
            logger.error(f"Failed to start iproxy: {e}")
            self.state = USBDeviceState.ERROR
            
            if self._on_tunnel_error:
                self._on_tunnel_error(str(e))
    
    def _start_pymobiledevice3_tunnel(self):
        """Start tunnel using pymobiledevice3 TcpForwarder."""
        if not TUNNEL_AVAILABLE or not self.current_device:
            return
        
        try:
            logger.info("Starting pymobiledevice3 TCP forwarder...")
            
            # Create lockdown for this device
            lockdown = create_using_usbmux(serial=self.current_device.udid)
            
            # Start TCP forwarder
            self._tcp_forwarder = TcpForwarder(
                lockdown,
                src_port=self.device_port,
                dst_port=self.local_port
            )
            
            # Start in background thread
            def run_forwarder():
                try:
                    self._tcp_forwarder.start()
                except Exception as e:
                    logger.error(f"TCP forwarder error: {e}")
            
            self._forwarder_thread = threading.Thread(
                target=run_forwarder,
                daemon=True,
                name="TcpForwarder"
            )
            self._forwarder_thread.start()
            
            time.sleep(0.5)  # Wait for forwarder to start
            
            logger.info(f"pymobiledevice3 tunnel active: {self.device_port} -> {self.local_port}")
            self.state = USBDeviceState.TUNNEL_ACTIVE
            
            if self._on_tunnel_ready:
                self._on_tunnel_ready("127.0.0.1", self.device_port)
                
        except Exception as e:
            logger.error(f"Failed to start pymobiledevice3 tunnel: {e}")
            self.state = USBDeviceState.ERROR
            
            if self._on_tunnel_error:
                self._on_tunnel_error(f"Tunnel failed: {e}")
    
    def _stop_iproxy(self):
        """Stop iproxy process and any forwarders."""
        if self._iproxy_process:
            try:
                self._iproxy_process.terminate()
                self._iproxy_process.wait(timeout=2.0)
            except Exception as e:
                logger.debug(f"iproxy stop error: {e}")
                try:
                    self._iproxy_process.kill()
                except:
                    pass
            self._iproxy_process = None
        
        # Stop pymobiledevice3 forwarder if active
        if hasattr(self, '_tcp_forwarder') and self._tcp_forwarder:
            try:
                self._tcp_forwarder.close()
            except Exception:
                pass
            self._tcp_forwarder = None
    
    def is_tunnel_active(self) -> bool:
        """Check if USB tunnel is active."""
        return self.state == USBDeviceState.TUNNEL_ACTIVE
    
    def get_status(self) -> dict:
        """Get current tunnel status."""
        deps = check_usb_dependencies()
        
        return {
            'state': self.state.value,
            'device': self.current_device.name if self.current_device else None,
            'device_udid': self.current_device.udid if self.current_device else None,
            'tunnel_active': self.is_tunnel_active(),
            'iproxy_available': deps['iproxy'],
            'iproxy_path': deps['iproxy_path'],
            'pymobiledevice3': deps['pymobiledevice3'],
            'local_port': self.local_port,
            'device_port': self.device_port
        }


def get_all_connection_options(port: int = 8889) -> List[dict]:
    """Get all available connection options."""
    options = []
    
    # WiFi option
    local_ip = get_local_ip()
    options.append({
        'type': 'wifi',
        'name': 'WiFi Connection',
        'address': local_ip,
        'port': port,
        'description': f'Connect via WiFi to {local_ip}:{port}'
    })
    
    # USB option
    deps = check_usb_dependencies()
    usb_available = deps['iproxy'] or deps['pymobiledevice3']
    
    options.append({
        'type': 'usb',
        'name': 'USB Connection',
        'address': '127.0.0.1',
        'port': port,
        'available': usb_available,
        'device_detected': deps['device_detected'],
        'description': 'Connect via USB cable (lower latency)'
    })
    
    return options


# Test
if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO)
    
    print("USB Tunnel Test")
    print("=" * 50)
    
    # Check dependencies
    deps = check_usb_dependencies()
    print(f"\nDependencies:")
    print(f"  pymobiledevice3: {'OK' if deps['pymobiledevice3'] else 'NOT FOUND'}")
    print(f"  iproxy: {'OK' if deps['iproxy'] else 'NOT FOUND'} ({deps['iproxy_path']})")
    print(f"  iTunes drivers: {'OK' if deps['itunes_drivers'] else 'NOT FOUND'}")
    print(f"  Device detected: {'YES' if deps['device_detected'] else 'NO'}")
    
    if not deps['iproxy']:
        print("\n" + "=" * 50)
        print("TO ENABLE USB CONNECTION:")
        print("1. Install Chocolatey (https://chocolatey.org/install)")
        print("2. Run: choco install libimobiledevice")
        print("3. Restart this application")
        print("=" * 50)
    
    # Get connection options
    options = get_all_connection_options()
    print(f"\nConnection Options:")
    for opt in options:
        print(f"  {opt['name']}: {opt['address']}:{opt['port']}")
    
    if deps['device_detected'] and deps['iproxy']:
        print("\nStarting USB tunnel...")
        
        tunnel = USBTunnel(
            local_port=8889,
            on_device_connected=lambda d: print(f"Device: {d.name}"),
            on_tunnel_ready=lambda h, p: print(f"Tunnel ready: {h}:{p}")
        )
        
        tunnel.start()
        
        try:
            while True:
                status = tunnel.get_status()
                print(f"\rTunnel: {status['state']}", end="", flush=True)
                time.sleep(1)
        except KeyboardInterrupt:
            print("\nStopping...")
            tunnel.stop()
    elif deps['device_detected']:
        print("\niPhone detected but iproxy not available.")
        print("Install libimobiledevice to enable USB connection.")

"""
VR Streaming - USB Tunnel Module
=================================
Manages USB tunnel connection to iOS device using pymobiledevice3.
Creates a TCP tunnel that allows the iPhone to communicate via USB.

Author: VR Streaming Project
License: MIT
"""

import threading
import subprocess
import socket
import time
import sys
import logging
import asyncio
from typing import Optional, Callable, List, Dict, Any
from dataclasses import dataclass
from enum import Enum

logger = logging.getLogger(__name__)

# Try to import pymobiledevice3
PYMOBILEDEVICE3_AVAILABLE = False
try:
    from pymobiledevice3.usbmux import list_devices
    from pymobiledevice3.lockdown import create_using_usbmux
    PYMOBILEDEVICE3_AVAILABLE = True
    logger.info("pymobiledevice3 available")
except ImportError as e:
    logger.warning(f"pymobiledevice3 not available: {e}")


class USBDeviceState(Enum):
    """USB device connection state."""
    NOT_FOUND = "not_found"
    FOUND = "found"
    CONNECTED = "connected"
    TUNNEL_ACTIVE = "tunnel_active"
    ERROR = "error"


@dataclass
class iOSDevice:
    """Represents a connected iOS device."""
    udid: str
    name: str
    model: str
    ios_version: str
    connection_type: str  # "USB" or "Network"
    
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
                name="Unknown",
                model="Unknown",
                ios_version="Unknown",
                connection_type="USB"
            )


class USBTunnel:
    """
    Manages USB tunnel to iOS device.
    
    Uses pymobiledevice3's tunneld to create a TCP tunnel over USB,
    allowing the iOS app to connect to localhost when connected via USB.
    """
    
    # Default ports
    LOCAL_PORT = 8889
    REMOTE_PORT = 8889
    
    def __init__(
        self,
        local_port: int = 8889,
        on_device_connected: Optional[Callable[[iOSDevice], None]] = None,
        on_device_disconnected: Optional[Callable[[], None]] = None,
        on_tunnel_ready: Optional[Callable[[str, int], None]] = None
    ):
        """
        Initialize USB tunnel manager.
        
        Args:
            local_port: Local port to use for tunnel
            on_device_connected: Callback when device connects
            on_device_disconnected: Callback when device disconnects
            on_tunnel_ready: Callback when tunnel is ready (host, port)
        """
        self.local_port = local_port
        self._on_device_connected = on_device_connected
        self._on_device_disconnected = on_device_disconnected
        self._on_tunnel_ready = on_tunnel_ready
        
        self.state = USBDeviceState.NOT_FOUND
        self.current_device: Optional[iOSDevice] = None
        
        # Tunnel process/thread
        self._tunnel_process: Optional[subprocess.Popen] = None
        self._tunnel_thread: Optional[threading.Thread] = None
        self._monitor_thread: Optional[threading.Thread] = None
        self._running = False
        
        # Port forwarding socket
        self._forward_socket: Optional[socket.socket] = None
        self._forward_thread: Optional[threading.Thread] = None
        
        logger.info(f"USBTunnel initialized, local_port={local_port}")
    
    def start(self):
        """Start monitoring for USB devices."""
        if self._running:
            logger.warning("USB tunnel already running")
            return
        
        self._running = True
        
        # Start device monitor thread
        self._monitor_thread = threading.Thread(
            target=self._device_monitor_loop,
            name="USBDeviceMonitor",
            daemon=True
        )
        self._monitor_thread.start()
        
        logger.info("USB tunnel monitoring started")
    
    def stop(self):
        """Stop the USB tunnel and monitoring."""
        self._running = False
        
        # Stop tunnel
        self._stop_tunnel()
        
        # Wait for threads
        if self._monitor_thread and self._monitor_thread.is_alive():
            self._monitor_thread.join(timeout=2.0)
        
        logger.info("USB tunnel stopped")
    
    def _device_monitor_loop(self):
        """Monitor for USB device connections."""
        last_device_udid = None
        
        while self._running:
            try:
                devices = self._get_usb_devices()
                
                if devices:
                    device = devices[0]  # Use first device
                    
                    if last_device_udid != device.udid:
                        # New device connected
                        logger.info(f"iOS device connected: {device.name} ({device.model})")
                        self.current_device = device
                        self.state = USBDeviceState.FOUND
                        last_device_udid = device.udid
                        
                        if self._on_device_connected:
                            try:
                                self._on_device_connected(device)
                            except Exception as e:
                                logger.error(f"Device connected callback error: {e}")
                        
                        # Start tunnel
                        self._start_tunnel()
                else:
                    if last_device_udid is not None:
                        # Device disconnected
                        logger.info("iOS device disconnected")
                        self.current_device = None
                        self.state = USBDeviceState.NOT_FOUND
                        last_device_udid = None
                        
                        self._stop_tunnel()
                        
                        if self._on_device_disconnected:
                            try:
                                self._on_device_disconnected()
                            except Exception as e:
                                logger.error(f"Device disconnected callback error: {e}")
                
                time.sleep(2.0)  # Check every 2 seconds
                
            except Exception as e:
                logger.error(f"Device monitor error: {e}")
                time.sleep(5.0)
    
    def _get_usb_devices(self) -> List[iOSDevice]:
        """Get list of connected USB iOS devices."""
        devices = []
        
        if not PYMOBILEDEVICE3_AVAILABLE:
            return devices
        
        try:
            # Get devices via usbmux
            usbmux_devices = list_devices()
            
            for dev in usbmux_devices:
                try:
                    # Only USB devices
                    if hasattr(dev, 'connection_type') and dev.connection_type != 'USB':
                        continue
                    
                    # Create lockdown client to get device info
                    lockdown = create_using_usbmux(serial=dev.serial)
                    device = iOSDevice.from_lockdown(lockdown)
                    devices.append(device)
                    
                except Exception as e:
                    logger.debug(f"Could not get device info: {e}")
                    # Add basic device info
                    devices.append(iOSDevice(
                        udid=dev.serial if hasattr(dev, 'serial') else 'unknown',
                        name="iOS Device",
                        model="Unknown",
                        ios_version="Unknown",
                        connection_type="USB"
                    ))
            
        except Exception as e:
            logger.debug(f"Error listing devices: {e}")
        
        return devices
    
    def _start_tunnel(self):
        """Start the USB tunnel using pymobiledevice3 tunneld."""
        if not self.current_device:
            return
        
        try:
            # Method 1: Try using pymobiledevice3's built-in port forwarding
            self._start_port_forward()
            
        except Exception as e:
            logger.error(f"Failed to start tunnel: {e}")
            self.state = USBDeviceState.ERROR
    
    def _start_port_forward(self):
        """Start port forwarding to device using subprocess."""
        try:
            # Stop any existing tunnel
            self._stop_tunnel()
            
            # Use pymobiledevice3 CLI for port forwarding
            # The command creates a tunnel from local port to the device
            # Format: python -m pymobiledevice3 usbmux forward LOCAL_PORT REMOTE_PORT
            
            cmd = [
                sys.executable, '-m', 'pymobiledevice3',
                'usbmux', 'forward',
                str(self.local_port),  # Local port (PC)
                str(self.local_port),  # Remote port (iPhone)
            ]
            
            # Add device UDID if available
            if self.current_device and self.current_device.udid:
                cmd.extend(['--udid', self.current_device.udid])
            
            logger.info(f"Starting port forward: {' '.join(cmd)}")
            
            self._tunnel_process = subprocess.Popen(
                cmd,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                creationflags=subprocess.CREATE_NO_WINDOW if sys.platform == 'win32' else 0
            )
            
            # Wait a moment for tunnel to establish
            time.sleep(1.0)
            
            # Check if process is still running
            if self._tunnel_process.poll() is None:
                self.state = USBDeviceState.TUNNEL_ACTIVE
                logger.info(f"USB tunnel active on port {self.local_port}")
                
                if self._on_tunnel_ready:
                    self._on_tunnel_ready("127.0.0.1", self.local_port)
            else:
                # Process exited, read error
                _, stderr = self._tunnel_process.communicate()
                error_msg = stderr.decode() if stderr else "Unknown error"
                logger.warning(f"Port forward failed: {error_msg}")
                
                # Fall back to direct TCP (same network)
                self.state = USBDeviceState.CONNECTED
                
        except FileNotFoundError:
            logger.warning("pymobiledevice3 CLI not found")
            self.state = USBDeviceState.CONNECTED
        except Exception as e:
            logger.error(f"Port forward error: {e}")
            self.state = USBDeviceState.CONNECTED
    
    def _stop_tunnel(self):
        """Stop the USB tunnel."""
        if self._tunnel_process:
            try:
                self._tunnel_process.terminate()
                self._tunnel_process.wait(timeout=2.0)
            except Exception:
                try:
                    self._tunnel_process.kill()
                except Exception:
                    pass
            self._tunnel_process = None
        
        if self._forward_socket:
            try:
                self._forward_socket.close()
            except Exception:
                pass
            self._forward_socket = None
        
        if self.state == USBDeviceState.TUNNEL_ACTIVE:
            self.state = USBDeviceState.CONNECTED
    
    def get_connection_info(self) -> Dict[str, Any]:
        """Get current connection information."""
        info = {
            'state': self.state.value,
            'device': None,
            'tunnel_port': None,
            'pymobiledevice3_available': PYMOBILEDEVICE3_AVAILABLE
        }
        
        if self.current_device:
            info['device'] = {
                'name': self.current_device.name,
                'model': self.current_device.model,
                'ios_version': self.current_device.ios_version,
                'udid': self.current_device.udid[:8] + '...' if self.current_device.udid else None
            }
        
        if self.state == USBDeviceState.TUNNEL_ACTIVE:
            info['tunnel_port'] = self.local_port
        
        return info
    
    def is_tunnel_active(self) -> bool:
        """Check if USB tunnel is active."""
        return self.state == USBDeviceState.TUNNEL_ACTIVE
    
    def has_device(self) -> bool:
        """Check if any device is connected."""
        return self.current_device is not None


def get_local_ip() -> str:
    """Get local IP address for same-network connection."""
    try:
        # Create a socket to determine local IP
        s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        s.connect(("8.8.8.8", 80))
        ip = s.getsockname()[0]
        s.close()
        return ip
    except Exception:
        return "127.0.0.1"


def check_usb_dependencies() -> Dict[str, bool]:
    """Check if USB dependencies are installed."""
    return {
        'pymobiledevice3': PYMOBILEDEVICE3_AVAILABLE,
        'itunes_drivers': _check_itunes_drivers(),
    }


def _check_itunes_drivers() -> bool:
    """Check if iTunes/Apple drivers are installed (Windows)."""
    if sys.platform != 'win32':
        return True  # Not needed on other platforms
    
    try:
        import winreg
        # Check for Apple Mobile Device Support
        try:
            key = winreg.OpenKey(
                winreg.HKEY_LOCAL_MACHINE,
                r"SOFTWARE\Apple Inc.\Apple Mobile Device Support"
            )
            winreg.CloseKey(key)
            return True
        except FileNotFoundError:
            pass
        
        # Alternative: check for MobileDevice.dll
        import os
        program_files = os.environ.get('ProgramFiles', 'C:\\Program Files')
        amds_path = os.path.join(
            program_files, 
            'Common Files', 
            'Apple', 
            'Mobile Device Support'
        )
        return os.path.exists(amds_path)
        
    except Exception:
        return False


# Test function
if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO)
    
    print("USB Tunnel Test")
    print("=" * 40)
    
    # Check dependencies
    deps = check_usb_dependencies()
    print(f"pymobiledevice3: {'✓' if deps['pymobiledevice3'] else '✗'}")
    print(f"iTunes drivers: {'✓' if deps['itunes_drivers'] else '✗'}")
    print()
    
    if not deps['pymobiledevice3']:
        print("Install pymobiledevice3: pip install pymobiledevice3")
        sys.exit(1)
    
    def on_device_connected(device):
        print(f"\n✓ Device connected: {device.name}")
        print(f"  Model: {device.model}")
        print(f"  iOS: {device.ios_version}")
    
    def on_device_disconnected():
        print("\n✗ Device disconnected")
    
    def on_tunnel_ready(host, port):
        print(f"\n✓ Tunnel ready at {host}:{port}")
        print("  iPhone app should connect to: 127.0.0.1:8889")
    
    tunnel = USBTunnel(
        local_port=8889,
        on_device_connected=on_device_connected,
        on_device_disconnected=on_device_disconnected,
        on_tunnel_ready=on_tunnel_ready
    )
    
    tunnel.start()
    
    print("Waiting for iOS device...")
    print("Connect your iPhone via USB cable")
    print("Press Ctrl+C to stop\n")
    
    try:
        while True:
            info = tunnel.get_connection_info()
            print(f"\rState: {info['state']}", end='', flush=True)
            time.sleep(1)
    except KeyboardInterrupt:
        print("\n\nStopping...")
    finally:
        tunnel.stop()

"""
VR Streaming - USB Connection Module
=====================================
Handles USB connection detection and network interface discovery.
Provides connection options for USB cable and WiFi connections.

Author: VR Streaming Project
License: MIT
"""

import socket
import subprocess
import sys
import time
import threading
import logging
from typing import Optional, Callable, List, Dict, Any, Tuple
from dataclasses import dataclass
from enum import Enum

logger = logging.getLogger(__name__)

# Try to import pymobiledevice3
PYMOBILEDEVICE3_AVAILABLE = False
try:
    from pymobiledevice3.usbmux import list_devices
    from pymobiledevice3.lockdown import create_using_usbmux
    PYMOBILEDEVICE3_AVAILABLE = True
    logger.info("pymobiledevice3 available for USB device detection")
except ImportError as e:
    logger.debug(f"pymobiledevice3 not available: {e}")


class USBDeviceState(Enum):
    """USB device connection state."""
    NOT_FOUND = "not_found"
    FOUND = "found"
    CONNECTED = "connected"
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
    Manages USB connection detection and provides connection options.
    
    This module detects iOS devices connected via USB and provides
    the appropriate IP addresses for connection.
    """
    
    def __init__(
        self,
        local_port: int = 8889,
        on_device_connected: Optional[Callable[['iOSDevice'], None]] = None,
        on_device_disconnected: Optional[Callable[[], None]] = None,
        on_tunnel_ready: Optional[Callable[[str, int], None]] = None
    ):
        """
        Initialize USB connection manager.
        
        Args:
            local_port: Local port for streaming
            on_device_connected: Callback when device connects
            on_device_disconnected: Callback when device disconnects
            on_tunnel_ready: Callback when connection is ready
        """
        self.local_port = local_port
        self._on_device_connected = on_device_connected
        self._on_device_disconnected = on_device_disconnected
        self._on_tunnel_ready = on_tunnel_ready
        
        self.state = USBDeviceState.NOT_FOUND
        self.current_device: Optional[iOSDevice] = None
        
        # Thread state
        self._running = False
        self._monitor_thread: Optional[threading.Thread] = None
        
        logger.info(f"USBTunnel initialized, port={local_port}")
    
    def start(self):
        """Start monitoring for USB devices."""
        if self._running:
            logger.warning("USB monitor already running")
            return
        
        self._running = True
        
        # Start device monitor thread
        self._monitor_thread = threading.Thread(
            target=self._device_monitor_loop,
            name="USBDeviceMonitor",
            daemon=True
        )
        self._monitor_thread.start()
        
        logger.info("USB device monitoring started")
    
    def stop(self):
        """Stop the USB monitoring."""
        self._running = False
        
        if self._monitor_thread and self._monitor_thread.is_alive():
            self._monitor_thread.join(timeout=2.0)
        
        logger.info("USB monitoring stopped")
    
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
                        self.state = USBDeviceState.CONNECTED
                        last_device_udid = device.udid
                        
                        if self._on_device_connected:
                            try:
                                self._on_device_connected(device)
                            except Exception as e:
                                logger.error(f"Device connected callback error: {e}")
                        
                        # Signal that connection is ready
                        if self._on_tunnel_ready:
                            local_ip = get_local_ip()
                            self._on_tunnel_ready(local_ip, self.local_port)
                else:
                    if last_device_udid is not None:
                        # Device disconnected
                        logger.info("iOS device disconnected")
                        self.current_device = None
                        self.state = USBDeviceState.NOT_FOUND
                        last_device_udid = None
                        
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
                    # Create lockdown client to get device info
                    lockdown = create_using_usbmux(serial=dev.serial)
                    device = iOSDevice.from_lockdown(lockdown)
                    devices.append(device)
                    
                except Exception as e:
                    logger.debug(f"Could not get device info: {e}")
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
    
    def get_connection_info(self) -> Dict[str, Any]:
        """Get current connection information."""
        local_ip = get_local_ip()
        
        info = {
            'state': self.state.value,
            'device': None,
            'local_ip': local_ip,
            'port': self.local_port,
            'pymobiledevice3_available': PYMOBILEDEVICE3_AVAILABLE,
            'connection_options': get_all_connection_options(self.local_port)
        }
        
        if self.current_device:
            info['device'] = {
                'name': self.current_device.name,
                'model': self.current_device.model,
                'ios_version': self.current_device.ios_version,
                'udid': self.current_device.udid[:8] + '...' if self.current_device.udid else None
            }
        
        return info
    
    def has_device(self) -> bool:
        """Check if any device is connected."""
        return self.current_device is not None


def get_local_ip() -> str:
    """Get primary local IP address for network connection."""
    try:
        # Create a socket to determine local IP
        s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        s.connect(("8.8.8.8", 80))
        ip = s.getsockname()[0]
        s.close()
        return ip
    except Exception:
        return "127.0.0.1"


def get_all_network_ips() -> List[Tuple[str, str]]:
    """Get all available network IP addresses with their interface names."""
    ips = []
    
    try:
        # Use socket to get hostname and addresses
        hostname = socket.gethostname()
        
        # Try to get all addresses
        try:
            for info in socket.getaddrinfo(hostname, None, socket.AF_INET):
                ip = info[4][0]
                if ip and ip != '127.0.0.1' and not ip.startswith('169.254'):
                    ips.append(("Network", ip))
        except Exception:
            pass
        
        # Also try ifaddr if available
        try:
            import ifaddr
            adapters = ifaddr.get_adapters()
            for adapter in adapters:
                for ip_obj in adapter.ips:
                    if isinstance(ip_obj.ip, str):  # IPv4
                        ip = ip_obj.ip
                        if ip and ip != '127.0.0.1' and not ip.startswith('169.254'):
                            name = adapter.nice_name
                            if ip not in [i[1] for i in ips]:
                                ips.append((name, ip))
        except ImportError:
            pass
            
    except Exception as e:
        logger.debug(f"Error getting network IPs: {e}")
    
    # Add localhost as fallback
    if not ips:
        ips.append(("Localhost", "127.0.0.1"))
    
    return ips


def get_all_connection_options(port: int = 8889) -> List[Dict[str, str]]:
    """Get all available connection options for the iOS app."""
    options = []
    
    # Get all network IPs
    ips = get_all_network_ips()
    
    for name, ip in ips:
        # Determine connection type
        if 'Wi-Fi' in name or 'WiFi' in name or 'Wireless' in name:
            conn_type = "WiFi"
            icon = "📶"
        elif 'Ethernet' in name or 'Local Area' in name:
            conn_type = "Ethernet"
            icon = "🔌"
        elif 'USB' in name or 'Apple' in name or 'iPhone' in name:
            conn_type = "USB Network"
            icon = "📱"
        else:
            conn_type = "Network"
            icon = "🌐"
        
        options.append({
            'name': name,
            'type': conn_type,
            'icon': icon,
            'ip': ip,
            'port': port,
            'address': f"{ip}:{port}"
        })
    
    return options


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
    
    print("USB Connection Test")
    print("=" * 50)
    
    # Check dependencies
    deps = check_usb_dependencies()
    print(f"pymobiledevice3: {'✓' if deps['pymobiledevice3'] else '✗'}")
    print(f"iTunes drivers: {'✓' if deps['itunes_drivers'] else '✗'}")
    print()
    
    # Show connection options
    print("Available Connection Options:")
    print("-" * 50)
    options = get_all_connection_options(8889)
    for opt in options:
        print(f"  {opt['icon']} {opt['type']}: {opt['address']}")
        print(f"      Interface: {opt['name']}")
    print()
    
    # Test device detection
    if deps['pymobiledevice3']:
        print("Checking for connected iOS devices...")
        
        def on_device_connected(device):
            print(f"\n✓ Device connected: {device.name}")
            print(f"  Model: {device.model}")
            print(f"  iOS: {device.ios_version}")
        
        def on_device_disconnected():
            print("\n✗ Device disconnected")
        
        def on_tunnel_ready(host, port):
            print(f"\n✓ Ready to connect!")
            print(f"  Use IP: {host}:{port} in iPhone app")
        
        tunnel = USBTunnel(
            local_port=8889,
            on_device_connected=on_device_connected,
            on_device_disconnected=on_device_disconnected,
            on_tunnel_ready=on_tunnel_ready
        )
        
        tunnel.start()
        
        print("Monitoring for devices...")
        print("Connect your iPhone via USB cable")
        print("Press Ctrl+C to stop\n")
        
        try:
            while True:
                info = tunnel.get_connection_info()
                status = "📱 Connected" if info['device'] else "⌛ Waiting"
                print(f"\r{status} - IP: {info['local_ip']}:{info['port']}", end='', flush=True)
                time.sleep(1)
        except KeyboardInterrupt:
            print("\n\nStopping...")
        finally:
            tunnel.stop()
    else:
        print("Install pymobiledevice3 for USB device detection:")
        print("  pip install pymobiledevice3")

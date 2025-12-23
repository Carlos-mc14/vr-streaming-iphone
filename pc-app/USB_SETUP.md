# USB Connection Setup Guide

This guide explains how to set up USB cable connection between your PC and iPhone for VR Streaming.

## Why USB?

USB connection provides:
- **Lower latency** (~5-10ms vs 20-50ms WiFi)
- **More stable connection** (no wireless interference)
- **Better for fast-paced games**

## Requirements

1. **Windows PC** with USB port
2. **iPhone** with USB-C or Lightning cable
3. **iTunes** installed (provides Apple Mobile Device drivers)

## Setup Steps

### Step 1: Install iTunes

iTunes is required for the Apple Mobile Device driver.

1. Download iTunes: https://www.apple.com/itunes/download/
2. Install it (you don't need to use iTunes itself)
3. Restart your computer

### Step 2: Install iproxy (Optional but Recommended)

iproxy creates a tunnel that forwards iPhone's localhost to PC.

**Option A: Automatic Installation**
1. Right-click `install_usb_dependencies.bat`
2. Select "Run as administrator"
3. Wait for installation to complete

**Option B: Manual Installation**
1. Install Chocolatey: https://chocolatey.org/install
2. Open PowerShell as Administrator
3. Run: `choco install libimobiledevice`

### Step 3: Connect iPhone

1. Connect iPhone to PC with USB cable
2. **Trust the computer** when iPhone asks
3. Verify connection in iTunes (optional)

### Step 4: Run VR Streaming

1. Run `VRStreaming.exe` on PC
2. Click "Start Streaming"
3. On iPhone, select **USB mode** (cable icon)
4. Address should be `127.0.0.1:8889`
5. Tap Connect

## Troubleshooting

### iPhone not detected

1. Make sure iTunes is installed
2. Trust the computer on iPhone
3. Try a different USB cable
4. Try a different USB port (USB 3.0 preferred)

### Connection fails with USB mode

1. Make sure iproxy is installed: `where iproxy` in PowerShell
2. Check that VR Streaming shows "USB tunnel active"
3. Restart both PC app and iPhone app

### iproxy not found

1. Reinstall libimobiledevice: `choco install libimobiledevice -y`
2. Restart your computer
3. Verify: `iproxy --version`

### Still having issues?

Try WiFi mode as fallback:
1. Connect PC and iPhone to same WiFi network
2. On iPhone app, select **WiFi mode**
3. Enter your PC's IP address (shown in VR Streaming app)

## How USB Connection Works

```
iPhone App                    PC App
    |                           |
    | Connect to 127.0.0.1:8889 |
    |                           |
    v                           v
[iPhone localhost:8889] <-USB-> [iproxy] <-> [PC Server:8889]
```

1. iPhone app connects to its own localhost (127.0.0.1:8889)
2. iproxy intercepts this via USB tunnel
3. Traffic is forwarded to PC's server on port 8889
4. Video/sensor data flows through USB cable

## Without iproxy

If iproxy is not available, the app uses pymobiledevice3 for device detection.
Connection will still work but may require WiFi fallback.

## Technical Details

- **Port**: 8889 (configurable in config.json)
- **Protocol**: TCP socket with VRVI header
- **Video**: JPEG encoded frames
- **Sensors**: JSON formatted gyroscope/accelerometer data

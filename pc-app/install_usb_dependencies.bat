@echo off
echo ========================================
echo VR Streaming - USB Dependencies Installer
echo ========================================
echo.

:: Check for admin privileges
net session >nul 2>&1
if %errorLevel% neq 0 (
    echo ERROR: This script requires administrator privileges.
    echo Right-click and select "Run as administrator"
    pause
    exit /b 1
)

echo Installing USB dependencies for iPhone connection...
echo.

:: Check if Chocolatey is installed
where choco >nul 2>&1
if %errorLevel% neq 0 (
    echo Chocolatey is not installed. Installing...
    echo.
    powershell -NoProfile -ExecutionPolicy Bypass -Command "[System.Net.ServicePointManager]::SecurityProtocol = 3072; iex ((New-Object System.Net.WebClient).DownloadString('https://community.chocolatey.org/install.ps1'))"
    
    if %errorLevel% neq 0 (
        echo Failed to install Chocolatey
        pause
        exit /b 1
    )
    
    :: Refresh environment
    call refreshenv
)

echo Chocolatey is installed.
echo.

:: Install libimobiledevice (includes iproxy)
echo Installing libimobiledevice (iproxy)...
choco install libimobiledevice -y

if %errorLevel% neq 0 (
    echo.
    echo Failed to install libimobiledevice.
    echo Trying alternative method...
    
    :: Try installing from a different source
    choco install ideviceinstaller -y
)

echo.
echo ========================================
echo Installation complete!
echo ========================================
echo.
echo Verifying installation...

:: Verify iproxy is available
where iproxy >nul 2>&1
if %errorLevel% equ 0 (
    echo [OK] iproxy is installed correctly!
    iproxy --help 2>nul | findstr /C:"Usage" >nul && echo [OK] iproxy is working
) else (
    echo [WARNING] iproxy not found in PATH
    echo You may need to restart your computer or add iproxy to PATH manually.
)

echo.
echo ========================================
echo IMPORTANT: Make sure iTunes is installed!
echo ========================================
echo.
echo iTunes provides the Apple Mobile Device driver required
echo for USB communication with iPhones.
echo.
echo Download iTunes: https://www.apple.com/itunes/download/
echo.
echo After installing iTunes, restart your computer and try again.
echo.

pause

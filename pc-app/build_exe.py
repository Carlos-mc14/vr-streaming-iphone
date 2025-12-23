"""
Build executable for VR Streaming PC App
=========================================
Uses PyInstaller to create a standalone executable.

Run: python build_exe.py
"""

import subprocess
import sys
import os
import shutil
from pathlib import Path

def build():
    """Build the executable."""
    print("=" * 60)
    print("VR Streaming - Build Executable")
    print("=" * 60)
    
    # Check if PyInstaller is installed
    try:
        import PyInstaller
        print(f"✓ PyInstaller version: {PyInstaller.__version__}")
    except ImportError:
        print("Installing PyInstaller...")
        subprocess.run([sys.executable, "-m", "pip", "install", "pyinstaller"], check=True)
    
    # Get current directory
    script_dir = Path(__file__).parent
    main_script = script_dir / "main.py"
    
    # Clean previous builds
    dist_dir = script_dir / "dist"
    build_dir = script_dir / "build"
    
    if dist_dir.exists():
        print("Cleaning dist directory...")
        shutil.rmtree(dist_dir)
    
    if build_dir.exists():
        print("Cleaning build directory...")
        shutil.rmtree(build_dir)
    
    # PyInstaller command
    cmd = [
        sys.executable, "-m", "PyInstaller",
        "--name=VRStreaming",
        "--onefile",          # Single executable
        "--windowed",         # No console window
        "--noconfirm",        # Overwrite without asking
        "--clean",            # Clean before build
        
        # Add icon if available
        # "--icon=icon.ico",
        
        # Hidden imports (modules that PyInstaller might miss)
        "--hidden-import=PIL._tkinter_finder",
        "--hidden-import=customtkinter",
        "--hidden-import=dxcam",
        "--hidden-import=mss",
        "--hidden-import=cv2",
        "--hidden-import=numpy",
        "--hidden-import=pynput",
        "--hidden-import=pynput.keyboard._win32",
        "--hidden-import=pynput.mouse._win32",
        
        # Collect all data for customtkinter
        "--collect-all=customtkinter",
        
        # Add data files
        f"--add-data={script_dir / 'config.json'};.",
        
        # Exclude unnecessary modules to reduce size
        "--exclude-module=matplotlib",
        "--exclude-module=scipy",
        "--exclude-module=pandas",
        "--exclude-module=jupyter",
        "--exclude-module=notebook",
        "--exclude-module=IPython",
        "--exclude-module=pytest",
        "--exclude-module=sphinx",
        "--exclude-module=tkinter.test",
        "--exclude-module=unittest",
        "--exclude-module=test",
        
        # The main script
        str(main_script)
    ]
    
    print("\nRunning PyInstaller...")
    print(f"Command: {' '.join(cmd)}")
    print()
    
    try:
        result = subprocess.run(cmd, cwd=script_dir, check=True)
        print()
        print("=" * 60)
        print("✓ Build completed successfully!")
        print("=" * 60)
        
        exe_path = dist_dir / "VRStreaming.exe"
        if exe_path.exists():
            size_mb = exe_path.stat().st_size / (1024 * 1024)
            print(f"\nExecutable: {exe_path}")
            print(f"Size: {size_mb:.1f} MB")
            print()
            print("To run: double-click VRStreaming.exe in the 'dist' folder")
        
    except subprocess.CalledProcessError as e:
        print(f"\n✗ Build failed with error code {e.returncode}")
        sys.exit(1)

if __name__ == "__main__":
    build()

# Windows Installer Build Guide

This guide walks through building a click-to-install Windows package for the Fish Counter Review app.

## Prerequisites

- Windows 10/11
- Python 3.9+ installed and on PATH
- [Inno Setup](https://jrsoftware.org/isinfo.php) installed

## Build steps

1. Open **PowerShell** and run the build script from the repo root:

   ```powershell
   .\scripts\build_windows.ps1
   ```

   This creates:

   - `dist/FishCounterReview/FishCounterReview.exe`
   - `dist/FishCounterReview/app/streamlit_app.py`
   - `dist/FishCounterReview/requirements.txt`

2. Open the Inno Setup script:

   ```
   installer/fish_counter_installer.iss
   ```

   Click **Build → Compile**. The installer will be created in:

   ```
   installer/Output/FishCounterReviewSetup.exe
   ```

3. Distribute `FishCounterReviewSetup.exe` to technicians. After install, they can launch
   **Fish Counter Review** from the desktop or Start Menu.

## Notes

- The app starts a local Streamlit server and opens the browser automatically.
- The installer bundles a portable Python runtime with the app via PyInstaller.

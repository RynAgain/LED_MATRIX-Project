@echo off
echo Installing Python dependencies for Windows...
echo Note: The rgbmatrix package is not available for Windows as it requires Raspberry Pi hardware.
echo Installing Windows-compatible dependencies only...
echo.

pip install -r requirements_windows.txt

echo.
echo Dependencies installation complete.
echo.
echo IMPORTANT NOTES:
echo 1. VLC media player installation instructions:
echo    a. Download VLC from: https://www.videolan.org/vlc/download-windows.html
echo    b. IMPORTANT: If using 64-bit Python, install 64-bit VLC (recommended)
echo    c. If using 32-bit Python, install 32-bit VLC
echo    d. During VLC installation, ensure "Add VLC to PATH" is selected
echo.
echo 2. After VLC installation:
echo    a. Restart your computer to ensure PATH changes take effect
echo    b. VLC should be installed in one of these locations:
echo       - C:\Program Files\VideoLAN\VLC
echo       - C:\Program Files (x86)\VideoLAN\VLC
echo.
echo 3. The LED matrix functionality is only available on Raspberry Pi.
echo    On Windows, you can develop and test the YouTube streaming feature.
echo.
pause

@echo off
echo Fixing Python PATH and Windows App Execution Aliases...
echo.

:: Disable Python App Execution Alias
reg add "HKEY_CURRENT_USER\Software\Microsoft\Windows\CurrentVersion\App Paths\python.exe" /ve /d "C:\Users\rsatt\AppData\Local\Programs\Python\Python313\python.exe" /f
reg add "HKEY_LOCAL_MACHINE\SOFTWARE\Microsoft\Windows\CurrentVersion\App Paths\python.exe" /ve /d "C:\Users\rsatt\AppData\Local\Programs\Python\Python313\python.exe" /f

:: Turn off App Installer for Python
reg add "HKEY_LOCAL_MACHINE\SOFTWARE\Policies\Microsoft\Windows\Explorer" /v "NoUseStoreOpenWith" /t REG_DWORD /d "1" /f
reg add "HKEY_LOCAL_MACHINE\SOFTWARE\Policies\Microsoft\Windows\Explorer" /v "NoNewAppAlert" /t REG_DWORD /d "1" /f

:: Update PATH
set "PYTHON_PATH=C:\Users\rsatt\AppData\Local\Programs\Python\Python313"
set "NEW_PATH=%PATH%;%PYTHON_PATH%;%PYTHON_PATH%\Scripts"

setx PATH "%NEW_PATH%" /M

echo.
echo Changes made:
echo 1. Disabled Windows Python App Installer
echo 2. Added Python directory to system PATH
echo 3. Added Python Scripts directory to system PATH
echo.
echo Please restart your computer for all changes to take effect.
echo After restart, Python commands should work without opening Microsoft Store.
pause

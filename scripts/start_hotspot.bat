@echo off
REM Starts the Windows hosted network the Raspberry Pi connects to.
REM MUST be run as Administrator (right-click -> Run as administrator).
REM Requires a Wi-Fi adapter that supports hosted networks - check with:
REM     netsh wlan show drivers
REM and look for "Hosted network supported : Yes".

net session >nul 2>&1
if %errorLevel% neq 0 (
    echo This script must be run as Administrator.
    pause
    exit /b 1
)

set SSID=drone
set PASSPHRASE=drone1234

echo Restarting the WLAN service...
net stop "wlansvc" >nul 2>&1
net start "wlansvc" >nul 2>&1

echo Configuring hosted network "%SSID%"...
netsh wlan set hostednetwork mode=allow ssid="%SSID%" key="%PASSPHRASE%"

echo Starting Internet Connection Sharing...
net start SharedAccess >nul 2>&1

echo Starting hosted network...
netsh wlan start hostednetwork
if %errorLevel% neq 0 (
    echo.
    echo Failed to start. See docs/TROUBLESHOOTING.md - "Hosted network won't start".
    pause
    exit /b 1
)

echo.
netsh wlan show hostednetwork | findstr /C:"Status" /C:"Number of clients"
echo.
echo Laptop address on this network should be 192.168.137.1:
ipconfig | findstr /C:"192.168.137.1"
echo.
echo Hosted network is up. Power on the Pi and wait ~20 seconds.
pause

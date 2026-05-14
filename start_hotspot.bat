@echo off
net stop "wlansvc"
net start "wlansvc"
netsh wlan set hostednetwork mode=allow ssid="drone" key="drone1234"
netsh wlan start hostednetwork
echo Hosted network started!
pause
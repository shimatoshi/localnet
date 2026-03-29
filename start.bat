@echo off
cd /d "%USERPROFILE%\Desktop\localnet"
echo Localnet server - auto restart on crash
echo.

:loop
echo [%date% %time%] Starting server...
python server.py
echo [%date% %time%] Server stopped. Restarting in 3 seconds...
timeout /t 3 /nobreak >nul
goto loop

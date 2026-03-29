@echo off
cd /d "%USERPROFILE%\Desktop\localnet"
echo Starting localnet on port 8789...
echo Access: http://localhost:8789
echo.
python server.py
pause

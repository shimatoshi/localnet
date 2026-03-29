@echo off
cd /d "%USERPROFILE%\Desktop"

:: Git clone or pull
if exist localnet (
    echo Updating localnet...
    cd localnet
    git pull
) else (
    echo Cloning localnet...
    git clone https://github.com/shimatoshi/localnet.git
    cd localnet
)

:: pip install flask
pip install flask

echo.
echo Setup complete. Run start.bat to start the server.
pause

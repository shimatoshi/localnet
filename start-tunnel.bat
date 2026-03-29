@echo off
echo Starting loophole tunnel...
echo.

:loop
echo [%date% %time%] Starting tunnel...
"%USERPROFILE%\Desktop\loophole\loophole.exe" http 8789 --hostname shimalocalnet
echo [%date% %time%] Tunnel stopped. Restarting in 3 seconds...
timeout /t 3 /nobreak >nul
goto loop

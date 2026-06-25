@echo off
setlocal

set SCRIPT=%~dp0morokoshi.py
set LNK=%APPDATA%\Microsoft\Windows\SendTo\MorokoshiTime.lnk

echo Creating SendTo shortcut...
echo Set ws = CreateObject("WScript.Shell") > "%TEMP%\mk_lnk.vbs"
echo Set sc = ws.CreateShortcut("%LNK%") >> "%TEMP%\mk_lnk.vbs"
echo sc.TargetPath = "python" >> "%TEMP%\mk_lnk.vbs"
echo sc.Arguments = Chr(34) ^& "%SCRIPT%" ^& Chr(34) >> "%TEMP%\mk_lnk.vbs"
echo sc.WorkingDirectory = "%~dp0" >> "%TEMP%\mk_lnk.vbs"
echo sc.Description = "Morokoshi Time" >> "%TEMP%\mk_lnk.vbs"
echo sc.Save >> "%TEMP%\mk_lnk.vbs"
cscript //nologo "%TEMP%\mk_lnk.vbs"
del "%TEMP%\mk_lnk.vbs"

if exist "%LNK%" (
    echo.
    echo SUCCESS: Shortcut created.
    echo Right-click any media file -^> Send To -^> MorokoshiTime
) else (
    echo.
    echo FAILED: Could not create shortcut.
)
echo.
pause
endlocal

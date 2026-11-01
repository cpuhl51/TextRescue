@echo off
REM ===================================================================
REM  TextRescue - exe bauen (nur bauen, nicht starten)
REM  Doppelklick auf diese Datei. Python muss installiert sein
REM  (python.org, beim Setup "Add to PATH" anhaken).
REM ===================================================================
setlocal

echo.
echo === TextRescue: benoetigte Pakete installieren ===
python -m pip install --upgrade pip
python -m pip install keyboard pystray pillow uiautomation pyinstaller
if errorlevel 1 (
    echo.
    echo FEHLER beim Installieren. Ist Python installiert und im PATH?
    echo Pruefe mit:  python --version
    pause
    exit /b 1
)

echo.
echo === exe bauen (mit Logo und Flaggen) ===
pyinstaller --onefile --noconsole --name TextRescue ^
    --icon icon.ico ^
    --add-data "icon.png;." ^
    --add-data "icon_paused.png;." ^
    --add-data "flag_de.png;." ^
    --add-data "flag_en.png;." ^
    textrescue.py
if errorlevel 1 (
    echo.
    echo FEHLER beim Bauen.
    pause
    exit /b 1
)

echo.
echo === Fertig ===
echo Die Datei liegt hier:   dist\TextRescue.exe
echo Starten per Doppelklick. Das Symbol erscheint unten rechts bei der Uhr.
echo.
pause

@echo off
setlocal
cd /d "%~dp0"
title SIGAM v4.8 - Preparacion del panel
if not exist ".venv\Scripts\python.exe" (
    where py >nul 2>&1
    if not errorlevel 1 (
        py -3 -m venv .venv
    ) else (
        python -m venv .venv
    )
    if errorlevel 1 goto ERROR_PYTHON
)
set "PYTHON=%CD%\.venv\Scripts\python.exe"
set "PYTHONW=%CD%\.venv\Scripts\pythonw.exe"
echo Instalando o comprobando componentes SIGAM...
"%PYTHON%" -m pip install --disable-pip-version-check -r requirements.txt
if errorlevel 1 goto ERROR_PIP
if not exist "%PYTHONW%" (
    "%PYTHON%" PANEL_SIGAM.py
) else (
    start "" "%PYTHONW%" "PANEL_SIGAM.py"
)
exit /b 0
:ERROR_PYTHON
echo No se pudo preparar Python. Instala Python 3.10+ y reintenta.
pause
exit /b 1
:ERROR_PIP
echo Error instalando componentes. Revisa tu acceso a Internet.
pause
exit /b 1

@echo off
setlocal
cd /d "%~dp0"
title SIGAM v4.3 - Panel grafico
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
echo Instalando o comprobando dependencias...
"%PYTHON%" -m pip install --disable-pip-version-check -r requirements.txt
if errorlevel 1 goto ERROR_PIP
if exist "%PYTHONW%" (
    start "" "%PYTHONW%" "%CD%\PANEL_SIGAM.py"
) else (
    "%PYTHON%" PANEL_SIGAM.py
)
exit /b 0
:ERROR_PYTHON
echo No se encontro Python o no se pudo preparar su entorno.
pause
exit /b 1
:ERROR_PIP
echo Error al instalar dependencias. Comprueba tu conexion.
pause
exit /b 1

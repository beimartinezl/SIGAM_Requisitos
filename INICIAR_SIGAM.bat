@echo off
setlocal
cd /d "%~dp0"
title SIGAM - Servidor de red local

echo.
echo ================================================
echo       SIGAM - Servidor de red local
echo ================================================
echo.

if not exist ".venv\Scripts\python.exe" (
    echo [1/3] Preparando el entorno de Python...
    where py >nul 2>nul
    if not errorlevel 1 (
        py -3 --version >nul 2>nul
        if not errorlevel 1 (
            py -3 -m venv .venv
        ) else (
            where python >nul 2>nul
            if errorlevel 1 goto SIN_PYTHON
            python -m venv .venv
        )
    ) else (
        where python >nul 2>nul
        if errorlevel 1 goto SIN_PYTHON
        python -m venv .venv
    )
    if errorlevel 1 goto ERROR_VENV
) else (
    echo [1/3] Entorno de Python encontrado.
)

set "PYTHON=%CD%\.venv\Scripts\python.exe"
echo.
echo [2/3] Comprobando componentes necesarios...
"%PYTHON%" -m pip install --disable-pip-version-check -r requirements.txt
if errorlevel 1 goto ERROR_INSTALACION

echo.
echo [3/3] Direccion para otros dispositivos:
for /f "delims=" %%I in ('"%PYTHON%" MOSTRAR_IP.py') do set "SIGAM_IP=%%I"
if not defined SIGAM_IP set "SIGAM_IP=Consulta la IP con ipconfig"
echo.
echo En este computador: http://127.0.0.1:5000
echo En la red local:     http://%SIGAM_IP%:5000
echo.
echo Los celulares y computadores deben estar conectados a la misma red.
echo Si Windows pregunta por el Firewall, permite el acceso en redes privadas.
echo No permitas el acceso en redes publicas y no publiques SIGAM en Internet.
echo.
echo Para detener el servidor, vuelve aqui y presiona Ctrl + C.
echo ================================================
echo.
"%PYTHON%" app.py

echo.
echo SIGAM se ha detenido.
pause
goto FIN

:SIN_PYTHON
echo ERROR: No se encontro Python 3.10 o superior.
echo Instala Python desde https://www.python.org/downloads/
echo Marca la opcion "Add Python to PATH" durante la instalacion.
pause
goto FIN

:ERROR_VENV
echo ERROR: No se pudo preparar el entorno de Python.
pause
goto FIN

:ERROR_INSTALACION
echo ERROR: No se pudieron instalar los componentes.
echo Comprueba tu conexion a Internet e intenta nuevamente.
pause
:FIN
endlocal

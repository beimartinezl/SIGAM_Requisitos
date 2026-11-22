@echo off
setlocal
cd /d "%~dp0"
title SIGAM - Inicio de la aplicacion

echo.
echo ========================================
echo       SIGAM - Sistema de mantenimiento
echo ========================================
echo.

REM Verificar si ya existe el entorno de Python de SIGAM.
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
echo [2/3] Comprobando e instalando los componentes necesarios...
"%PYTHON%" -m pip install --disable-pip-version-check -r requirements.txt
if errorlevel 1 goto ERROR_INSTALACION

echo.
echo [3/3] Iniciando SIGAM...
echo.
echo Cuando aparezca el mensaje de que el servidor esta activo,
echo abre tu navegador y visita: http://127.0.0.1:5000
echo.
echo Para cerrar SIGAM, vuelve a esta ventana y presiona Ctrl + C.
echo ========================================
echo.
"%PYTHON%" app.py

echo.
echo SIGAM se ha detenido.
pause
goto FIN

:SIN_PYTHON
echo.
echo ERROR: No se encontro Python en este computador.
echo Instala Python 3.10 o superior desde https://www.python.org/downloads/
echo Durante la instalacion, marca la opcion "Add Python to PATH".
echo Luego vuelve a ejecutar este archivo.
pause
goto FIN

:ERROR_VENV
echo.
echo ERROR: No se pudo preparar el entorno de Python.
echo Revisa que Python este instalado correctamente y vuelve a intentarlo.
pause
goto FIN

:ERROR_INSTALACION
echo.
echo ERROR: No se pudieron instalar los componentes necesarios.
echo Comprueba tu conexion a Internet e intenta ejecutar este archivo otra vez.
pause
goto FIN

:FIN
endlocal

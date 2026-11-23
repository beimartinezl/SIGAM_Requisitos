@echo off
setlocal
cd /d "%~dp0"
title SIGAM - Reiniciar base de datos

echo ================================================
echo        REINICIAR BASE DE DATOS SIGAM
echo ================================================
echo.
echo ADVERTENCIA: Se eliminaran los activos, avisos,
echo ordenes, intervenciones y cuentas de usuarios.
echo.
echo Primero CIERRA SIGAM en el computador servidor.
echo Se guardara un respaldo antes de eliminar datos.
echo.
set /p CONFIRMACION=Escribe REINICIAR para continuar: 
if not "%CONFIRMACION%"=="REINICIAR" (
    echo Operacion cancelada. No se modificaron datos.
    pause
    exit /b 0
)
python --version >nul 2>&1
if errorlevel 1 (
    echo ERROR: Python no esta disponible.
    pause
    exit /b 1
)
python REINICIAR_BASE_DATOS.py
set "RESULTADO=%ERRORLEVEL%"
if not "%RESULTADO%"=="0" (
    echo ERROR: No se completo el reinicio. Revisa el mensaje anterior.
) else (
    echo.
    echo Al iniciar SIGAM, configura una nueva cuenta administradora.
)
pause
exit /b %RESULTADO%

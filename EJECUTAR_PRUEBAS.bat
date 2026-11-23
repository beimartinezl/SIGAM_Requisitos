@echo off
setlocal
cd /d "%~dp0"
echo ==========================================
echo     SIGAM v4.3 - PRUEBAS AUTOMATIZADAS
echo ==========================================
python --version
if errorlevel 1 (echo ERROR: Python no esta instalado o no esta en PATH.& pause & exit /b 1)
python -m pip install -r requirements.txt
if errorlevel 1 (echo ERROR al instalar dependencias.& pause & exit /b 1)
python -m pip install pytest
if errorlevel 1 (echo ERROR al instalar pytest.& pause & exit /b 1)
python -m pytest tests -v
set TEST_RESULT=%ERRORLEVEL%
echo.
if "%TEST_RESULT%"=="0" (echo RESULTADO: todas las pruebas aprobadas.) else (echo RESULTADO: existen pruebas fallidas.)
pause
exit /b %TEST_RESULT%

@echo off
cd /d "%~dp0"
python -m pip install -r requirements-dev.txt
python -m pytest -v
echo.
pause

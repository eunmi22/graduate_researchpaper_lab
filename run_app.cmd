@echo off
cd /d "%~dp0"
python check_install.py
if errorlevel 1 (
  pause
  exit /b 1
)
python -m streamlit run "%~dp0app.py"
pause

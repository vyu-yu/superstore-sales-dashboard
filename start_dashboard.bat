@echo off
cd /d "%~dp0"
echo Starting Superstore Dashboard...
echo.
".venv\Scripts\python.exe" -m streamlit run "dashboard\app.py"
pause

@echo off
setlocal

REM Always run from the directory containing this launcher.
cd /d "%~dp0"

set "VENV_DIR=%~dp0ICT\.venv"
set "VENV_PYTHON=%VENV_DIR%\Scripts\python.exe"

echo ============================================================
echo Dynamic Moisture-Triggered Seed Release System
echo ============================================================
echo.

REM Create the environment only when it does not already exist.
if exist "%VENV_PYTHON%" goto install_dependencies

echo Creating the Python virtual environment in ICT\.venv...
python -m venv "%VENV_DIR%"
if errorlevel 1 goto environment_error

:install_dependencies
echo Checking and installing application dependencies...
"%VENV_PYTHON%" -m pip install -r "%~dp0requirements.txt"
if errorlevel 1 goto dependency_error

echo.
echo Starting the dashboard...
echo Keep this window open while using the application.
echo Press Ctrl+C in this window to stop the dashboard.
echo.

"%VENV_PYTHON%" -m streamlit run "%~dp0final_dashboard.py"
if errorlevel 1 goto dashboard_error
goto end

:environment_error
echo.
echo ERROR: Could not create the virtual environment.
echo Ensure Python is installed and available using the python command.
goto failed

:dependency_error
echo.
echo ERROR: Could not install application dependencies.
echo Check the messages above and your internet connection.
goto failed

:dashboard_error
echo.
echo ERROR: The dashboard stopped with an error.
echo Review the messages above for details.
goto failed

:failed
echo.
pause
endlocal
exit /b 1

:end
endlocal
exit /b 0
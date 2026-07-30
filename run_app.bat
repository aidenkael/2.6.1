@echo off
setlocal
cd /d "%~dp0"

if not exist ".venv-311\Scripts\python.exe" (
  py -3.11 -m venv .venv-311 || exit /b 1
)
.venv-311\Scripts\python.exe -c "import PySide6, profit_accounting_26" >nul 2>nul
if errorlevel 1 (
  .venv-311\Scripts\python.exe -m pip install --upgrade pip || exit /b 1
  .venv-311\Scripts\python.exe -m pip install -e . || exit /b 1
)

set QT_ENABLE_HIGHDPI_SCALING=1
start "Profit Accounting 2.6" .venv-311\Scripts\pythonw.exe -m profit_accounting_26.ui.app
endlocal

@echo off
setlocal
cd /d "%~dp0"
set PYTHONUTF8=1
set QT_QPA_PLATFORM=offscreen

if not exist ".venv-311\Scripts\python.exe" (
  py -3.11 -m venv .venv-311 || exit /b 1
)

.venv-311\Scripts\python.exe -m pip install --upgrade pip || exit /b 1
.venv-311\Scripts\python.exe -m pip install -e ".[dev]" || exit /b 1
.venv-311\Scripts\python.exe -m compileall -q src tests tools || exit /b 1
.venv-311\Scripts\python.exe -m pytest -q || exit /b 1
.venv-311\Scripts\python.exe tools\sensitive_scan.py || exit /b 1

echo Release candidate verification passed.
endlocal

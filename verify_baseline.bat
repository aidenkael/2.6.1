@echo off
setlocal
cd /d "%~dp0"
if exist ".venv-311\Scripts\python.exe" (
  set "PY=.venv-311\Scripts\python.exe"
) else (
  set "PY=py -3.11"
)
%PY% -m pytest -q
if errorlevel 1 exit /b 1
%PY% tools\sensitive_scan.py
if errorlevel 1 exit /b 1
echo Baseline verification passed.

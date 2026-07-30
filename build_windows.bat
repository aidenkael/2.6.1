@echo off
setlocal
cd /d "%~dp0"
set PYTHONUTF8=1
set QT_QPA_PLATFORM=offscreen

call verify_release_candidate.bat || exit /b 1

if not exist ".venv-build\Scripts\python.exe" (
  py -3.11 -m venv .venv-build || exit /b 1
)
.venv-build\Scripts\python.exe -m pip install --upgrade pip || exit /b 1
.venv-build\Scripts\python.exe -m pip install -e ".[dev]" -r requirements-build.txt || exit /b 1
.venv-build\Scripts\pyinstaller.exe --noconfirm --clean ProfitAccounting26.spec || exit /b 1
.venv-build\Scripts\python.exe tools\build_release.py || exit /b 1

echo Windows release package created under release\
endlocal

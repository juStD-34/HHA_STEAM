@echo off
where python >nul 2>nul
if errorlevel 1 (
  where winget >nul 2>nul
  if errorlevel 1 (
    echo Python chua duoc cai dat. Hay cai Python 3 truoc.
    echo Goi y: https://www.python.org/downloads/
    exit /b 1
  ) else (
    winget install -e --id Python.Python.3 --accept-source-agreements --accept-package-agreements
  )
)

python --version

python -m pip --version >nul 2>nul
if errorlevel 1 (
  python -m ensurepip --upgrade
)

python -m pip install --upgrade pip
python -m pip install -r requirements.txt

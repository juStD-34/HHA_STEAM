#!/bin/sh
set -e

if ! command -v python3 >/dev/null 2>&1; then
  if ! command -v brew >/dev/null 2>&1; then
    /bin/bash -c "$(curl -fsSL https://raw.githubusercontent.com/Homebrew/install/HEAD/install.sh)"
  fi
  brew install python
fi

python3 --version

if ! python3 -m pip --version >/dev/null 2>&1; then
  python3 -m ensurepip --upgrade
fi

python3 -m pip install --upgrade pip
python3 -m pip install -r requirements.txt

#!/bin/zsh
set -e
cd "${0:A:h}"
.venv/bin/python scripts/launcher.py stop

#!/bin/zsh
cd "${0:A:h}"
export PATH="/opt/homebrew/bin:/usr/local/bin:$PATH"
if [[ ! -x .venv/bin/python ]]; then
  print 'Python environment missing. Run ./scripts/setup.command'
  exit 1
fi
.venv/bin/python scripts/doctor.py

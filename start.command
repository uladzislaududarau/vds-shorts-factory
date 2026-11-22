#!/bin/zsh
set -e
cd "${0:A:h}"
export PATH="/opt/homebrew/bin:/usr/local/bin:$PATH"
if [[ ! -x .venv/bin/python ]]; then
  print 'Dependencies are missing. Run ./scripts/setup.command first.'
  exit 1
fi
.venv/bin/python scripts/launcher.py start "$@"

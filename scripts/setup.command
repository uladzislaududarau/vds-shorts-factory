#!/bin/zsh
set -e
cd "${0:A:h:h}"
export PATH="/opt/homebrew/bin:/usr/local/bin:$PATH"
export UV_CACHE_DIR="$PWD/.tools/uv-cache"
export UV_PYTHON_INSTALL_DIR="$PWD/.tools/python"
export UV_HTTP_TIMEOUT=300
if ! command -v ffmpeg >/dev/null || ! command -v ffprobe >/dev/null; then
  print 'FFmpeg/FFprobe missing. Install them with your package manager after reviewing system changes.'
  exit 1
fi
if ! command -v node >/dev/null; then
  print 'Node.js 22.12+ is required.'
  exit 1
fi
mkdir -p .tools
if [[ ! -x .tools/uv ]]; then
  curl -LsSf --max-time 120 https://astral.sh/uv/install.sh -o .tools/install-uv.sh
  UV_INSTALL_DIR="$PWD/.tools" UV_NO_MODIFY_PATH=1 sh .tools/install-uv.sh
fi
.tools/uv venv --python 3.11 --allow-existing .venv
.tools/uv pip install --python .venv/bin/python --no-deps -r backend/requirements-runtime.lock
npm --prefix frontend install --cache "$PWD/.tools/npm-cache" --no-audit --no-fund
npm --prefix frontend run build
chmod +x start.command stop.command doctor.command
print 'Ready. Run ./start.command'

#!/bin/bash
# VDS Shorts Factory — установка, обновление и удаление на macOS (Apple Silicon и Intel) и Linux (x86_64 и ARM64).
#
#   Установить или обновить:  curl -fsSL https://raw.githubusercontent.com/uladzislaududarau/vds-shorts-factory/main/install.sh | bash
#   Удалить (видео, проекты и ключи сохраняются):  ... | bash -s -- --uninstall
#   Удалить полностью, вместе с видео и проектами:  ... | bash -s -- --uninstall --purge
#
# Ставит всё в папку пользователя: свой Python, библиотеки, FFmpeg и Node.js.
# Homebrew, Xcode, apt и права администратора не нужны.
set -euo pipefail

REPO="${SHORTS_FACTORY_REPO:-uladzislaududarau/vds-shorts-factory}"
BRANCH="${SHORTS_FACTORY_BRANCH:-main}"
SOURCE="${SHORTS_FACTORY_SOURCE:-}"        # локальная папка с кодом вместо GitHub (для проверки установщика)
NEED_FREE_GB=4
NODE_VERSION="v26.13.1"
FFMPEG_BASE="https://ffmpeg.martin-riedl.de/download"

say()  { printf '\n\033[1m%s\033[0m\n' "$*"; }
info() { printf '   %s\n' "$*"; }
fail() { printf '\n\033[31mОшибка: %s\033[0m\n' "$*" >&2; exit 1; }

# ---- платформа: зафиксированные сборки FFmpeg 9.1 / Node.js и их SHA-256 (опубликованы производителями)
case "$(uname -s)" in
  Darwin)
    OS=macos
    if [ "$(sysctl -n hw.optional.arm64 2>/dev/null || echo 0)" = "1" ]; then ARCH=arm64; else ARCH=x64; fi
    APP_HOME="${SHORTS_FACTORY_HOME:-$HOME/Library/Application Support/VDS Shorts Factory}" ;;
  Linux)
    OS=linux
    case "$(uname -m)" in x86_64|amd64) ARCH=x64 ;; aarch64|arm64) ARCH=arm64 ;; *) fail "процессор $(uname -m) не поддерживается." ;; esac
    APP_HOME="${SHORTS_FACTORY_HOME:-${XDG_DATA_HOME:-$HOME/.local/share}/vds-shorts-factory}" ;;
  *) fail "этот установщик для macOS и Linux. Для Windows используйте install.ps1." ;;
esac
case "$OS-$ARCH" in
  macos-arm64) FFMPEG_DIR=macos/arm64/1795207104_9.1
    FFMPEG_SHA=1f66e9a690a7f1c9e60b012379f8869c11818d1797f45b21dbb2f2564ba61ae1; FFPROBE_SHA=6ef2df5f575042923a28537ab37adf936f28bf3e7b85de23a1447ed447ec1dbd
    NODE_NAME=darwin-arm64; NODE_SHA=aec2514ea1ceb2ba52455e9ec65986f6749a06dd759e5db2a72e6889668c9735 ;;
  macos-x64) FFMPEG_DIR=macos/amd64/1795212433_9.1
    FFMPEG_SHA=35b3d82cccc2c1d644d49d15f5e57eb913a08ef68f798042c90eecec62c51f1e; FFPROBE_SHA=41ca7b7cba7992e33f1da3f1bf54db8ec103a4d387b1bfac3162062e8b1074ad
    NODE_NAME=darwin-x64; NODE_SHA=82bb96078a24ca50b9c9a38f2379e6be6d87171fcd400fc14c8934b3bce96e2f ;;
  linux-x64) FFMPEG_DIR=linux/amd64/1795205506_9.1
    FFMPEG_SHA=707d4fa675932cc310e39e1506ac9224049786119689e345fed1c453a8a0896e; FFPROBE_SHA=5e4c53c9c86d6371027efa83d62c2cea00e02ded0234d8cc952d06c9259e4b33
    NODE_NAME=linux-x64; NODE_SHA=518674de2b621728a5e4486f5fb3b7d2900bb3cc4aa97969edaa463db99f9778 ;;
  linux-arm64) FFMPEG_DIR=linux/arm64/1795204341_9.1
    FFMPEG_SHA=e42242dd20b01cf9fe6cff1902b6e5e72be07c2b551d95abc8f332cdb0ff7d86; FFPROBE_SHA=a1561aa2136bce9f51dac9b13be4480466a3031f82907d551619dcdc3b867ccc
    NODE_NAME=linux-arm64; NODE_SHA=80a330b35415382878df18d41afbd106ea89bfb3be0087d6608e289a14c5cc7d ;;
esac
# Apple Silicon: MLX Whisper on the GPU. Everything else: faster-whisper on the CPU.
case "$OS-$ARCH" in
  macos-arm64) LOCK=backend/requirements-runtime.lock; SPEECH=mlx_whisper ;;
  macos-x64)   LOCK=backend/requirements-macos-intel.lock; SPEECH=faster_whisper ;;
  *)           LOCK=backend/requirements-portable.lock; SPEECH=faster_whisper ;;
esac
PY="$APP_HOME/.venv/bin/python"

download() {  # url target [sha256]
  local tries=0
  until curl -fL --progress-bar --retry 3 --connect-timeout 20 -C - -o "$2" "$1"; do
    [ $? -eq 33 ] && rm -f "$2"   # the server can't resume (GitHub archives): start this file over
    tries=$((tries + 1)); [ "$tries" -ge 5 ] && fail "не удалось скачать $1. Проверьте интернет и запустите команду ещё раз — загрузка продолжится."
    sleep 3
  done
  if [ -n "${3:-}" ]; then
    local actual; actual="$( (shasum -a 256 "$2" 2>/dev/null || sha256sum "$2") | cut -d' ' -f1)"
    if [ "$actual" != "$3" ]; then rm -f "$2"; fail "контрольная сумма $(basename "$2") не совпала — файл повреждён или подменён. Запустите установку ещё раз."; fi
  fi
}

stop_server() {
  if [ -x "$PY" ] && [ -f "$APP_HOME/scripts/launcher.py" ]; then "$PY" "$APP_HOME/scripts/launcher.py" stop >/dev/null 2>&1 || true; fi
}

remove_shortcuts() {
  if [ "$OS" = linux ]; then
    if [ -x "$PY" ]; then "$PY" "$APP_HOME/scripts/linux_app.py" remove >/dev/null 2>&1 || true; fi
    return
  fi
  local app plist lsregister=/System/Library/Frameworks/CoreServices.framework/Frameworks/LaunchServices.framework/Support/lsregister
  for app in "/Applications/VDS Shorts Factory.app" "$HOME/Applications/VDS Shorts Factory.app"; do
    plist="$app/Contents/Info.plist"
    # Только наш лаунчер: чужое приложение с тем же именем не трогаем.
    if [ -f "$plist" ] && [ "$(/usr/libexec/PlistBuddy -c 'Print :CFBundleIdentifier' "$plist" 2>/dev/null)" = "local.shorts-factory.launcher" ]; then
      "$lsregister" -u "$app" >/dev/null 2>&1 || true
      rm -rf "$app"
    fi
  done
}

uninstall() {
  say "Удаляю VDS Shorts Factory"
  stop_server
  remove_shortcuts
  [ -d "$APP_HOME" ] || { info "Папка программы не найдена — удалять нечего."; exit 0; }
  if [ "${1:-}" = "--purge" ]; then
    rm -rf "$APP_HOME"
    info "Удалено полностью, включая видео, проекты и ключи."
  else
    find "$APP_HOME" -mindepth 1 -maxdepth 1 ! -name data ! -name database ! -name .secrets -exec rm -rf {} +
    info "Программа удалена. Видео, проекты и ключи сохранены в:"
    info "$APP_HOME"
    info "Повторная установка подхватит их автоматически."
  fi
  exit 0
}

install_tools() {
  local tools="$APP_HOME/.tools" tmp="$1"
  mkdir -p "$tools/bin"
  if [ -x "$tools/bin/ffmpeg" ] && [ -x "$tools/bin/ffprobe" ]; then
    info "FFmpeg уже установлен."
  elif [ "$OS" = macos ] && [ -x /opt/homebrew/bin/ffmpeg ] && [ -x /opt/homebrew/bin/ffprobe ]; then
    info "Использую FFmpeg из Homebrew."
  else
    info "Скачиваю FFmpeg 9.1 (~60 МБ)…"
    download "$FFMPEG_BASE/$FFMPEG_DIR/ffmpeg.zip" "$tmp/ffmpeg.zip" "$FFMPEG_SHA"
    download "$FFMPEG_BASE/$FFMPEG_DIR/ffprobe.zip" "$tmp/ffprobe.zip" "$FFPROBE_SHA"
    # Python's zipfile instead of unzip, which minimal Linux systems may lack.
    "$PY" -m zipfile -e "$tmp/ffmpeg.zip" "$tools/bin"
    "$PY" -m zipfile -e "$tmp/ffprobe.zip" "$tools/bin"
    chmod +x "$tools/bin/ffmpeg" "$tools/bin/ffprobe"
  fi
  if [ -x "$tools/bin/node" ]; then
    info "Node.js уже установлен."
  elif [ "$OS" = macos ] && [ -x /opt/homebrew/bin/node ]; then
    info "Использую Node.js из Homebrew."
  else
    info "Скачиваю Node.js $NODE_VERSION (~50 МБ) — нужен для загрузки видео с YouTube…"
    local name="node-$NODE_VERSION-$NODE_NAME"
    download "https://nodejs.org/dist/$NODE_VERSION/$name.tar.gz" "$tmp/node.tar.gz" "$NODE_SHA"
    rm -rf "${tools:?}/$name"
    tar -xzf "$tmp/node.tar.gz" -C "$tools"
    ln -sf "../$name/bin/node" "$tools/bin/node"
  fi
  local ffmpeg="$tools/bin/ffmpeg"; [ -x "$ffmpeg" ] || ffmpeg=/opt/homebrew/bin/ffmpeg
  "$ffmpeg" -version >/dev/null 2>&1 || fail "FFmpeg не запускается."
}

main() {
  if [ "${1:-}" = "--uninstall" ]; then uninstall "${2:-}"; fi
  local free_gb
  free_gb=$(( $(df -Pk "$HOME" | awk 'NR==2 {print $4}') / 1024 / 1024 ))
  [ "$free_gb" -ge "$NEED_FREE_GB" ] || fail "мало места на диске: свободно ${free_gb} ГБ, нужно хотя бы ${NEED_FREE_GB} ГБ."

  tmp="$(mktemp -d)"; trap 'rm -rf "${tmp:-}"' EXIT   # global: the EXIT trap runs after main returns
  say "1/5 · Загружаю VDS Shorts Factory"
  mkdir -p "$tmp/code"
  if [ -n "$SOURCE" ]; then
    tar -C "$SOURCE" --exclude=./.git --exclude=./.venv --exclude=./.tools --exclude=./.run --exclude=./.secrets \
        --exclude=./data --exclude=./database --exclude=node_modules --exclude=__pycache__ --exclude=.pytest_cache -cf - . \
      | tar -C "$tmp/code" -xf -
  else
    [ -n "$REPO" ] || fail "в установщике не указан репозиторий GitHub (REPO)."
    download "https://codeload.github.com/$REPO/tar.gz/refs/heads/$BRANCH" "$tmp/code.tar.gz"
    tar -xzf "$tmp/code.tar.gz" -C "$tmp/code" --strip-components 1 || fail "скачанный архив с кодом повреждён. Запустите установку ещё раз."
  fi
  [ -f "$tmp/code/backend/main.py" ] && [ -f "$tmp/code/frontend/dist/index.html" ] || fail "скачанный код неполный."

  if [ -d "$APP_HOME/backend" ]; then info "Найдена установленная версия — обновляю. Видео и проекты сохранятся."; stop_server; fi
  mkdir -p "$APP_HOME"
  # Replace the program files; the user's data, keys and installed tools stay untouched.
  find "$APP_HOME" -mindepth 1 -maxdepth 1 ! -name data ! -name database ! -name .secrets ! -name .venv ! -name .tools ! -name .run -exec rm -rf {} +
  cp -R "$tmp/code/." "$APP_HOME/"

  say "2/5 · Устанавливаю Python и библиотеки (первый раз — несколько минут)"
  cd "$APP_HOME"
  mkdir -p .tools
  if [ ! -x .tools/uv ]; then
    download "https://astral.sh/uv/install.sh" "$tmp/install-uv.sh"
    UV_INSTALL_DIR="$APP_HOME/.tools" UV_NO_MODIFY_PATH=1 sh "$tmp/install-uv.sh" >/dev/null
  fi
  # Few parallel downloads: on a slow link dozens of them starve each other until each one times out.
  export UV_CACHE_DIR="$APP_HOME/.tools/uv-cache" UV_PYTHON_INSTALL_DIR="$APP_HOME/.tools/python" UV_HTTP_TIMEOUT=300 UV_CONCURRENT_DOWNLOADS=2
  local attempt=1
  until .tools/uv venv --quiet --python 3.11 --allow-existing .venv && .tools/uv pip install --python .venv/bin/python --no-deps -r "$LOCK"; do
    [ "$attempt" -ge 10 ] && fail "интернет слишком нестабилен. Запустите команду ещё раз — уже скачанное повторно не загружается."
    attempt=$((attempt + 1)); info "Связь прервалась — продолжаю с места обрыва (попытка $attempt из 10)…"; sleep 5
  done
  .venv/bin/python -c "import fastapi, cv2, $SPEECH" || fail "библиотеки установились с ошибкой."

  say "3/5 · Устанавливаю FFmpeg и Node.js"
  install_tools "$tmp"

  say "4/5 · Создаю ярлык VDS Shorts Factory"
  if [ "$OS" = macos ]; then info "$(.venv/bin/python scripts/build_app.py)"; else .venv/bin/python scripts/linux_app.py install; fi

  say "5/5 · Запускаю"
  .venv/bin/python scripts/launcher.py start ${SHORTS_FACTORY_NO_OPEN:+--no-open}

  say "Готово! VDS Shorts Factory открыт в браузере: http://127.0.0.1:8765"
  if [ "$OS" = macos ]; then
    info "Дальше запускайте его как обычное приложение — из Launchpad или папки «Программы»."
    info "Чтобы закрепить в Dock: откройте приложение, правый клик по иконке в Dock → Параметры → Оставить в Dock."
  else
    info "Дальше запускайте его из меню приложений: «VDS Shorts Factory»."
  fi
  info "Обновить: запустите эту же команду ещё раз. Видео и проекты сохранятся."
}

main "$@"

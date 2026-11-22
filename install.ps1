# VDS Shorts Factory — установка, обновление и удаление на Windows 10/11 (x64).
#
#   Установить или обновить (PowerShell):
#     irm https://raw.githubusercontent.com/uladzislaududarau/vds-shorts-factory/main/install.ps1 | iex
#   Удалить (видео, проекты и ключи сохраняются):
#     $env:VDS_ACTION='uninstall'; irm https://raw.githubusercontent.com/uladzislaududarau/vds-shorts-factory/main/install.ps1 | iex
#   Удалить полностью, вместе с видео и проектами:  $env:VDS_ACTION='purge'; irm ... | iex
#
# Ставит всё в «%LOCALAPPDATA%\VDS Shorts Factory»: свой Python, библиотеки, FFmpeg и Node.js.
# Права администратора не нужны. Создаёт ярлыки в меню «Пуск» и на рабочем столе.

$ErrorActionPreference = 'Stop'
$ProgressPreference = 'SilentlyContinue'   # the progress bar makes Invoke-WebRequest many times slower

function Install-VdsShortsFactory {
  $Repo    = if ($env:VDS_REPO) { $env:VDS_REPO } else { 'uladzislaududarau/vds-shorts-factory' }
  $Branch  = if ($env:VDS_BRANCH) { $env:VDS_BRANCH } else { 'main' }
  $Source  = $env:VDS_SOURCE                                           # локальная папка с кодом (для проверки)
  $AppHome = if ($env:VDS_HOME) { $env:VDS_HOME } else { Join-Path $env:LOCALAPPDATA 'VDS Shorts Factory' }
  $Action  = $env:VDS_ACTION

  # Зафиксированные сборки и их SHA-256 (проверяются после скачивания).
  $FfmpegUrl = 'https://www.gyan.dev/ffmpeg/builds/packages/ffmpeg-9.0.2-essentials_build.zip'
  $FfmpegSha = '60f467265b1e312373dbcd92200c2618a74850f98d3d078e94296bb3fa2047ba'
  $NodeUrl   = 'https://nodejs.org/dist/v26.13.1/node-v26.13.1-win-x64.zip'
  $NodeSha   = 'e2edda75bfb089654705cf65a13b58933bfd5f57148e8ebda916f58a2474f1f7'
  $UvUrl     = 'https://github.com/astral-sh/uv/releases/download/0.13.8/uv-x86_64-pc-windows-msvc.zip'
  $UvSha     = '529e78a9cec6cd7e3e014f7ecd8bda0c113969d4ed0f2efeedb85c30943325b8'
  $NeedFreeGB = 5

  function Say($text)  { Write-Host ''; Write-Host $text -ForegroundColor White }
  function Info($text) { Write-Host "   $text" }
  function Fail($text) { Write-Host ''; Write-Host "Ошибка: $text" -ForegroundColor Red; throw 'VDS Shorts Factory: установка остановлена' }

  function Download($url, $target, $sha) {
    for ($try = 1; $try -le 5; $try++) {
      try { Invoke-WebRequest -Uri $url -OutFile $target -UseBasicParsing; break }
      catch { if ($try -eq 5) { Fail "не удалось скачать $url. Проверьте интернет и запустите команду ещё раз." }; Start-Sleep 3 }
    }
    if ($sha -and (Get-FileHash -Algorithm SHA256 -LiteralPath $target).Hash.ToLower() -ne $sha) {
      Remove-Item -LiteralPath $target -Force
      Fail "контрольная сумма $(Split-Path $target -Leaf) не совпала — файл повреждён или подменён. Запустите установку ещё раз."
    }
  }

  $Python = Join-Path $AppHome '.venv\Scripts\python.exe'
  function Stop-Server {
    if ((Test-Path -LiteralPath $Python) -and (Test-Path -LiteralPath (Join-Path $AppHome 'scripts\launcher.py'))) {
      & $Python (Join-Path $AppHome 'scripts\launcher.py') stop *> $null
    }
  }

  if ($Action -eq 'uninstall' -or $Action -eq 'purge') {
    Say 'Удаляю VDS Shorts Factory'
    Stop-Server
    if (Test-Path -LiteralPath $Python) { & $Python (Join-Path $AppHome 'scripts\windows_app.py') remove *> $null }
    if (-not (Test-Path -LiteralPath $AppHome)) { Info 'Папка программы не найдена — удалять нечего.'; return }
    if ($Action -eq 'purge') {
      Remove-Item -LiteralPath $AppHome -Recurse -Force
      Info 'Удалено полностью, включая видео, проекты и ключи.'
    } else {
      Get-ChildItem -LiteralPath $AppHome -Force | Where-Object { $_.Name -notin @('data', 'database', '.secrets') } |
        Remove-Item -Recurse -Force
      Info 'Программа удалена. Видео, проекты и ключи сохранены в:'
      Info $AppHome
      Info 'Повторная установка подхватит их автоматически.'
    }
    return
  }

  if ($env:PROCESSOR_ARCHITECTURE -ne 'AMD64') { Fail 'нужна 64-битная Windows 10 или 11 на процессоре Intel/AMD. Windows на ARM пока не поддерживается.' }
  $drive = (Split-Path -Qualifier $env:LOCALAPPDATA).TrimEnd(':')
  $freeGB = [math]::Floor((Get-PSDrive $drive).Free / 1GB)
  if ($freeGB -lt $NeedFreeGB) { Fail "мало места на диске ${drive}: свободно $freeGB ГБ, нужно хотя бы $NeedFreeGB ГБ." }

  $tmp = Join-Path ([IO.Path]::GetTempPath()) ('vds-' + [Guid]::NewGuid().ToString('N'))
  New-Item -ItemType Directory -Path $tmp | Out-Null
  try {
    Say '1/5 · Загружаю VDS Shorts Factory'
    $code = Join-Path $tmp 'code'
    if ($Source) {
      $code = $Source
    } else {
      if (-not $Repo) { Fail 'в установщике не указан репозиторий GitHub (VDS_REPO).' }
      Download "https://codeload.github.com/$Repo/zip/refs/heads/$Branch" (Join-Path $tmp 'code.zip') $null
      Expand-Archive -LiteralPath (Join-Path $tmp 'code.zip') -DestinationPath $code
      $code = (Get-ChildItem -LiteralPath $code -Directory | Select-Object -First 1).FullName
    }
    if (-not ((Test-Path (Join-Path $code 'backend\main.py')) -and (Test-Path (Join-Path $code 'frontend\dist\index.html')))) {
      Fail 'скачанный код неполный.'
    }
    $updating = Test-Path -LiteralPath (Join-Path $AppHome 'backend')
    if ($updating) { Info 'Найдена установленная версия — обновляю. Видео и проекты сохранятся.'; Stop-Server }
    New-Item -ItemType Directory -Force -Path $AppHome | Out-Null
    # /MIR replaces the code; /XD keeps the user's data, keys and installed tools untouched.
    robocopy $code $AppHome /MIR /NFL /NDL /NJH /NJS /NP /XD data database .secrets .venv .tools .run .git node_modules __pycache__ .pytest_cache | Out-Null
    if ($LASTEXITCODE -ge 8) { Fail "не удалось скопировать файлы программы (robocopy $LASTEXITCODE)." }

    Say '2/5 · Устанавливаю FFmpeg, Node.js и Python'
    $tools = Join-Path $AppHome '.tools'
    $bin = Join-Path $tools 'bin'
    New-Item -ItemType Directory -Force -Path $bin | Out-Null
    if ((Test-Path (Join-Path $bin 'ffmpeg.exe')) -and (Test-Path (Join-Path $bin 'ffprobe.exe'))) { Info 'FFmpeg уже установлен.' }
    else {
      Info 'Скачиваю FFmpeg 9.0.2 (~115 МБ)…'
      Download $FfmpegUrl (Join-Path $tmp 'ffmpeg.zip') $FfmpegSha
      Expand-Archive -LiteralPath (Join-Path $tmp 'ffmpeg.zip') -DestinationPath (Join-Path $tmp 'ffmpeg')
      Get-ChildItem -Path (Join-Path $tmp 'ffmpeg') -Recurse -Include ffmpeg.exe, ffprobe.exe | Copy-Item -Destination $bin -Force
    }
    if (Test-Path (Join-Path $bin 'node.exe')) { Info 'Node.js уже установлен.' }
    else {
      Info 'Скачиваю Node.js v26.13.1 (~35 МБ) — нужен для загрузки видео с YouTube…'
      Download $NodeUrl (Join-Path $tmp 'node.zip') $NodeSha
      Expand-Archive -LiteralPath (Join-Path $tmp 'node.zip') -DestinationPath (Join-Path $tmp 'node')
      Get-ChildItem -Path (Join-Path $tmp 'node') -Recurse -Filter node.exe | Select-Object -First 1 | Copy-Item -Destination $bin -Force
    }
    $uv = Join-Path $tools 'uv.exe'
    if (-not (Test-Path $uv)) {
      Info 'Скачиваю установщик Python (uv)…'
      Download $UvUrl (Join-Path $tmp 'uv.zip') $UvSha
      Expand-Archive -LiteralPath (Join-Path $tmp 'uv.zip') -DestinationPath (Join-Path $tmp 'uv')
      Get-ChildItem -Path (Join-Path $tmp 'uv') -Recurse -Filter uv.exe | Select-Object -First 1 | Copy-Item -Destination $tools -Force
    }
    & (Join-Path $bin 'ffmpeg.exe') -version *> $null
    if ($LASTEXITCODE -ne 0) { Fail 'FFmpeg не запускается. Возможно, его заблокировал антивирус.' }

    Say '3/5 · Устанавливаю библиотеки (первый раз — несколько минут)'
    $env:UV_CACHE_DIR = Join-Path $tools 'uv-cache'
    $env:UV_PYTHON_INSTALL_DIR = Join-Path $tools 'python'
    $env:UV_HTTP_TIMEOUT = '300'
    Push-Location $AppHome
    try {
      & $uv venv --quiet --python 3.11 --allow-existing .venv
      if ($LASTEXITCODE -ne 0) { Fail 'не удалось установить Python.' }
      & $uv pip install --quiet --python .venv\Scripts\python.exe --no-deps -r backend\requirements-portable.lock
      if ($LASTEXITCODE -ne 0) { Fail 'не удалось установить библиотеки. Проверьте интернет и запустите команду ещё раз.' }
      & $Python -c 'import fastapi, faster_whisper, cv2'
      if ($LASTEXITCODE -ne 0) { Fail 'библиотеки установились с ошибкой.' }

      Say '4/5 · Создаю ярлыки VDS Shorts Factory'
      & $Python scripts\windows_app.py install
      if ($LASTEXITCODE -ne 0) { Fail 'не удалось создать ярлыки.' }

      Say '5/5 · Запускаю'
      if ($env:VDS_NO_OPEN) { & $Python scripts\launcher.py start --no-open } else { & $Python scripts\launcher.py start }
      if ($LASTEXITCODE -ne 0) { Fail "сервер не запустился. Журнал: $AppHome\.run\server.log" }
    } finally { Pop-Location }

    Say 'Готово! VDS Shorts Factory открыт в браузере: http://127.0.0.1:8765'
    Info 'Дальше запускайте его ярлыком на рабочем столе или из меню «Пуск».'
    Info 'Обновить: выполните эту же команду ещё раз. Видео и проекты сохранятся.'
  } finally {
    Remove-Item -LiteralPath $tmp -Recurse -Force -ErrorAction SilentlyContinue
  }
}

Install-VdsShortsFactory

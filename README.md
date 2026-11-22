<p align="center">
  <picture>
    <source media="(prefers-color-scheme: dark)" srcset="frontend/public/brand/logo-dark.png">
    <img src="frontend/public/brand/logo-light.png" alt="VDS Shorts Factory" width="360">
  </picture>
</p>

<p align="center"><b>Локальная студия коротких видео.</b> Из длинного ролика — готовые Shorts, Reels и TikTok: поиск сильных моментов, кадрирование 9:16, субтитры, монтаж и AI-музыка. Всё работает на вашем компьютере.</p>

## Установка

**macOS и Linux** — откройте «Терминал», вставьте строку и нажмите Enter:

```sh
curl -fsSL https://raw.githubusercontent.com/uladzislaududarau/vds-shorts-factory/main/install.sh | bash
```

**Windows 10/11** — откройте PowerShell (Пуск → «PowerShell»), вставьте строку и нажмите Enter:

```powershell
irm https://raw.githubusercontent.com/uladzislaududarau/vds-shorts-factory/main/install.ps1 | iex
```

Установщик сам скачает всё нужное (Python, FFmpeg, Node.js), создаст ярлык и откроет студию в браузере: **http://127.0.0.1:8765**. Права администратора, Homebrew и Xcode не нужны. Первая установка занимает 5–15 минут.

**Дальше запускайте как обычную программу:** на Mac — «VDS Shorts Factory» в Launchpad или «Программах», на Windows — ярлык на рабочем столе или в «Пуске», на Linux — меню приложений. Статус сервера виден справа вверху, кнопка «Запустить» поднимет его, если он остановлен.

**Обновить** — выполните ту же команду ещё раз. Видео, проекты и ключи сохраняются.

<details>
<summary><b>Удалить</b></summary>

macOS / Linux (видео и проекты сохраняются; добавьте `--purge`, чтобы удалить всё):
```sh
curl -fsSL https://raw.githubusercontent.com/uladzislaududarau/vds-shorts-factory/main/install.sh | bash -s -- --uninstall
```
Windows (`purge` вместо `uninstall` удаляет всё):
```powershell
$env:VDS_ACTION='uninstall'; irm https://raw.githubusercontent.com/uladzislaududarau/vds-shorts-factory/main/install.ps1 | iex
```
</details>

## Системные требования

| | |
|---|---|
| macOS | Apple Silicon (M1 и новее) или Intel |
| Windows | 10 или 11, 64-бит (Intel/AMD) |
| Linux | x86_64 или ARM64, glibc 2.28+ (Ubuntu 20.04+, Debian 10+, Fedora 29+) |
| Диск | ~5 ГБ на программу и запас под видео |

На Mac с Apple Silicon речь распознаётся на видеоядре (MLX Whisper), на остальных системах — на процессоре (faster-whisper), это медленнее.

## Что умеет

- **Импорт** — ссылка YouTube или файлы MP4/MOV/MKV/WebM.
- **Поиск моментов** — локально или через OpenAI / Gemini (по вашему ключу и согласию).
- **Clip Studio** — кадрирование 9:16 со слежением за лицом, субтитры по словам, правка текста.
- **Монтаж** — склейка нескольких роликов, обрезка, звук, 5 шаблонов субтитров, AI-музыка ElevenLabs под длину монтажа.
- **Публикация** — загрузка в YouTube по расписанию.

Подробно: [руководство](docs/USER_GUIDE.md) · [монтаж](docs/MONTAGE.md) · [YouTube](docs/YOUTUBE.md) · [публикация](docs/YOUTUBE_PUBLISHING.md) · [OpenAI и ElevenLabs](docs/AI_CONNECTIONS.md) · [если что-то не работает](docs/TROUBLESHOOTING.md) · [для разработчиков](docs/TECHNICAL.md)

## Лицензия

[MIT](LICENSE). Сторонние компоненты — в [THIRD_PARTY_NOTICES.md](THIRD_PARTY_NOTICES.md). Используйте только видео, на которые у вас есть права.

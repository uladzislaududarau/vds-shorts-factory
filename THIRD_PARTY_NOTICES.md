# Third-party notices

The VDS Shorts Factory source code is MIT-licensed (see [LICENSE](LICENSE)). The logo and name «VDS Shorts Factory» belong to the author.

## Bundled in this repository (`frontend/dist`)

| Component | License |
|---|---|
| React, React DOM, scheduler | MIT |
| lucide-react (icons) | ISC |
| @radix-ui/react-slot | MIT |
| class-variance-authority | Apache-2.0 |
| clsx, tailwind-merge, Tailwind CSS | MIT |
| qrcode-generator (Kazuhiko Arase) | MIT. «QR Code» is a registered trademark of DENSO WAVE INCORPORATED |
| Inter font via @fontsource/inter (The Inter Project Authors) | SIL Open Font License 1.1 |

The full license texts are included in each package's distribution on npm.

## Downloaded by the installer, not stored in this repository

Each is fetched from its publisher at a pinned version and checked against the publisher's SHA-256, under its own license:

- **FFmpeg** — LGPL/GPL static builds from [ffmpeg.martin-riedl.de](https://ffmpeg.martin-riedl.de/) (macOS, Linux) and [gyan.dev](https://www.gyan.dev/ffmpeg/builds/) (Windows; GPLv3).
- **Node.js** — MIT, from [nodejs.org](https://nodejs.org/).
- **uv** and the Python runtime — Apache-2.0/MIT and PSF, from Astral.
- **Python packages** listed in `backend/requirements-*.lock` (FastAPI, OpenCV, MLX Whisper / faster-whisper, yt-dlp and others), from PyPI.

Whisper speech-recognition model weights are downloaded from Hugging Face on first use under their own licenses.

<p align="center">
  <picture>
    <source media="(prefers-color-scheme: dark)" srcset="frontend/public/brand/logo-dark.png">
    <img src="frontend/public/brand/logo-light.png" alt="VDS Shorts Factory" width="360">
  </picture>
</p>

<p align="center"><b>Your local short-video studio.</b> Turn long videos into Shorts, Reels and TikToks with highlight selection, 9:16 framing, captions, editing and AI music. Run the studio on your own computer.</p>

## Installation

**macOS and Linux:** open Terminal, paste this command and press Enter:

```sh
curl -fsSL https://raw.githubusercontent.com/uladzislaududarau/vds-shorts-factory/main/install.sh | bash
```

**Windows 10/11:** open PowerShell from the Start menu, paste this command and press Enter:

```powershell
irm https://raw.githubusercontent.com/uladzislaududarau/vds-shorts-factory/main/install.ps1 | iex
```

The installer downloads Python, FFmpeg and Node.js, creates a shortcut and opens the studio in your browser at **http://127.0.0.1:8765**. Administrator privileges, Homebrew and Xcode are not required. Allow roughly 5–15 minutes for the first installation; slow connections can take longer.

**After installation, launch it like any other app:** use VDS Shorts Factory in Applications or Launchpad on Mac, the desktop or Start menu shortcut on Windows, or the application menu on Linux. The server status appears in the top-right corner. Use **Start** if the server is stopped.

**To update,** run the same installation command again. Your videos, projects and keys are preserved.

<details>
<summary><b>Uninstall</b></summary>

macOS / Linux (keeps videos and projects; add `--purge` to remove all application data):

```sh
curl -fsSL https://raw.githubusercontent.com/uladzislaududarau/vds-shorts-factory/main/install.sh | bash -s -- --uninstall
```

Windows (use `purge` instead of `uninstall` to remove all application data):

```powershell
$env:VDS_ACTION='uninstall'; irm https://raw.githubusercontent.com/uladzislaududarau/vds-shorts-factory/main/install.ps1 | iex
```

</details>

## System requirements

| Component | Requirement |
|---|---|
| macOS | Apple Silicon (M1 or later) or Intel |
| Windows | Windows 10 or 11, 64-bit Intel/AMD |
| Linux | x86_64 or ARM64, glibc 2.28+ (Ubuntu 20.04+, Debian 10+, Fedora 29+) |
| Storage | Approximately 5 GB for the application, plus space for videos |

On Apple Silicon, MLX Whisper transcribes speech using the GPU. Other systems use faster-whisper on the CPU, which is slower. These requirements describe the command-line installer; native DMG builds have their own compatibility requirements.

## Features

- **Import:** YouTube URLs or MP4, MOV, MKV and WebM files.
- **Highlight selection:** local processing or OpenAI / Gemini with your own key and explicit consent.
- **Clip Studio:** 9:16 framing with face tracking, word-level captions and text corrections.
- **Montage:** combine and trim videos, mix audio, use five caption presets and generate ElevenLabs music to match the edit.
- **Publishing:** upload to YouTube on a schedule.
- **Interface languages:** English, Russian, Spanish, Portuguese, French, German, Italian, Turkish, Chinese, Japanese, Korean and Hindi.

Read the [user guide](docs/USER_GUIDE.md), [montage guide](docs/MONTAGE.md), [YouTube download guide](docs/YOUTUBE.md), [publishing guide](docs/YOUTUBE_PUBLISHING.md), [OpenAI and ElevenLabs setup](docs/AI_CONNECTIONS.md), [troubleshooting guide](docs/TROUBLESHOOTING.md) or [developer documentation](docs/TECHNICAL.md).

## Support the project

VDS Shorts Factory is free and open source. Donations help fund maintenance and new features. The application also includes a **Karma** dialog with wallet addresses and QR codes.

| Asset | Network | Address |
|---|---|---|
| BTC | Bitcoin | `bc1q8vn6mv7vk2lnlfa3my896cynksxkpl6jnzzezg` |
| ETH · USDT · USDC · BNB | Ethereum (ERC-20) · BSC (BEP-20) | `0x7cDC8cBbD9AFFaB70B54587A4282e17272CE8c62` |
| SOL | Solana | `8Vz1gj6cnaSw1eM3SFtfmyx8JfgVbbVU2mbWYUh5BtZJ` |
| TRX · USDT | Tron (TRC-20) | `TP1dznp6UirK4yeAhpigSV56U3kndS95CN` |

Send assets only over the listed network.

## License

[MIT](LICENSE). See [THIRD_PARTY_NOTICES.md](THIRD_PARTY_NOTICES.md) for third-party components. Only process videos you have the right to use.

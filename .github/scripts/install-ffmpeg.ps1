# Match the checksum-verified Windows build used by install.ps1.
$ErrorActionPreference = 'Stop'
$url = 'https://www.gyan.dev/ffmpeg/builds/packages/ffmpeg-9.0.2-essentials_build.zip'
$sha = '60f467265b1e312373dbcd92200c2618a74850f98d3d078e94296bb3fa2047ba'
$archive = Join-Path $env:RUNNER_TEMP 'ffmpeg.zip'
$destination = Join-Path $env:RUNNER_TEMP 'ffmpeg'

for ($attempt = 1; $attempt -le 5; $attempt++) {
    try {
        Invoke-WebRequest -Uri $url -OutFile $archive
        if ((Get-FileHash -Algorithm SHA256 -LiteralPath $archive).Hash.ToLowerInvariant() -ne $sha) {
            throw 'FFmpeg archive checksum mismatch.'
        }
        break
    } catch {
        Remove-Item -LiteralPath $archive -Force -ErrorAction SilentlyContinue
        if ($attempt -eq 5) { throw }
        Write-Warning "FFmpeg download attempt $attempt failed: $_"
        Start-Sleep -Seconds (3 * $attempt)
    }
}
Expand-Archive -LiteralPath $archive -DestinationPath $destination -Force
$ffmpeg = @(Get-ChildItem -LiteralPath $destination -Recurse -Filter ffmpeg.exe)
if ($ffmpeg.Count -ne 1) { throw 'Expected exactly one FFmpeg executable.' }
$bin = $ffmpeg[0].DirectoryName
foreach ($tool in @('ffmpeg.exe', 'ffprobe.exe')) {
    $executable = Join-Path $bin $tool
    if (!(Test-Path -LiteralPath $executable)) { throw "Missing $tool" }
    & $executable -version
    if ($LASTEXITCODE -ne 0) { throw "$tool failed to start: $LASTEXITCODE" }
}
$bin | Out-File -FilePath $env:GITHUB_PATH -Encoding utf8 -Append

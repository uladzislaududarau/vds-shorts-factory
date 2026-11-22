#!/usr/bin/env python3
"""Build «VDS Shorts Factory.app»: a Dock/Launchpad launcher for this checkout.

Click → start the launchd server (scripts/launcher.py start) and open the studio.
shortsfactory://start (the «Запустить» button in the web UI) → start without opening a new tab.
Uses only tools shipped with macOS: osacompile, iconutil, codesign, lsregister.
"""
import os
import plistlib
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
APP_NAME = 'VDS Shorts Factory'
SCHEME = 'shortsfactory'
LSREGISTER = '/System/Library/Frameworks/CoreServices.framework/Frameworks/LaunchServices.framework/Support/lsregister'

def applescript(root: Path):
    literal = str(root).replace('\\', '\\\\').replace('"', '\\"')
    return f'''property installRoot : "{literal}"

on run
	startFactory(true)
end run

on open location theURL
	startFactory(false)
end open location

on startFactory(openBrowser)
	set cmd to quoted form of (installRoot & "/.venv/bin/python") & " " & quoted form of (installRoot & "/scripts/launcher.py") & " start"
	if openBrowser is false then set cmd to cmd & " --no-open"
	try
		do shell script cmd
	on error errorMessage
		display dialog "VDS Shorts Factory не запустился." & return & return & errorMessage & return & return & "Если папка программы была перемещена или удалена, установите её заново." buttons {{"OK"}} default button 1 with icon caution with title "{APP_NAME}"
	end try
end startFactory
'''

def draw_icon(path: Path):
    """App icon: the VDS mark (frontend/public/brand/mark-1024.png) on a white macOS rounded square."""
    from PIL import Image, ImageDraw
    size = 1024
    image = Image.new('RGBA', (size, size), (0, 0, 0, 0))
    inset = 100
    ImageDraw.Draw(image).rounded_rectangle((inset, inset, size - inset, size - inset), radius=185, fill=(255, 255, 255, 255))
    mark = Image.open(ROOT / 'frontend/public/brand/mark-1024.png').convert('RGBA')
    side = size - 2 * inset - 60
    mark = mark.resize((side, side), Image.Resampling.LANCZOS)
    image.alpha_composite(mark, ((size - side) // 2, (size - side) // 2))
    image.save(path)

def make_icns(png: Path, target: Path):
    from PIL import Image
    iconset = png.parent / 'icon.iconset'
    iconset.mkdir()
    source = Image.open(png)
    for base in (16, 32, 128, 256, 512):
        for scale in (1, 2):
            pixels = base * scale
            name = f'icon_{base}x{base}{"@2x" if scale == 2 else ""}.png'
            source.resize((pixels, pixels), Image.Resampling.LANCZOS).save(iconset / name)
    subprocess.run(['iconutil', '-c', 'icns', str(iconset), '-o', str(target)], check=True)

def destination():
    if '--dest' in sys.argv:
        return Path(sys.argv[sys.argv.index('--dest') + 1]).expanduser()
    system = Path('/Applications')
    return system if os.access(system, os.W_OK) else Path.home() / 'Applications'

def build():
    target_dir = destination()
    target_dir.mkdir(parents=True, exist_ok=True)
    target = target_dir / f'{APP_NAME}.app'
    with tempfile.TemporaryDirectory() as temp:
        temp = Path(temp)
        script = temp / 'launcher.applescript'
        script.write_text(applescript(ROOT), encoding='utf-8')
        app = temp / f'{APP_NAME}.app'
        subprocess.run(['osacompile', '-o', str(app), str(script)], check=True)
        resources = app / 'Contents/Resources'
        draw_icon(temp / 'icon.png')
        make_icns(temp / 'icon.png', resources / 'applet.icns')
        (resources / 'Assets.car').unlink(missing_ok=True)
        info_path = app / 'Contents/Info.plist'
        info = plistlib.loads(info_path.read_bytes())
        info.pop('CFBundleIconName', None)
        info.update({'CFBundleName': APP_NAME, 'CFBundleDisplayName': APP_NAME, 'CFBundleIdentifier': 'local.shorts-factory.launcher',
                     'CFBundleIconFile': 'applet', 'CFBundleShortVersionString': '1.0.0',
                     'CFBundleURLTypes': [{'CFBundleURLName': APP_NAME, 'CFBundleURLSchemes': [SCHEME]}]})
        info_path.write_bytes(plistlib.dumps(info))
        # Editing Info.plist invalidates osacompile's ad-hoc signature; Apple Silicon refuses unsigned code.
        subprocess.run(['codesign', '--force', '--deep', '--sign', '-', str(app)], check=True, capture_output=True)
        if target.exists():
            shutil.rmtree(target)
        shutil.move(str(app), str(target))
    subprocess.run([LSREGISTER, '-f', str(target)], check=False, capture_output=True)
    print(target)
    return target

if __name__ == '__main__':
    build()

#!/usr/bin/env python3
"""Windows: Start-menu and Desktop shortcuts plus the shortsfactory:// link for VDS Shorts Factory.

  python scripts/windows_app.py install   # icon, shortcuts, URL scheme (current user, no admin rights)
  python scripts/windows_app.py remove    # undo all of it
Shortcut → pythonw launcher.py start (starts the hidden supervisor and opens the studio).
shortsfactory://start (the «Запустить» button in the web UI) → the same without opening a new tab.
"""
import os
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
APP_NAME = 'VDS Shorts Factory'
SCHEME = 'shortsfactory'
ICON = ROOT / '.tools/vds-shorts-factory.ico'
PYTHONW = ROOT / '.venv/Scripts/pythonw.exe'
LAUNCHER = ROOT / 'scripts/launcher.py'

# Values travel through environment variables, never interpolated into PowerShell code.
SHORTCUTS_PS = r'''
$shell = New-Object -ComObject WScript.Shell
foreach ($folder in @([Environment]::GetFolderPath('Programs'), [Environment]::GetFolderPath('Desktop'))) {
  $path = Join-Path $folder ($env:VDS_NAME + '.lnk')
  if ($env:VDS_REMOVE -eq '1') { if (Test-Path -LiteralPath $path) { Remove-Item -LiteralPath $path -Force }; continue }
  $link = $shell.CreateShortcut($path)
  $link.TargetPath = $env:VDS_TARGET
  $link.Arguments = $env:VDS_ARGS
  $link.WorkingDirectory = $env:VDS_DIR
  $link.IconLocation = $env:VDS_ICON
  $link.Description = $env:VDS_NAME
  $link.Save()
}
'''

def shortcuts(remove=False):
    env = {**os.environ, 'VDS_NAME': APP_NAME, 'VDS_TARGET': str(PYTHONW), 'VDS_ARGS': f'"{LAUNCHER}" start',
           'VDS_DIR': str(ROOT), 'VDS_ICON': str(ICON), 'VDS_REMOVE': '1' if remove else '0'}
    subprocess.run(['powershell', '-NoProfile', '-NonInteractive', '-ExecutionPolicy', 'Bypass', '-Command', SHORTCUTS_PS],
                   env=env, check=True, capture_output=True, creationflags=subprocess.CREATE_NO_WINDOW)

def make_icon():
    sys.path.insert(0, str(ROOT / 'scripts'))
    from build_app import draw_icon   # same artwork as the macOS app
    from PIL import Image
    png = ICON.with_suffix('.png')
    ICON.parent.mkdir(parents=True, exist_ok=True)
    draw_icon(png)
    Image.open(png).save(ICON, sizes=[(s, s) for s in (16, 24, 32, 48, 64, 128, 256)])
    png.unlink()

def register_scheme():
    import winreg
    base = rf'Software\Classes\{SCHEME}'
    with winreg.CreateKey(winreg.HKEY_CURRENT_USER, base) as key:
        winreg.SetValueEx(key, None, 0, winreg.REG_SZ, f'URL:{APP_NAME}')
        winreg.SetValueEx(key, 'URL Protocol', 0, winreg.REG_SZ, '')
    with winreg.CreateKey(winreg.HKEY_CURRENT_USER, base + r'\DefaultIcon') as key:
        winreg.SetValueEx(key, None, 0, winreg.REG_SZ, f'"{ICON}",0')
    with winreg.CreateKey(winreg.HKEY_CURRENT_USER, base + r'\shell\open\command') as key:
        winreg.SetValueEx(key, None, 0, winreg.REG_SZ, f'"{PYTHONW}" "{LAUNCHER}" start --no-open')

def unregister_scheme():
    import winreg
    for sub in (r'\shell\open\command', r'\shell\open', r'\shell', r'\DefaultIcon', ''):
        try: winreg.DeleteKey(winreg.HKEY_CURRENT_USER, rf'Software\Classes\{SCHEME}{sub}')
        except FileNotFoundError: pass

if __name__ == '__main__':
    if sys.platform != 'win32':
        raise SystemExit('windows_app.py is for Windows; on macOS use scripts/build_app.py')
    if sys.argv[1:] == ['install']:
        make_icon(); register_scheme(); shortcuts()
        print(f'{APP_NAME}: shortcuts in Start menu and on Desktop, {SCHEME}:// registered')
    elif sys.argv[1:] == ['remove']:
        shortcuts(remove=True); unregister_scheme()
        ICON.unlink(missing_ok=True)
    else:
        raise SystemExit('usage: windows_app.py install|remove')

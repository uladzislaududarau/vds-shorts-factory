#!/usr/bin/env python3
"""Linux: application-menu entry and the shortsfactory:// link for VDS Shorts Factory (current user only).

  python scripts/linux_app.py install   # icon, .desktop entry, URL scheme handler
  python scripts/linux_app.py remove
Menu entry → launcher.py start (starts the background supervisor and opens the studio).
shortsfactory://start (the «Запустить» button in the web UI) → the same without opening a new tab.
"""
import os
import shutil
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
APP_NAME = 'VDS Shorts Factory'
SCHEME = 'shortsfactory'
ICON = ROOT / '.tools/vds-shorts-factory.png'
APPS = Path(os.environ.get('XDG_DATA_HOME') or Path.home() / '.local/share') / 'applications'
MENU = APPS / 'vds-shorts-factory.desktop'
HANDLER = APPS / 'vds-shorts-factory-url.desktop'

def quoted(value):
    # Desktop Entry spec: quote arguments, escape " ` $ \ inside quotes.
    return '"' + ''.join('\\' + c if c in '"`$\\' else c for c in str(value)) + '"'

def entry(name, args, hidden=False, scheme=False):
    exec_line = ' '.join([quoted(ROOT / '.venv/bin/python'), quoted(ROOT / 'scripts/launcher.py'), *args])
    lines = ['[Desktop Entry]', 'Type=Application', f'Name={name}', 'Comment=Локальная студия коротких видео',
             f'Exec={exec_line}', f'Icon={ICON}', 'Terminal=false', 'Categories=AudioVideo;Video;']
    if hidden: lines.append('NoDisplay=true')
    if scheme: lines.append(f'MimeType=x-scheme-handler/{SCHEME};')
    return '\n'.join(lines) + '\n'

def install():
    sys.path.insert(0, str(ROOT / 'scripts'))
    from build_app import draw_icon   # same artwork as the macOS app
    ICON.parent.mkdir(parents=True, exist_ok=True)
    draw_icon(ICON)
    APPS.mkdir(parents=True, exist_ok=True)
    MENU.write_text(entry(APP_NAME, ['start']), encoding='utf-8')
    HANDLER.write_text(entry(APP_NAME + ' (запуск сервера)', ['start', '--no-open', '%u'], hidden=True, scheme=True), encoding='utf-8')
    for path in (MENU, HANDLER):
        path.chmod(0o755)
    if shutil.which('xdg-mime'):
        subprocess.run(['xdg-mime', 'default', HANDLER.name, f'x-scheme-handler/{SCHEME}'], check=False, capture_output=True)
    if shutil.which('update-desktop-database'):
        subprocess.run(['update-desktop-database', str(APPS)], check=False, capture_output=True)
    print(f'{APP_NAME}: application menu entry and {SCHEME}:// handler installed')

def remove():
    for path in (MENU, HANDLER, ICON):
        path.unlink(missing_ok=True)
    if shutil.which('update-desktop-database'):
        subprocess.run(['update-desktop-database', str(APPS)], check=False, capture_output=True)

if __name__ == '__main__':
    if not sys.platform.startswith('linux'):
        raise SystemExit('linux_app.py is for Linux; macOS uses scripts/build_app.py, Windows scripts/windows_app.py')
    {'install': install, 'remove': remove}.get(sys.argv[1] if len(sys.argv) > 1 else '', lambda: sys.exit('usage: linux_app.py install|remove'))()

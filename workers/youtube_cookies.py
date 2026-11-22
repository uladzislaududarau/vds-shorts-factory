"""Read only the studio-owned Chrome profile; export only YouTube domains."""
import sys
from pathlib import Path
from yt_dlp.cookies import extract_cookies_from_browser
from yt_dlp.utils import DownloadError

class QuietLogger:
    def debug(self,*args,**kwargs):pass
    def info(self,*args,**kwargs):pass
    def warning(self,*args,**kwargs):pass
    def error(self,*args,**kwargs):pass

def main():
    from backend.youtube_auth import profile_path
    profile,destination=map(Path,sys.argv[1:3])
    if profile.resolve()!=(profile_path()/'Default').resolve():
        raise DownloadError('Only the studio-owned profile is permitted')
    jar=extract_cookies_from_browser('chrome',profile=str(profile),logger=QuietLogger())
    lines=['# Netscape HTTP Cookie File']
    for c in jar:
        host=c.domain.lower().lstrip('.')
        if host!='youtube.com' and not host.endswith('.youtube.com'):continue
        lines.append('\t'.join([c.domain,'TRUE' if c.domain_initial_dot else 'FALSE',c.path,
                                'TRUE' if c.secure else 'FALSE',str(c.expires or 0),c.name,c.value]))
    destination.write_text('\n'.join(lines)+'\n')
    destination.chmod(0o600)

if __name__=='__main__':
    try:main()
    except Exception:
        # Never put cookies or Keychain command output in process logs.
        print('YouTube session extraction failed',file=sys.stderr)
        raise SystemExit(1)

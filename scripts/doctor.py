import importlib.metadata
import json
import platform
import shutil
import subprocess
import sys
from pathlib import Path

ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT))
from backend.media import capabilities

def main():
    result={'architecture':platform.machine(),'python':sys.version.split()[0],
            'free_gb':round(shutil.disk_usage(ROOT).free/1024**3,2)}
    try: result.update(capabilities())
    except Exception as e: result['ffmpeg_error']=str(e)
    for name in ('fastapi','uvicorn','mlx','mlx-whisper','scenedetect','opencv-python','google-genai','Pillow','yt-dlp','yt-dlp-ejs','pycryptodomex'):
        try: result[name]=importlib.metadata.version(name)
        except importlib.metadata.PackageNotFoundError: result[name]='MISSING'
    test=subprocess.run([sys.executable,'-c','import mlx.core as mx; print(mx.metal.is_available()); print(mx.array([1,2])+1)'],capture_output=True,text=True)
    result['metal_test']=test.stdout.strip() if test.returncode==0 else test.stderr[-700:]
    result['subtitles']='ASS/SRT export; burned-in Pillow RGBA fallback when libass unavailable'
    result['gemini']='No media uploaded by doctor; real API requires a key and explicit consent'
    print(json.dumps(result,ensure_ascii=False,indent=2))

if __name__=='__main__': main()

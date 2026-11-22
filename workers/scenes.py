import json
import sys
from pathlib import Path

def main():
    from scenedetect import detect, ContentDetector
    source, destination = sys.argv[1:]
    scenes = detect(source, ContentDetector(threshold=27, min_scene_len=15), show_progress=False,start_in_scene=True)
    output=Path(destination)
    temporary=output.with_suffix('.tmp')
    temporary.write_text(json.dumps([{'start': a.get_seconds(), 'end': b.get_seconds()} for a, b in scenes]))
    temporary.replace(output)

if __name__ == '__main__':
    main()

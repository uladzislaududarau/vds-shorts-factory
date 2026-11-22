"""ASS/SRT export and font-measured RGBA captions for FFmpeg without libass."""
import os
import re
from pathlib import Path
from .analysis import transcript_words

PRESETS = {
    'Clean Minimal': {'size': 54, 'bold': False, 'outline': 1, 'shadow': 1, 'animation': 'none'},
    'Bold Viral': {'size': 70, 'bold': True, 'outline': 4, 'shadow': 2, 'animation': 'highlight'},
    'Kinetic Captions': {'size': 76, 'bold': True, 'outline': 4, 'shadow': 2, 'animation': 'pop', 'words_per_line': 3},
    'Premium Editorial': {'size': 56, 'font': 'Georgia', 'bold': False, 'outline': 1, 'shadow': 2, 'animation': 'none'},
    'High Contrast': {'size': 68, 'bold': True, 'outline': 5, 'shadow': 2, 'active_color': '#FFFF00', 'animation': 'highlight'},
}

def remap_words(transcript, segments):
    source = transcript_words(transcript)
    result, offset = [], 0.0
    for seg in segments:
        start, end = (seg.start, seg.end) if hasattr(seg, 'start') else (seg['start'], seg['end'])
        for word in source:
            # Only complete words survive a trim; never invent timing.
            if word['start'] >= start - .025 and word['end'] <= end + .025:
                result.append({'word': word['word'], 'start': max(offset, word['start'] - start + offset),
                               'end': min(offset + end - start, word['end'] - start + offset)})
        offset += end - start
    return result

def groups(words, per_line):
    result, current = [], []
    for word in words:
        if current and (len(current) >= per_line or word['start'] - current[-1]['end'] > .65):
            result.append(current)
            current = []
        current.append(word)
        if re.search(r'[.!?]$', word['word']):
            result.append(current)
            current = []
    if current:
        result.append(current)
    return result

def timestamp(seconds, ass=False):
    ticks = max(0, round(seconds * (100 if ass else 1000)))
    rate = 100 if ass else 1000
    s, fraction = divmod(ticks, rate)
    h, rem = divmod(s, 3600)
    m, s = divmod(rem, 60)
    return f'{h}:{m:02}:{s:02}.{fraction:02}' if ass else f'{h:02}:{m:02}:{s:02},{fraction:03}'

def clean(text):
    return text.replace('\\', '').replace('{', '').replace('}', '').replace('\n', ' ').replace('\r', '')

def ass_color(hex_color):
    h = hex_color.lstrip('#')
    return '&H00' + h[4:6] + h[2:4] + h[0:2]

def export_text(words, style, width, height, destination):
    grouped = groups(words, style.words_per_line)
    srt = []
    ass = [f'''[Script Info]
ScriptType: v4.00+
PlayResX: {width}
PlayResY: {height}
WrapStyle: 0
[V4+ Styles]
Format: Name, Fontname, Fontsize, PrimaryColour, SecondaryColour, OutlineColour, BackColour, Bold, Italic, Underline, StrikeOut, ScaleX, ScaleY, Spacing, Angle, BorderStyle, Outline, Shadow, Alignment, MarginL, MarginR, MarginV, Encoding
Style: Default,{style.font},{round(style.size * width / 1080)},{ass_color(style.color)},{ass_color(style.active_color)},&H00000000,&H80000000,{-1 if style.bold else 0},0,0,0,100,100,0,0,{3 if style.preset == 'High Contrast' else 1},{style.outline},{style.shadow},5,{style.margin},{style.margin},40,1
[Events]
Format: Layer, Start, End, Style, Name, MarginL, MarginR, MarginV, Effect, Text''']
    for i, group in enumerate(grouped):
        srt.append(f'{i+1}\n{timestamp(group[0]["start"])} --> {timestamp(group[-1]["end"])}\n' + ' '.join(w['word'] for w in group) + '\n')
        # Separate events preserve the exact alignment of active words, including pauses.
        boundaries = sorted(set([group[0]['start'], group[-1]['end']] + [w[k] for w in group for k in ('start', 'end')]))
        for left, right in zip(boundaries, boundaries[1:]):
            if right <= left:
                continue
            mid = (left + right) / 2
            active = next((n for n, w in enumerate(group) if w['start'] <= mid < w['end']), -1)
            text = []
            for n, w in enumerate(group):
                color = style.active_color if n == active and style.animation != 'none' else style.color
                tag = '{\\c' + ass_color(color) + '&}'
                text.append(tag + clean(w['word']))
            pos = f'{{\\pos({width//2},{round(height*style.position)})}}'
            if style.animation == 'pop':
                pos += '{\\fscx95\\fscy95\\t(0,75,\\fscx100\\fscy100)}'
            ass.append(f'Dialogue: 0,{timestamp(left,True)},{timestamp(right,True)},Default,,0,0,0,,{pos}' + ' '.join(text))
    destination.with_suffix('.srt').write_text('\n'.join(srt), encoding='utf-8')
    destination.with_suffix('.ass').write_text('\n'.join(ass), encoding='utf-8')

def font_path(style):
    fonts = Path('/System/Library/Fonts/Supplemental')
    family = style.font
    windows = Path(os.environ.get('WINDIR', r'C:\Windows')) / 'Fonts'
    # Windows has no Helvetica: Arial is its metric twin.
    win_name = {'Georgia': 'georgia'}.get(family, 'arial') + ('bd' if family != 'Georgia' and style.bold else 'b' if style.bold else '')
    candidates = [fonts / f'{family} Bold.ttf' if style.bold else fonts / f'{family}.ttf',
                  Path('/System/Library/Fonts') / f'{family}.ttc', windows / f'{win_name}.ttf',
                  fonts / 'Arial.ttf', Path('/Library/Fonts/Arial.ttf'), windows / 'arial.ttf',
                  Path('/usr/share/fonts/truetype/liberation/LiberationSans-Bold.ttf' if style.bold else '/usr/share/fonts/truetype/liberation/LiberationSans-Regular.ttf'),
                  Path('/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf')]
    return str(next((p for p in candidates if p.exists()), 'Arial.ttf'))

def raster_captions(words, style, width, height, duration, folder, job_id=None):
    from PIL import Image, ImageDraw, ImageFont
    from .media import check_job
    folder.mkdir(parents=True, exist_ok=True)
    blank = folder / 'blank.png'
    Image.new('RGBA', (width, height), (0, 0, 0, 0)).save(blank)
    events = []
    scale = width / 1080
    max_width = width - 2 * style.margin * scale
    for g_index, group in enumerate(groups(words, style.words_per_line)):
        check_job(job_id)
        font_size = max(18, round(style.size * scale))
        font = ImageFont.truetype(font_path(style), font_size)
        text = ' '.join(w['word'] for w in group)
        while font.getlength(text) > max_width and font_size > 12:
            font_size -= 1
            font = ImageFont.truetype(font_path(style), font_size)
        if font.getlength(text) > max_width:
            raise ValueError('Subtitle line is wider than the safe area; reduce words per line')
        boundaries = sorted(set([w[k] for w in group for k in ('start', 'end')]))
        for left, right in zip(boundaries, boundaries[1:]):
            mid = (left + right) / 2
            active = next((n for n, w in enumerate(group) if w['start'] <= mid < w['end']), -1)
            if right <= left:
                continue
            path = folder / f'g{g_index}-{active}.png'
            if not path.exists():
                im = Image.new('RGBA', (width, height), (0, 0, 0, 0))
                draw = ImageDraw.Draw(im)
                x, y = (width - font.getlength(text)) / 2, height * style.position - font_size / 2
                safe_y = min(height*.04, style.margin*scale)
                y = max(safe_y,min(y,height-safe_y-font_size-32*scale))
                if style.preset == 'High Contrast':
                    draw.rounded_rectangle((x - 16, y - 12, width - x + 16, y + font_size + 28), radius=8, fill=(0,0,0,230))
                for n, w in enumerate(group):
                    color = style.active_color if n == active and style.animation != 'none' else style.color
                    stroke = max(0, round(style.outline * scale))
                    if style.shadow:
                        shadow = round(style.shadow * scale)
                        draw.text((x + shadow, y + shadow), w['word'], font=font, fill='#000000', stroke_width=stroke, stroke_fill='#000000')
                    draw.text((x, y), w['word'], font=font, fill=color, stroke_width=stroke, stroke_fill='#000000')
                    x += font.getlength(w['word'] + ' ')
                im.save(path)
            if style.animation == 'pop' and active >= 0 and abs(left - group[active]['start']) < .001:
                pop_path = path.with_name(path.stem + '-pop.png')
                if not pop_path.exists():
                    original = Image.open(path).convert('RGBA')
                    box = original.getbbox()
                    if box:
                        caption = original.crop(box)
                        caption = caption.resize((max(1,round(caption.width*.94)),max(1,round(caption.height*.94))),Image.Resampling.LANCZOS)
                        popped = Image.new('RGBA',(width,height),(0,0,0,0))
                        popped.paste(caption,(round((box[0]+box[2]-caption.width)/2),round((box[1]+box[3]-caption.height)/2)))
                        popped.save(pop_path)
                if pop_path.exists():
                    cut = min(right,left+.067)
                    events.append((max(0,left),min(duration,cut),pop_path))
                    left = cut
            if right > left:
                events.append((max(0, left), min(duration, right), path))
    frames, cursor = [], 0.0
    for start, end, path in events:
        if start > cursor + .0001:
            frames.append((blank, start - cursor))
        if end > max(cursor, start):
            frames.append((path, end - max(cursor, start)))
            cursor = end
    if cursor < duration:
        frames.append((blank, duration - cursor))
    if not frames:
        frames = [(blank, duration)]
    concat = folder / 'captions.ffconcat'
    # Filenames are generated and absolute. Escape quote for ffconcat, never shell.
    def quoted(path):
        return "'" + str(path).replace("'", "'\\''") + "'"
    lines = ['ffconcat version 1.0']
    for path, hold in frames:
        lines += ['file ' + quoted(path), f'duration {hold:.6f}']
    lines.append('file ' + quoted(frames[-1][0]))
    concat.write_text('\n'.join(lines) + '\n')
    return concat

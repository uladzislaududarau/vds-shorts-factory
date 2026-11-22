"""Social-media caption templates for the montage editor.

Frames are rendered with Pillow as transparent PNGs and played through an
ffconcat list, exactly like the clip renderer, so the MP4 never depends on libass.
All template fonts are macOS system fonts with Cyrillic coverage.
"""
import hashlib
import io
import os
import re
from pathlib import Path
from typing import Literal

from pydantic import Field

from .schemas import StrictModel

SUPPLEMENTAL = Path('/System/Library/Fonts/Supplemental')
SYSTEM = Path('/System/Library/Fonts')
WINDOWS = Path(os.environ.get('WINDIR', r'C:\Windows')) / 'Fonts'
# macOS font first, then the closest Windows system font (all with Cyrillic). Avenir/Helvetica Neue → Segoe UI.
FONTS = {
    'arial_black': [(SUPPLEMENTAL / 'Arial Black.ttf', 0), (WINDOWS / 'ariblk.ttf', 0)],
    'impact': [(SUPPLEMENTAL / 'Impact.ttf', 0), (WINDOWS / 'impact.ttf', 0)],
    'avenir_bold': [(SYSTEM / 'Avenir Next.ttc', 0), (WINDOWS / 'segoeuib.ttf', 0)],
    'helvetica_medium': [(SYSTEM / 'HelveticaNeue.ttc', 10), (WINDOWS / 'seguisb.ttf', 0), (WINDOWS / 'segoeui.ttf', 0)],
    'helvetica_black': [(SYSTEM / 'HelveticaNeue.ttc', 9), (WINDOWS / 'seguibl.ttf', 0), (WINDOWS / 'ariblk.ttf', 0)],
}
FALLBACK = [(SUPPLEMENTAL / 'Arial Bold.ttf', 0), (Path('/Library/Fonts/Arial.ttf'), 0), (WINDOWS / 'arialbd.ttf', 0),
            # Linux: Liberation Sans (Debian/Ubuntu, Fedora) is metric-compatible with Arial; DejaVu as the last resort.
            (Path('/usr/share/fonts/truetype/liberation/LiberationSans-Bold.ttf'), 0), (Path('/usr/share/fonts/liberation-sans/LiberationSans-Bold.ttf'), 0),
            (Path('/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf'), 0)]

# effect: color = active word recoloured, box = plate behind active word,
# single = one word at a time, none = static line, glow = neon light.
TEMPLATES = {
    'bold': {'label': 'Жирный акцент', 'hint': 'Крупно, ЗАГЛАВНЫМИ, активное слово жёлтым — самый популярный стиль Reels/Shorts',
             'font': 'arial_black', 'effect': 'color', 'pop': True, 'scale_active': 1.1,
             'defaults': {'color': '#FFFFFF', 'accent': '#FFE600', 'size': 74, 'uppercase': True, 'words': 3, 'outline': 8, 'position': .7}},
    'box': {'label': 'Плашка на слове', 'hint': 'Активное слово на цветной плашке, как в CapCut',
            'font': 'avenir_bold', 'effect': 'box', 'pop': False, 'scale_active': 1.0,
            'defaults': {'color': '#FFFFFF', 'accent': '#7C3AED', 'size': 68, 'uppercase': False, 'words': 3, 'outline': 0, 'position': .7}},
    'single': {'label': 'По одному слову', 'hint': 'Одно большое слово в центре, цвета чередуются — динамично',
               'font': 'impact', 'effect': 'single', 'pop': True, 'scale_active': 1.0,
               'defaults': {'color': '#FFFFFF', 'accent': '#FFE600', 'size': 118, 'uppercase': True, 'words': 1, 'outline': 10, 'position': .5}},
    'clean': {'label': 'Минимал', 'hint': 'Спокойный белый текст с мягкой тенью — для экспертного контента',
              'font': 'helvetica_medium', 'effect': 'none', 'pop': False, 'scale_active': 1.0,
              'defaults': {'color': '#FFFFFF', 'accent': '#FFFFFF', 'size': 56, 'uppercase': False, 'words': 5, 'outline': 0, 'position': .78}},
    'neon': {'label': 'Неон', 'hint': 'Светящееся активное слово — для музыки, ночи, игр',
             'font': 'helvetica_black', 'effect': 'glow', 'pop': False, 'scale_active': 1.0,
             'defaults': {'color': '#FFFFFF', 'accent': '#00F0FF', 'size': 82, 'uppercase': True, 'words': 3, 'outline': 0, 'position': .7}},
}
HEX = r'^#[0-9A-Fa-f]{6}$'

class CaptionStyle(StrictModel):
    enabled: bool = True
    template: Literal['bold', 'box', 'single', 'clean', 'neon'] = 'bold'
    color: str = Field(default='#FFFFFF', pattern=HEX)
    accent: str = Field(default='#FFE600', pattern=HEX)
    size: int = Field(default=74, ge=30, le=160)
    uppercase: bool = True
    words: int = Field(default=3, ge=1, le=6)
    outline: int = Field(default=8, ge=0, le=14)
    position: float = Field(default=.7, ge=.1, le=.9)

def template_list():
    return [{'id': key, 'label': value['label'], 'hint': value['hint'], 'defaults': value['defaults']} for key, value in TEMPLATES.items()]

_FONT_CACHE = {}
def font(name, size):
    key = (name, size)
    if key not in _FONT_CACHE:
        from PIL import ImageFont
        for path, index in FONTS.get(name, []) + FALLBACK:
            if path.exists():
                _FONT_CACHE[key] = ImageFont.truetype(str(path), size, index=index)
                break
        else:
            _FONT_CACHE[key] = ImageFont.load_default(size)
    return _FONT_CACHE[key]

def rgb(hex_color, alpha=255):
    value = hex_color.lstrip('#')
    return (int(value[0:2], 16), int(value[2:4], 16), int(value[4:6], 16), alpha)

def group_words(words, per_group):
    """Words carry an optional 'clip' index: a caption never spans a cut."""
    result, current = [], []
    for word in words:
        if current and (len(current) >= per_group or word['start'] - current[-1]['end'] > .6
                        or word.get('clip') != current[-1].get('clip')):
            result.append(current)
            current = []
        current.append(word)
        if re.search(r'[.!?…]$', word['word']):
            result.append(current)
            current = []
    if current:
        result.append(current)
    return result

def draw_frame(texts, active, style, width, height, word_index=0):
    """One full-size transparent frame of a caption group with `active` highlighted (-1 = none)."""
    from PIL import Image, ImageDraw, ImageFilter
    template = TEMPLATES[style.template]
    scale = width / 1080 if width < height else height / 1080
    effect = template['effect']
    texts = [t.upper() if style.uppercase else t for t in texts]
    base = max(16, round(style.size * scale))
    margin = round(70 * scale)
    max_width = width - 2 * margin
    # Shrink the whole line until it fits the safe area (long words, 16:9 or big sizes).
    while True:
        regular = font(template['font'], base)
        big = font(template['font'], max(base, round(base * template['scale_active'])))
        space = regular.getlength(' ')
        widths = [(big if n == active else regular).getlength(t) for n, t in enumerate(texts)]
        total = sum(widths) + space * (len(texts) - 1)
        if total <= max_width or base <= 16:
            break
        base = max(16, int(base * .92))
    stroke = round(style.outline * scale)
    layer = Image.new('RGBA', (width, height), (0, 0, 0, 0))
    draw = ImageDraw.Draw(layer)
    baseline = round(height * style.position + base * .35)
    baseline = max(base + margin // 2, min(baseline, height - margin))
    x = (width - total) / 2
    positions = []
    for n, text in enumerate(texts):
        positions.append((x, widths[n]))
        x += widths[n] + space

    def fill_for(n):
        if effect == 'single':
            return rgb(style.accent if word_index % 2 else style.color)
        if effect == 'color' and n == active:
            return rgb(style.accent)
        if effect == 'glow' and n == active:
            # Neon tube: bright core tinted by the accent, the halo carries the colour.
            accent, core = rgb(style.accent), rgb(style.color)
            return tuple(round(a * .35 + c * .65) for a, c in zip(accent[:3], core[:3])) + (255,)
        return rgb(style.color)

    if effect == 'box' and active >= 0:
        left, w = positions[active]
        pad_x, pad_y = round(base * .18), round(base * .14)
        top = baseline - base * .86 - pad_y
        draw.rounded_rectangle((left - pad_x, top, left + w + pad_x, baseline + base * .2 + pad_y),
                               radius=round(base * .22), fill=rgb(style.accent))
    if effect == 'glow':
        glow = Image.new('RGBA', (width, height), (0, 0, 0, 0))
        glow_draw = ImageDraw.Draw(glow)
        for n, text in enumerate(texts):
            colour = rgb(style.accent, 255) if n == active else rgb(style.accent, 60)
            glow_draw.text((positions[n][0], baseline), text, font=big if n == active else regular,
                           fill=colour, anchor='ls', stroke_width=round(base * .1), stroke_fill=colour)
        wide = glow.filter(ImageFilter.GaussianBlur(max(3, base * .3)))
        tight = glow.filter(ImageFilter.GaussianBlur(max(2, base * .1)))
        for halo in (wide, wide, tight):
            layer = Image.alpha_composite(layer, halo)
        draw = ImageDraw.Draw(layer)
    if effect in ('none', 'box') or style.template == 'clean':
        # Soft drop shadow keeps light text readable on bright footage.
        shadow = Image.new('RGBA', (width, height), (0, 0, 0, 0))
        shadow_draw = ImageDraw.Draw(shadow)
        offset = max(2, round(base * .05))
        for n, text in enumerate(texts):
            shadow_draw.text((positions[n][0] + offset, baseline + offset), text, font=big if n == active else regular,
                             fill=(0, 0, 0, 170), anchor='ls', stroke_width=max(stroke, 1), stroke_fill=(0, 0, 0, 170))
        shadow = shadow.filter(ImageFilter.GaussianBlur(max(2, base * .08)))
        layer = Image.alpha_composite(shadow, layer)
        draw = ImageDraw.Draw(layer)
    elif effect in ('color', 'single'):
        offset = max(2, round(base * .06))
        for n, text in enumerate(texts):
            draw.text((positions[n][0] + offset, baseline + offset), text, font=big if n == active else regular,
                      fill=(0, 0, 0, 200), anchor='ls', stroke_width=stroke, stroke_fill=(0, 0, 0, 200))
    for n, text in enumerate(texts):
        draw.text((positions[n][0], baseline), text, font=big if n == active else regular, fill=fill_for(n),
                  anchor='ls', stroke_width=stroke, stroke_fill=(0, 0, 0, 255))
    return layer

def pop_version(image, factor=.9):
    from PIL import Image
    box = image.getbbox()
    if not box:
        return image
    caption = image.crop(box)
    caption = caption.resize((max(1, round(caption.width * factor)), max(1, round(caption.height * factor))), Image.Resampling.LANCZOS)
    result = Image.new('RGBA', image.size, (0, 0, 0, 0))
    result.paste(caption, (round((box[0] + box[2] - caption.width) / 2), round((box[1] + box[3] - caption.height) / 2)))
    return result

def render_concat(words, style, width, height, duration, folder, job_id=None):
    """Write caption PNG frames + ffconcat list covering [0, duration]."""
    from PIL import Image
    from .media import check_job
    folder.mkdir(parents=True, exist_ok=True)
    blank = folder / 'blank.png'
    Image.new('RGBA', (width, height), (0, 0, 0, 0)).save(blank)
    template = TEMPLATES[style.template]
    per_group = 1 if template['effect'] == 'single' else style.words
    events = []
    for g, group in enumerate(group_words(words, per_group)):
        check_job(job_id)
        texts = [w['word'] for w in group]
        # Hold each caption until the next word or shortly after the last word.
        boundaries = sorted({w[k] for w in group for k in ('start', 'end')})
        for left, right in zip(boundaries, boundaries[1:]):
            if right <= left:
                continue
            mid = (left + right) / 2
            active = next((n for n, w in enumerate(group) if w['start'] <= mid < w['end']), -1)
            if template['effect'] == 'none':
                active = -1
            path = folder / f'g{g}-{active}.png'
            if not path.exists():
                draw_frame(texts, active, style, width, height, word_index=g).save(path)
            if template['pop'] and active >= 0 and abs(left - group[active]['start']) < .001:
                pop_path = folder / f'g{g}-{active}-pop.png'
                if not pop_path.exists():
                    pop_version(Image.open(path).convert('RGBA')).save(pop_path)
                cut = min(right, left + .07)
                events.append((left, cut, pop_path))
                left = cut
            if right > left:
                events.append((left, right, path))
    frames, cursor = [], 0.0
    for start, end, path in sorted(events, key=lambda e: e[0]):
        start, end = max(start, cursor), min(end, duration)
        if end <= start:
            continue
        if start > cursor + .0001:
            frames.append((blank, start - cursor))
        frames.append((path, end - start))
        cursor = end
    if cursor < duration:
        frames.append((blank, duration - cursor))
    concat = folder / 'captions.ffconcat'
    def quoted(path):
        return "'" + str(path).replace("'", "'\\''") + "'"
    lines = ['ffconcat version 1.0']
    for path, hold in frames:
        lines += ['file ' + quoted(path), f'duration {hold:.6f}']
    lines.append('file ' + quoted(frames[-1][0]))
    concat.write_text('\n'.join(lines) + '\n')
    return concat

def srt(words, style, destination):
    from .subtitles import timestamp
    per_group = 1 if TEMPLATES[style.template]['effect'] == 'single' else style.words
    blocks = [f'{i + 1}\n{timestamp(g[0]["start"])} --> {timestamp(g[-1]["end"])}\n' + ' '.join(w['word'] for w in g) + '\n'
              for i, g in enumerate(group_words(words, per_group))]
    destination.write_text('\n'.join(blocks), encoding='utf-8')

SAMPLE = ['Так', 'будут', 'выглядеть', 'ваши', 'субтитры']

def preview_png(style, width, height, crop=False):
    """Exact PIL output for the UI: same renderer as the MP4."""
    count = 1 if TEMPLATES[style.template]['effect'] == 'single' else min(style.words, len(SAMPLE))
    texts = SAMPLE[1:2] if count == 1 else SAMPLE[:count]
    image = draw_frame(texts, 0 if count == 1 else 1, style, width, height, word_index=1)
    if crop and image.getbbox():
        box = image.getbbox()
        pad = 24
        image = image.crop((max(0, box[0] - pad), max(0, box[1] - pad), min(width, box[2] + pad), min(height, box[3] + pad)))
    buffer = io.BytesIO()
    image.save(buffer, format='PNG', optimize=True)
    return buffer.getvalue()

def preview_key(style, width, height, crop):
    return hashlib.sha256(f'v1:{style.model_dump_json()}:{width}:{height}:{crop}'.encode()).hexdigest()

#!/usr/bin/env python3
"""Breaking Point Sim kanal kimliği: banner, profil, açıklama.  python brand.py [--apply]"""
import math, os, random, sys
from pathlib import Path
from PIL import Image, ImageDraw, ImageFilter, ImageFont

HERE = Path(__file__).resolve().parent
A = HERE / 'assets'; A.mkdir(exist_ok=True)

# palet: grafit laboratuvar + erimiş metal turuncusu + çelik
BG = (17, 19, 22)
GRID = (30, 34, 39)
STEEL = (150, 160, 170)
STEEL_D = (78, 86, 95)
WHITE = (236, 238, 240)
HOT = (255, 106, 26)
HOT_L = (255, 196, 92)

DESCRIPTION = """What happens when a hydraulic press meets a steel bolt? When a wrecking ball hits a brick wall? When 10,000 marbles drop on a glass floor?

Every video on this channel is a 3D physics simulation, built and rendered frame by frame in Blender with physically based materials and Blender's own physics engine. Nothing real is destroyed, and nothing is presented as real footage.

New simulations every day: crush tests, impacts, shattering, fluids and slow-motion breaks. Tell us in the comments what should reach its breaking point next.

All videos are computer simulations for entertainment; results are illustrative, not engineering data."""
KEYWORDS = ['physics simulation', 'hydraulic press', 'satisfying', 'blender simulation', 'destruction', 'slow motion',
            'crush test', 'what happens if', 'oddly satisfying', '3d simulation', 'rigid body', 'fluid simulation']


def font(name, size, weight=None):
    f = ImageFont.truetype(str(HERE / 'fonts' / name), size)
    if weight:
        try: f.set_variation_by_axes([weight])
        except Exception: pass
    return f


def TITLE(s): return font('BigShoulders.ttf', s, 900)
def MONO(s, w=500): return font('JetBrainsMono.ttf', s, w)


def lab_bg(W, H, seed=1):
    img = Image.new('RGB', (W, H), BG); d = ImageDraw.Draw(img)
    step = max(24, W // 64)
    for x in range(0, W, step): d.line([(x, 0), (x, H)], fill=GRID, width=1)
    for y in range(0, H, step): d.line([(0, y), (W, y)], fill=GRID, width=1)
    for x in range(0, W, step * 4): d.line([(x, 0), (x, H)], fill=(38, 43, 49), width=2)
    for y in range(0, H, step * 4): d.line([(0, y), (W, y)], fill=(38, 43, 49), width=2)
    # köşelerde vinyet
    v = Image.new('L', (W, H), 0); vd = ImageDraw.Draw(v)
    vd.ellipse([-W * 0.15, -H * 0.3, W * 1.15, H * 1.3], fill=255)
    v = v.filter(ImageFilter.GaussianBlur(W // 10))
    return Image.composite(img, Image.new('RGB', (W, H), (8, 9, 11)), v)


def glow(img, box, color, r):
    g = Image.new('RGBA', img.size, (0, 0, 0, 0)); ImageDraw.Draw(g).ellipse(box, fill=color + (200,))
    g = g.filter(ImageFilter.GaussianBlur(r)); img.paste(g, (0, 0), g)


def crack(d, x0, y0, length, ang, rng, width, color, depth=0):
    """dallanan kırık çizgisi"""
    x, y = x0, y0; seg = length / 7
    for i in range(7):
        ang += rng.uniform(-0.55, 0.55)
        nx, ny = x + seg * math.cos(ang), y + seg * math.sin(ang)
        d.line([(x, y), (nx, ny)], fill=color, width=max(1, int(width * (1 - i / 9))))
        if depth < 2 and rng.random() < 0.35:
            crack(d, nx, ny, length * 0.45, ang + rng.choice([-1, 1]) * rng.uniform(0.5, 1.1), rng, width * 0.6, color, depth + 1)
        x, y = nx, ny


def press_scene(img, cx, base_y, s, seed=3):
    """hidrolik pres plakası, ezilen çelik küp, temas noktasında kızgın parıltı"""
    d = ImageDraw.Draw(img); rng = random.Random(seed)
    cw, ch = int(260 * s), int(190 * s)                     # küp yarı ezilmiş: geniş ve basık
    top = base_y - ch
    # pres pistonu + plaka
    d.rectangle([cx - 46 * s, 0, cx + 46 * s, top - 70 * s], fill=STEEL_D)
    d.rectangle([cx - 30 * s, 0, cx - 18 * s, top - 70 * s], fill=(110, 119, 128))
    d.rectangle([cx - 230 * s, top - 70 * s, cx + 230 * s, top], fill=STEEL, outline=(190, 198, 206), width=max(1, int(3 * s)))
    d.rectangle([cx - 230 * s, top - 14 * s, cx + 230 * s, top], fill=(105, 113, 122))
    # örs
    d.rectangle([cx - 300 * s, base_y, cx + 300 * s, base_y + 60 * s], fill=STEEL_D)
    # küp: kenarları dışa bombeli (ezilme)
    pts = []
    for i in range(21):
        t = i / 20; y = top + t * ch; bulge = math.sin(t * math.pi) * 34 * s
        pts.append((cx - cw / 2 - bulge, y))
    for i in range(20, -1, -1):
        t = i / 20; y = top + t * ch; bulge = math.sin(t * math.pi) * 34 * s
        pts.append((cx + cw / 2 + bulge, y))
    d.polygon(pts, fill=(64, 70, 77), outline=(120, 128, 136))
    # parıltı + kırıklar sadece küpün içinde
    layer = img.copy(); glow(layer, [cx - cw * 0.55, top - 40 * s, cx + cw * 0.55, top + 60 * s], HOT, int(28 * s))
    ld = ImageDraw.Draw(layer)
    for k in range(5):
        crack(ld, cx + rng.uniform(-cw * 0.35, cw * 0.35), top + 4 * s, ch * 0.8, math.pi / 2 + rng.uniform(-0.45, 0.45), rng, 5 * s, HOT_L)
    m = Image.new('L', img.size, 0); ImageDraw.Draw(m).polygon(pts, fill=255)
    img.paste(layer, (0, 0), m)
    d = ImageDraw.Draw(img)
    # kıvılcımlar
    for _ in range(int(60 * s) + 20):
        a = rng.uniform(-math.pi, 0); r = rng.uniform(40, 260) * s
        x, y = cx + rng.choice([-1, 1]) * (cw / 2 + 20 * s) + math.cos(a) * r * 0.6, top + math.sin(a) * r * 0.5
        L = rng.uniform(6, 22) * s
        d.line([(x, y), (x + math.cos(a) * L, y + math.sin(a) * L)], fill=rng.choice([HOT, HOT_L, (255, 240, 200)]), width=max(1, int(3 * s)))


def readout(d, x, y, rows, size, anchor='la'):
    f = MONO(size)
    for i, (k, v) in enumerate(rows):
        d.text((x, y + i * size * 1.45), f'{k:<7}{v}', font=f, fill=STEEL if i else HOT, anchor=anchor)


def banner():
    W, H = 2560, 1440; img = lab_bg(W, H); d = ImageDraw.Draw(img)
    # YouTube güvenli alanı: ortadaki 1546x423 (her cihazda görünür)
    cy = H // 2
    press_scene(img, W // 2 - 520, cy + 170, 1.05)
    d = ImageDraw.Draw(img)
    d.text((W // 2 - 170, cy - 40), 'BREAKING', font=TITLE(210), fill=WHITE, anchor='ls')
    d.text((W // 2 - 170, cy + 150), 'POINT', font=TITLE(210), fill=WHITE, anchor='ls')
    tw = d.textlength('POINT', font=TITLE(210))
    x0 = W // 2 - 170 + tw + 30
    d.rounded_rectangle([x0, cy + 4, x0 + 190, cy + 150], radius=10, fill=HOT)
    d.text((x0 + 95, cy + 77), 'SIM', font=TITLE(120), fill=BG, anchor='mm')
    d.text((W // 2 - 170, cy + 205), 'PHYSICS SIMULATIONS  ·  RENDERED IN BLENDER  ·  DAILY', font=MONO(34, 600), fill=STEEL, anchor='ls')
    # güvenli alan dışı: ölçüm paneli (masaüstü/TV)
    readout(d, W // 2 + 770, cy - 380, [('LOAD', '1,240 kN'), ('STRAIN', '0.38'), ('TEMP', '612 °C'), ('FRAME', '0412 / 0900')], 30)
    for i in range(18):   # tehlike şeridi (alt kenar, ince)
        x = i * 160 - 40; d.polygon([(x, H - 26), (x + 80, H - 26), (x + 110, H), (x + 30, H)], fill=HOT)
    img.save(A / 'banner_2560x1440.png')


def profile():
    S = 800; img = lab_bg(S, S, 2); d = ImageDraw.Draw(img)
    d.ellipse([20, 20, S - 20, S - 20], outline=HOT, width=18)
    press_scene(img, S // 2, 530, 0.9, seed=7)
    # dairenin dışını temizle
    m = Image.new('L', (S, S), 0); ImageDraw.Draw(m).ellipse([29, 29, S - 29, S - 29], fill=255)
    out = Image.new('RGB', (S, S), BG); out.paste(img, (0, 0), m)
    d = ImageDraw.Draw(out); d.ellipse([20, 20, S - 20, S - 20], outline=HOT, width=18)
    d.text((S // 2, 680), 'BP', font=TITLE(120), fill=WHITE, anchor='mm')
    out.save(A / 'profile_800x800.png')


def yt():
    from google.oauth2.credentials import Credentials
    from googleapiclient.discovery import build
    c = Credentials(None, refresh_token=os.environ['YT_REFRESH_TOKEN'], token_uri='https://oauth2.googleapis.com/token',
                    client_id=os.environ['YT_CLIENT_ID'], client_secret=os.environ['YT_CLIENT_SECRET'])
    return build('youtube', 'v3', credentials=c, cache_discovery=False)


def apply():
    from googleapiclient.http import MediaFileUpload
    api = yt(); ch = api.channels().list(part='snippet,brandingSettings', mine=True).execute()['items'][0]
    print('kanal:', ch['snippet']['title'])
    url = api.channelBanners().insert(media_body=MediaFileUpload(str(A / 'banner_2560x1440.png'), mimetype='image/png')).execute()['url']
    b = ch.get('brandingSettings', {}); b.setdefault('channel', {})
    b['channel'].update(description=DESCRIPTION, keywords=' '.join(f'"{k}"' if ' ' in k else k for k in KEYWORDS), defaultLanguage='en', country='US')
    b.setdefault('image', {})['bannerExternalUrl'] = url; b.pop('hints', None)
    api.channels().update(part='brandingSettings', body={'id': ch['id'], 'brandingSettings': b}).execute()
    api.channels().update(part='status', body={'id': ch['id'], 'status': {'selfDeclaredMadeForKids': False}}).execute()
    print('✓ banner + açıklama + çocuklara özel değil')


if __name__ == '__main__':
    banner(); profile(); print('✓ görseller')
    if '--apply' in sys.argv: apply()

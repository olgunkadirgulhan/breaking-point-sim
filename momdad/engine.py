#!/usr/bin/env python3
"""Mom vs Dad Toons video engine (2026-11-21, replaces Breaking Point Sim on the same channel).

A video = 3 rounds. Each round: the kid says something -> MOM handles it -> DAD handles it.
Flat 2D vector style (own look: pastel rooms, Fredoka font, speech bubbles). Everything is drawn in code:
no third-party art, music or voices.

  python engine.py --preview 2,5.5 --sit sick,bored,money    # PNG frames
  python engine.py --render --sit sick,bored,money            # output/final.mp4
"""
import math, os, random, subprocess, sys, wave, json
from functools import lru_cache
from multiprocessing import Pool

import numpy as np
from PIL import Image, ImageDraw, ImageFont
import imageio_ffmpeg

HERE = os.path.dirname(os.path.abspath(__file__))
OUT = os.path.join(os.path.dirname(HERE), 'output')
FONT = os.path.join(HERE, 'Fredoka.ttf')
W, H, FPS, S = 1080, 1920, 30, 2
SR = 44100
KIDT, PART = 1.7, 3.7                 # kid line, each parent part
ROUND = KIDT + 2 * PART               # 9.1 s
OUTRO = 2.6
GY = 1500                             # ground line (Shorts UI covers the bottom ~350 px)
KX, PX = 290, 740                     # kid x, parent standing x
SC = 1.3                              # character scale
DARK = (38, 30, 52)
WHITE = (255, 255, 255)
MOMC, DADC = (236, 72, 136), (52, 132, 236)


def P(v): return int(round(v * S))
def clamp(x, a=0.0, b=1.0): return a if x < a else b if x > b else x
def seg(t, a, b): return clamp((t - a) / (b - a))
def sm(u): u = clamp(u); return u * u * (3 - 2 * u)
def lerp(a, b, u): return a + (b - a) * u
def lerpc(c1, c2, u): return tuple(int(round(lerp(a, b, u))) for a, b in zip(c1, c2))
def darker(c, k=0.25): return lerpc(c, (0, 0, 0), k)
def back(u):
    u = clamp(u); c = 1.7; v = u - 1
    return 1 + (c + 1) * v ** 3 + c * v ** 2


@lru_cache(None)
def font(sz, wt=b'Bold'):
    f = ImageFont.truetype(FONT, sz)
    try: f.set_variation_by_name(wt)
    except Exception: pass
    return f


# ---------------------------------------------------------------- families (look varies per video)
SKINS = [(255, 220, 190), (241, 194, 160), (214, 160, 120), (176, 120, 86), (128, 84, 60), (250, 208, 176)]
HAIRS = [(60, 40, 30), (30, 26, 30), (140, 80, 40), (220, 170, 90), (170, 60, 40), (90, 60, 45)]
MOM_TOPS = [(236, 72, 136), (250, 140, 80), (150, 100, 220), (60, 180, 160), (240, 90, 90)]
DAD_TOPS = [(52, 132, 236), (70, 160, 90), (240, 170, 50), (100, 110, 130), (200, 80, 70)]
KID_TOPS = [(255, 200, 40), (90, 200, 120), (255, 120, 60), (120, 160, 255), (230, 90, 170)]


def family(seed):
    r = random.Random(seed)
    sk = r.randrange(len(SKINS)); skin = SKINS[sk]
    return dict(
        mom=dict(kind='mom', skin=skin, hair=r.choice(HAIRS), style=r.choice(['long', 'bun', 'curly', 'bob']),
                 top=r.choice(MOM_TOPS), legs=(70, 80, 110), shoe=(60, 50, 70), glasses=r.random() < 0.25),
        dad=dict(kind='dad', skin=SKINS[(sk + r.choice([0, 0, 1])) % len(SKINS)], hair=r.choice(HAIRS),
                 style=r.choice(['short', 'quiff', 'bald', 'short']), beard=r.random() < 0.45,
                 top=r.choice(DAD_TOPS), legs=(60, 70, 100), shoe=(50, 40, 40), glasses=r.random() < 0.35),
        kid=dict(kind='kid', skin=skin, hair=r.choice(HAIRS), style=r.choice(['boy', 'cap', 'pigtails', 'pony']),
                 top=r.choice(KID_TOPS), legs=(80, 110, 170), shoe=(240, 240, 240), glasses=False,
                 cap=r.choice([(220, 60, 60), (60, 120, 220), (60, 170, 90)])),
    )


# ---------------------------------------------------------------- person
def limb(d, a, b, w, col):
    d.line([P(a[0]), P(a[1]), P(b[0]), P(b[1])], fill=DARK, width=P(w + 9))
    for p in (a, b): d.ellipse([P(p[0] - (w + 9) / 2), P(p[1] - (w + 9) / 2), P(p[0] + (w + 9) / 2), P(p[1] + (w + 9) / 2)], fill=DARK)
    d.line([P(a[0]), P(a[1]), P(b[0]), P(b[1])], fill=col, width=P(w))
    for p in (a, b): d.ellipse([P(p[0] - w / 2), P(p[1] - w / 2), P(p[0] + w / 2), P(p[1] + w / 2)], fill=col)


def circ(d, x, y, r, fill, ol=5):
    d.ellipse([P(x - r), P(y - r), P(x + r), P(y + r)], fill=fill, outline=DARK if ol else None, width=P(ol) if ol else 0)


def arm_pts(sx, sy, s, a1, a2, k):
    u = (s * math.sin(math.radians(a1)), math.cos(math.radians(a1)))
    e = (sx + u[0] * 100 * k, sy + u[1] * 100 * k)
    v = (s * math.sin(math.radians(a1 + a2)), math.cos(math.radians(a1 + a2)))
    h = (e[0] + v[0] * 92 * k, e[1] + v[1] * 92 * k)
    return e, h


def person(d, who, x, gy, o):
    """Draws a front-facing cartoon person with feet at (x, gy). Returns hand positions."""
    kid = who['kind'] == 'kid'; k = (0.68 if kid else 1.0) * SC
    bob = o.get('bob', 0.0); sw = o.get('swing', 0.0)
    hip = gy - 225 * k - bob
    sh = hip - 205 * k
    R = 80 * k * (1.22 if kid else 1.0)
    hc = (x + o.get('lean', 0) * 0.5, sh - R * 0.95 - 10 * k)
    skin, hair = who['skin'], who['hair']
    # hair behind head
    if who['style'] == 'long':
        d.rounded_rectangle([P(hc[0] - R * 1.08), P(hc[1] - R * 0.7), P(hc[0] + R * 1.08), P(sh + 70 * k)], radius=P(R * 0.6), fill=hair, outline=DARK, width=P(5))
    if who['style'] == 'pony':
        d.ellipse([P(hc[0] + R * 0.6), P(hc[1] - R * 0.4), P(hc[0] + R * 1.5), P(hc[1] + R * 0.9)], fill=hair, outline=DARK, width=P(5))
    # legs
    for s in (-1, 1):
        a = math.radians(sw * s)
        h0 = (x + s * 36 * k, hip)
        f = (h0[0] + math.sin(a) * 215 * k, h0[1] + math.cos(a) * 215 * k)
        limb(d, h0, f, 46 * k, who['legs'])
        d.ellipse([P(f[0] - 36 * k), P(f[1] - 12 * k), P(f[0] + 40 * k), P(f[1] + 20 * k)], fill=who['shoe'], outline=DARK, width=P(5))
    # torso (+ skirt for mom style)
    top = who['top']
    d.rounded_rectangle([P(x - 80 * k), P(sh - 12 * k), P(x + 80 * k), P(hip + 26 * k)], radius=P(44 * k), fill=top, outline=DARK, width=P(5))
    if who['kind'] == 'kid':
        d.rectangle([P(x - 78 * k), P(sh + 70 * k), P(x + 78 * k), P(sh + 92 * k)], fill=lerpc(top, WHITE, 0.45))
    if who['kind'] == 'dad':
        d.polygon([(P(x - 22), P(sh - 10)), (P(x + 22), P(sh - 10)), (P(x), P(sh + 40))], fill=lerpc(top, WHITE, 0.6), outline=DARK)
    # neck + head
    d.rectangle([P(hc[0] - 20 * k), P(hc[1] + R * 0.7), P(hc[0] + 20 * k), P(sh + 4)], fill=skin)
    for s in (-1, 1): circ(d, hc[0] + s * R * 0.98, hc[1] + R * 0.1, R * 0.2, skin)
    circ(d, hc[0], hc[1], R, skin)
    hair_front(d, who, hc, R)
    face(d, who, hc, R, o)
    # arms (in front of body)
    hands = []
    for s, (a1, a2) in ((-1, o.get('la', (8, 0))), (1, o.get('ra', (8, 0)))):
        sp = (x + s * 70 * k, sh + 22 * k)
        e, hpt = arm_pts(sp[0], sp[1], s, a1, a2, k)
        limb(d, sp, e, 36 * k, top); limb(d, e, hpt, 30 * k, skin if who['kind'] != 'kid' else skin)
        circ(d, hpt[0], hpt[1], 22 * k, skin)
        hands.append(hpt)
    return dict(hands=hands, head=hc, R=R, top=hc[1] - R)


def hair_front(d, who, hc, R):
    x, y = hc; hair = who['hair']; st = who['style']
    def cap(drop=0.32):
        d.chord([P(x - R * 1.05), P(y - R * 1.1), P(x + R * 1.05), P(y + R * drop)], 180, 360, fill=hair, outline=DARK, width=P(5))
    if st in ('long', 'bob', 'pony'):
        cap(0.25)
        if st == 'bob':
            for s in (-1, 1): d.rounded_rectangle([P(x + s * R * 0.78 - R * 0.32), P(y - R * 0.5), P(x + s * R * 0.78 + R * 0.32), P(y + R * 0.55)], radius=P(R * 0.3), fill=hair, outline=DARK, width=P(5))
    elif st == 'bun':
        cap(0.2); circ(d, x, y - R * 1.15, R * 0.42, hair)
    elif st == 'curly':
        for i in range(9):
            a = math.pi + i * math.pi / 8
            circ(d, x + math.cos(a) * R * 0.95, y + math.sin(a) * R * 0.85 - R * 0.05, R * 0.33, hair, 4)
        for s in (-1, 1): circ(d, x + s * R * 1.0, y + R * 0.25, R * 0.3, hair, 4)
    elif st in ('short', 'boy'):
        cap(0.0)
    elif st == 'quiff':
        cap(0.0); d.chord([P(x - R * 0.5), P(y - R * 1.45), P(x + R * 0.9), P(y - R * 0.45)], 160, 360, fill=hair, outline=DARK, width=P(5))
    elif st == 'bald':
        for s in (-1, 1): d.chord([P(x + s * R * 0.75 - R * 0.3), P(y - R * 0.55), P(x + s * R * 0.75 + R * 0.3), P(y + R * 0.15)], 90 if s > 0 else 270, 270 if s > 0 else 450, fill=hair)
    elif st == 'cap':
        cap(0.0)
        c = who.get('cap', (220, 60, 60))
        d.chord([P(x - R * 1.04), P(y - R * 1.12), P(x + R * 1.04), P(y + R * 0.0)], 180, 360, fill=c, outline=DARK, width=P(5))
        d.rounded_rectangle([P(x - R * 0.2), P(y - R * 0.62), P(x + R * 1.35), P(y - R * 0.4)], radius=P(R * 0.1), fill=darker(c, 0.15), outline=DARK, width=P(4))
    elif st == 'pigtails':
        cap(0.2)
        for s in (-1, 1): circ(d, x + s * R * 1.12, y - R * 0.25, R * 0.38, hair)


def face(d, who, hc, R, o):
    x, y = hc; eyes = o.get('eyes', 'open'); mouth = o.get('mouth', 'smile')
    lx, ly = o.get('look', (0, 0))
    ex, ey, er = R * 0.36, y - R * 0.02, R * 0.2
    if who['kind'] == 'dad' and who.get('beard'):
        d.chord([P(x - R * 0.92), P(y - R * 0.5), P(x + R * 0.92), P(y + R * 1.08)], 0, 180, fill=who['hair'], outline=DARK, width=P(4))
    for s in (-1, 1):
        cx = x + s * ex
        if eyes in ('closed', 'sleep'):
            d.arc([P(cx - er), P(ey - er * 0.6), P(cx + er), P(ey + er * 0.8)], 0, 180, fill=DARK, width=P(5))
        elif eyes == 'happy':
            d.arc([P(cx - er), P(ey - er * 0.4), P(cx + er), P(ey + er * 1.2)], 180, 360, fill=DARK, width=P(6))
        else:
            big = 1.35 if eyes == 'wide' else 1.0
            d.ellipse([P(cx - er * big), P(ey - er * 1.2 * big), P(cx + er * big), P(ey + er * 1.2 * big)], fill=WHITE, outline=DARK, width=P(4))
            pr = er * (0.42 if eyes == 'wide' else 0.58)
            d.ellipse([P(cx + lx * er * 0.45 - pr), P(ey + ly * er * 0.5 - pr), P(cx + lx * er * 0.45 + pr), P(ey + ly * er * 0.5 + pr)], fill=DARK)
            if eyes == 'roll':
                d.rectangle([P(cx - er), P(ey + er * 0.2), P(cx + er), P(ey + er * 1.3)], fill=who['skin'])
        # brows
        by = ey - er * 1.7
        if eyes == 'angry': d.line([P(cx - s * er * 1.1), P(by - er * 0.4), P(cx + s * er * 0.9), P(by + er * 0.35)], fill=DARK, width=P(7))
        elif eyes == 'sad': d.line([P(cx - s * er * 1.0), P(by + er * 0.3), P(cx + s * er * 0.9), P(by - er * 0.35)], fill=DARK, width=P(6))
        elif eyes == 'wide': d.arc([P(cx - er), P(by - er * 0.9), P(cx + er), P(by + er * 0.4)], 200, 340, fill=DARK, width=P(6))
        else: d.line([P(cx - er * 0.9), P(by), P(cx + er * 0.9), P(by - er * 0.12)], fill=DARK, width=P(5))
    if who.get('glasses'):
        for s in (-1, 1): d.ellipse([P(x + s * ex - er * 1.45), P(ey - er * 1.35), P(x + s * ex + er * 1.45), P(ey + er * 1.35)], outline=DARK, width=P(5))
        d.line([P(x - ex + er * 1.45), P(ey), P(x + ex - er * 1.45), P(ey)], fill=DARK, width=P(5))
    for s in (-1, 1):
        d.ellipse([P(x + s * R * 0.58 - R * 0.13), P(y + R * 0.28 - R * 0.08), P(x + s * R * 0.58 + R * 0.13), P(y + R * 0.28 + R * 0.08)], fill=lerpc(who['skin'], (240, 110, 120), 0.45))
    my = y + R * 0.48; mw = R * 0.34
    if mouth == 'smile': d.arc([P(x - mw), P(my - mw * 0.7), P(x + mw), P(my + mw * 0.5)], 15, 165, fill=DARK, width=P(6))
    elif mouth == 'grin':
        d.chord([P(x - mw * 1.2), P(my - mw * 0.6), P(x + mw * 1.2), P(my + mw * 0.8)], 0, 180, fill=WHITE, outline=DARK, width=P(5))
    elif mouth in ('big', 'open'):
        oy = mw * (1.0 if mouth == 'big' else 0.6) * o.get('mo', 1.0)
        d.chord([P(x - mw * 1.1), P(my - oy * 0.8), P(x + mw * 1.1), P(my + oy + mw * 0.2)], 0, 180 if mouth == 'big' else 360, fill=(150, 40, 60), outline=DARK, width=P(5))
    elif mouth == 'o': d.ellipse([P(x - mw * 0.45), P(my - mw * 0.4), P(x + mw * 0.45), P(my + mw * 0.6)], fill=(150, 40, 60), outline=DARK, width=P(5))
    elif mouth == 'frown': d.arc([P(x - mw * 0.9), P(my), P(x + mw * 0.9), P(my + mw)], 200, 340, fill=DARK, width=P(6))
    else: d.line([P(x - mw * 0.7), P(my + mw * 0.1), P(x + mw * 0.7), P(my + mw * 0.1)], fill=DARK, width=P(6))


# ---------------------------------------------------------------- props
PROP_C = {'money': (90, 190, 100), 'cookie': (210, 150, 80), 'gift': (240, 80, 90), 'icecream': (250, 190, 210), 'book': (80, 120, 220),
          'cake': (250, 220, 230), 'blanket': (130, 170, 250), 'cup': (120, 200, 240), 'pizza': (250, 190, 70), 'chips': (250, 210, 60),
          'trophy': (250, 200, 50), 'umbrella': (240, 80, 90), 'coin': (250, 200, 50), 'bandaid': (240, 200, 160), 'remote': (60, 60, 70),
          'puppy': (220, 170, 110), 'toy': (240, 120, 60), 'sandwich': (240, 200, 120)}


def prop(d, name, x, y, s=1.0, ang=0.0, gt=0.0):
    s *= SC
    c = PROP_C.get(name, (240, 80, 90))
    ol = dict(outline=DARK, width=P(5))
    if name == 'phone':
        d.rounded_rectangle([P(x - 26 * s), P(y - 46 * s), P(x + 26 * s), P(y + 46 * s)], radius=P(9 * s), fill=(40, 40, 50), **ol)
        d.rounded_rectangle([P(x - 19 * s), P(y - 37 * s), P(x + 19 * s), P(y + 34 * s)], radius=P(5 * s), fill=(120, 200, 255))
    elif name == 'pan':
        d.line([P(x), P(y), P(x + 110 * s), P(y - 10 * s)], fill=DARK, width=P(18 * s))
        d.ellipse([P(x - 95 * s), P(y - 22 * s), P(x + 30 * s), P(y + 24 * s)], fill=(70, 70, 80), **ol)
    elif name in ('money',):
        for i in range(3):
            d.rounded_rectangle([P(x - 50 * s + i * 8), P(y - 26 * s - i * 8), P(x + 50 * s + i * 8), P(y + 26 * s - i * 8)], radius=P(4), fill=c, **ol)
        d.text((P(x - 8 * s + 16), P(y - 30 * s - 16)), '$', font=font(P(34 * s)), fill=(30, 90, 40))
    elif name in ('cookie', 'coin'):
        circ(d, x, y, 34 * s, c)
        if name == 'cookie':
            for dx, dy in ((-12, -8), (10, 6), (-2, 14), (14, -12)): circ(d, x + dx * s, y + dy * s, 5 * s, (90, 50, 30), 0)
    elif name == 'icecream':
        d.polygon([(P(x - 28 * s), P(y - 10 * s)), (P(x + 28 * s), P(y - 10 * s)), (P(x), P(y + 70 * s))], fill=(220, 160, 90), **ol)
        circ(d, x, y - 28 * s, 34 * s, c)
    elif name == 'cake':
        d.rounded_rectangle([P(x - 70 * s), P(y - 40 * s), P(x + 70 * s), P(y + 40 * s)], radius=P(10), fill=c, **ol)
        d.rectangle([P(x - 70 * s), P(y - 8 * s), P(x + 70 * s), P(y + 6 * s)], fill=(240, 100, 140))
        for i in (-1, 0, 1):
            d.rectangle([P(x + i * 35 * s - 5), P(y - 75 * s), P(x + i * 35 * s + 5), P(y - 40 * s)], fill=(120, 180, 250))
            fl = 1 + 0.2 * math.sin(gt * 20 + i)
            d.ellipse([P(x + i * 35 * s - 7), P(y - 92 * s * fl), P(x + i * 35 * s + 7), P(y - 74 * s)], fill=(255, 190, 40))
    elif name == 'cup':
        d.rounded_rectangle([P(x - 26 * s), P(y - 40 * s), P(x + 26 * s), P(y + 40 * s)], radius=P(8), fill=(230, 245, 255), **ol)
        d.rectangle([P(x - 20 * s), P(y - 12 * s), P(x + 20 * s), P(y + 34 * s)], fill=c)
    elif name == 'pizza':
        d.polygon([(P(x - 50 * s), P(y - 40 * s)), (P(x + 50 * s), P(y - 40 * s)), (P(x), P(y + 60 * s))], fill=c, **ol)
        for dx, dy in ((-15, -20), (14, -15), (0, 10)): circ(d, x + dx * s, y + dy * s, 8 * s, (210, 60, 50), 0)
    elif name == 'chips':
        d.rounded_rectangle([P(x - 40 * s), P(y - 55 * s), P(x + 40 * s), P(y + 55 * s)], radius=P(12), fill=c, **ol)
        d.text((P(x - 30 * s), P(y - 18 * s)), 'CHIPS', font=font(P(20 * s)), fill=(200, 50, 40))
    elif name == 'trophy':
        d.chord([P(x - 45 * s), P(y - 70 * s), P(x + 45 * s), P(y + 20 * s)], 0, 180, fill=c, **ol)
        d.rectangle([P(x - 10 * s), P(y - 25 * s), P(x + 10 * s), P(y + 30 * s)], fill=c, **ol)
        d.rectangle([P(x - 35 * s), P(y + 30 * s), P(x + 35 * s), P(y + 45 * s)], fill=(140, 90, 50), **ol)
    elif name == 'umbrella':
        d.line([P(x), P(y - 90 * s), P(x), P(y + 20 * s)], fill=DARK, width=P(7))
        d.chord([P(x - 90 * s), P(y - 150 * s), P(x + 90 * s), P(y - 30 * s)], 180, 360, fill=c, **ol)
    elif name == 'book':
        d.rounded_rectangle([P(x - 50 * s), P(y - 36 * s), P(x + 50 * s), P(y + 36 * s)], radius=P(5), fill=c, **ol)
        d.line([P(x), P(y - 36 * s), P(x), P(y + 36 * s)], fill=DARK, width=P(4))
    elif name == 'remote':
        d.rounded_rectangle([P(x - 16 * s), P(y - 50 * s), P(x + 16 * s), P(y + 50 * s)], radius=P(8), fill=c, **ol)
        circ(d, x, y - 30 * s, 7 * s, (230, 60, 60), 0)
    elif name == 'bandaid':
        d.rounded_rectangle([P(x - 50 * s), P(y - 16 * s), P(x + 50 * s), P(y + 16 * s)], radius=P(16), fill=c, **ol)
        d.rectangle([P(x - 16 * s), P(y - 14 * s), P(x + 16 * s), P(y + 14 * s)], fill=(250, 235, 215))
    elif name == 'blanket':
        d.rounded_rectangle([P(x - 70 * s), P(y - 45 * s), P(x + 70 * s), P(y + 45 * s)], radius=P(14), fill=c, **ol)
        for i in (-1, 0, 1): d.line([P(x + i * 40 * s), P(y - 45 * s), P(x + i * 40 * s), P(y + 45 * s)], fill=lerpc(c, WHITE, 0.4), width=P(8))
    elif name == 'puppy':
        circ(d, x, y, 46 * s, c)
        for sx in (-1, 1): d.ellipse([P(x + sx * 40 * s - 16 * s), P(y - 30 * s), P(x + sx * 40 * s + 16 * s), P(y + 20 * s)], fill=darker(c, 0.3), outline=DARK, width=P(4))
        for sx in (-1, 1): circ(d, x + sx * 16 * s, y - 6 * s, 6 * s, DARK, 0)
        circ(d, x, y + 12 * s, 9 * s, DARK, 0)
    elif name == 'sandwich':
        d.rounded_rectangle([P(x - 60 * s), P(y - 30 * s), P(x + 60 * s), P(y - 8 * s)], radius=P(10), fill=c, **ol)
        d.rectangle([P(x - 64 * s), P(y - 8 * s), P(x + 64 * s), P(y + 4 * s)], fill=(110, 200, 90))
        d.rectangle([P(x - 60 * s), P(y + 4 * s), P(x + 60 * s), P(y + 14 * s)], fill=(230, 80, 70))
        d.rounded_rectangle([P(x - 60 * s), P(y + 14 * s), P(x + 60 * s), P(y + 34 * s)], radius=P(10), fill=c, **ol)
    else:   # gift / toy
        d.rounded_rectangle([P(x - 50 * s), P(y - 44 * s), P(x + 50 * s), P(y + 44 * s)], radius=P(6), fill=c, **ol)
        d.rectangle([P(x - 9 * s), P(y - 44 * s), P(x + 9 * s), P(y + 44 * s)], fill=(255, 220, 80))
        d.rectangle([P(x - 50 * s), P(y - 9 * s), P(x + 50 * s), P(y + 9 * s)], fill=(255, 220, 80))


# ---------------------------------------------------------------- rooms
ROOMS = ('living', 'kitchen', 'bedroom', 'yard', 'car')


@lru_cache(8)
def room_img(room, seed):
    r = random.Random(seed)
    walls = {'living': [(255, 236, 214), (226, 240, 250), (240, 230, 250)], 'kitchen': [(225, 248, 236), (255, 244, 220)],
             'bedroom': [(236, 228, 255), (220, 240, 255)], 'yard': [(170, 220, 255)], 'car': [(190, 225, 255)]}[room]
    wall = r.choice(walls)
    img = Image.new('RGB', (P(W), P(H)), wall); d = ImageDraw.Draw(img)
    for i in range(40):  # soft vertical gradient
        y0 = i * H / 40
        d.rectangle([0, P(y0), P(W), P(y0 + H / 40 + 1)], fill=lerpc(wall, WHITE, 0.25 * (1 - i / 40)))
    if room == 'yard':
        circ(d, 900, 330, 90, (255, 220, 90), 0)
        for cx in (200, 640):
            for dx in (-60, 0, 60): circ(d, cx + dx, 560 + abs(dx) * 0.3, 60, WHITE, 0)
        for i in range(-1, 12):
            d.rounded_rectangle([P(i * 100 + 10), P(GY - 330), P(i * 100 + 80), P(GY - 40)], radius=P(14), fill=(250, 245, 235), outline=(200, 190, 170), width=P(3))
        d.rectangle([0, P(GY - 260), P(W), P(GY - 230)], fill=(235, 225, 205))
        d.rectangle([0, P(GY - 40), P(W), P(H)], fill=(120, 200, 100))
        d.rectangle([P(80), P(GY - 520), P(140), P(GY - 40)], fill=(150, 100, 60))
        for dx, dy in ((-70, 0), (60, -20), (0, -90)): circ(d, 110 + dx, GY - 560 + dy, 100, (90, 180, 90), 0)
        return img
    if room == 'car':
        d.rectangle([0, P(GY - 120), P(W), P(H)], fill=(110, 110, 120))
        for i in range(6): d.rectangle([P(i * 220 + 40), P(GY + 120), P(i * 220 + 160), P(GY + 140)], fill=(250, 230, 120))
        d.rounded_rectangle([P(40), P(GY - 700), P(1040), P(GY - 40)], radius=P(140), fill=(240, 90, 80), outline=DARK, width=P(8))
        d.rounded_rectangle([P(100), P(GY - 640), P(990), P(GY - 300)], radius=P(90), fill=(200, 235, 255), outline=DARK, width=P(6))
        return img
    floor = {'living': (200, 150, 110), 'kitchen': (230, 220, 200), 'bedroom': (190, 160, 200)}[room]
    d.rectangle([0, P(GY - 40), P(W), P(H)], fill=floor)
    for i in range(14): d.line([P(i * 90), P(GY - 40), P(i * 90 - 120), P(H)], fill=darker(floor, 0.08), width=P(3))
    d.rectangle([0, P(GY - 52), P(W), P(GY - 36)], fill=WHITE)
    # window
    wx = r.choice([150, 820]) if room != 'kitchen' else 540
    d.rounded_rectangle([P(wx - 130), P(560), P(wx + 130), P(860)], radius=P(16), fill=(170, 220, 255), outline=WHITE, width=P(16))
    d.line([P(wx), P(560), P(wx), P(860)], fill=WHITE, width=P(10)); d.line([P(wx - 130), P(710), P(wx + 130), P(710)], fill=WHITE, width=P(10))
    if room == 'living':
        c = r.choice([(110, 150, 220), (230, 120, 90), (120, 180, 140)])
        d.rounded_rectangle([P(600), P(GY - 300), P(1060), P(GY - 60)], radius=P(40), fill=c, outline=DARK, width=P(6))
        d.rounded_rectangle([P(570), P(GY - 210), P(1090), P(GY - 60)], radius=P(36), fill=lerpc(c, WHITE, 0.15), outline=DARK, width=P(6))
        d.ellipse([P(180), P(GY - 70), P(760), P(GY + 10)], fill=r.choice([(240, 200, 120), (230, 160, 170)]))
        d.rectangle([P(70), P(GY - 420), P(84), P(GY - 50)], fill=DARK)
        d.polygon([(P(30), P(GY - 420)), (P(124), P(GY - 420)), (P(100), P(GY - 520)), (P(54), P(GY - 520))], fill=(255, 220, 120), outline=DARK)
    elif room == 'kitchen':
        cab = r.choice([(120, 170, 200), (240, 200, 130), (150, 200, 160)])
        d.rectangle([P(0), P(GY - 300), P(W), P(GY - 50)], fill=cab, outline=DARK, width=P(6))
        d.rectangle([P(0), P(GY - 320), P(W), P(GY - 290)], fill=(240, 240, 245), outline=DARK, width=P(5))
        for i in range(5):
            d.rectangle([P(i * 216 + 18), P(GY - 270), P(i * 216 + 198), P(GY - 70)], outline=darker(cab, 0.2), width=P(5))
            circ(d, i * 216 + 108, GY - 170, 9, (240, 240, 240), 3)
        for i in range(4): d.rectangle([P(i * 270 + 30), P(330), P(i * 270 + 240), P(500)], fill=cab, outline=DARK, width=P(5))
    elif room == 'bedroom':
        bc = r.choice([(250, 150, 180), (150, 190, 250), (250, 210, 120)])
        d.rounded_rectangle([P(640), P(GY - 330), P(700), P(GY - 50)], radius=P(10), fill=(150, 100, 70), outline=DARK, width=P(5))
        d.rounded_rectangle([P(640), P(GY - 200), P(1100), P(GY - 80)], radius=P(20), fill=bc, outline=DARK, width=P(6))
        d.rounded_rectangle([P(700), P(GY - 250), P(840), P(GY - 190)], radius=P(24), fill=WHITE, outline=DARK, width=P(5))
        for i in range(6): circ(d, 120 + i * 30 * (1 + i % 2), 420 + (i * 53) % 140, 8, (255, 230, 120), 0)
    return img


# ---------------------------------------------------------------- overlays
def wrap(txt, f, maxw):
    words, lines, cur = txt.split(), [], ''
    for w_ in words:
        t = (cur + ' ' + w_).strip()
        if f.getlength(t) <= maxw or not cur: cur = t
        else: lines.append(cur); cur = w_
    if cur: lines.append(cur)
    return lines


def bubble(d, txt, cx, by, tx, ty, t0, tt, col=WHITE, ink=DARK, size=58, maxw=820):
    """speech bubble with bottom edge at y=by, tail pointing at (tx, ty). Pops in at t0."""
    if tt < t0: return
    sc = back(seg(tt, t0, t0 + 0.25))
    if sc <= 0.02: return
    f = font(P(size * sc)); lines = wrap(txt, font(P(size)), P(maxw))
    lh = P(size * 1.18 * sc); bw = max(f.getlength(l) for l in lines) + P(70 * sc); bh = lh * len(lines) + P(50 * sc)
    x0 = P(cx) - bw / 2; x0 = max(P(30), min(P(W - 30) - bw, x0)); y1 = P(by); y0 = y1 - bh
    tail = [(P(tx) - P(26), y1 - P(4)), (P(tx) + P(26), y1 - P(4)), (P(lerp(tx, tx, 1)), P(lerp(by, ty, 0.6 * sc)))]
    d.polygon(tail, fill=col, outline=DARK, width=P(6))
    d.rounded_rectangle([x0, y0, x0 + bw, y1], radius=P(38 * sc), fill=col, outline=DARK, width=P(6))
    d.polygon([(a, b - P(8)) for a, b in tail[:2]] + [(tail[2][0], tail[2][1] - P(12))], fill=col)
    for i, l in enumerate(lines):
        lw = f.getlength(l)
        d.text((x0 + (bw - lw) / 2, y0 + P(22 * sc) + i * lh), l, font=f, fill=ink)


def stroke_text(d, txt, cx, cy, size, fill=WHITE, maxw=1000, sc=1.0, stroke=DARK):
    if sc <= 0.02: return
    f = font(P(size)); lw = f.getlength(txt)
    if lw > P(maxw): f = font(int(P(size) * P(maxw) / lw)); lw = f.getlength(txt)
    if sc != 1: f = font(max(4, int(f.size * sc))); lw = f.getlength(txt)
    bb = f.getbbox(txt)
    d.text((P(cx) - lw / 2, P(cy) - (bb[1] + bb[3]) / 2), txt, font=f, fill=fill, stroke_width=max(2, f.size // 9), stroke_fill=stroke)


def pill(d, txt, cx, cy, col, sc=1.0, size=64):
    if sc <= 0.02: return
    f = font(P(size * sc)); lw = f.getlength(txt); w2 = lw / 2 + P(44 * sc); h2 = P(size * 0.78 * sc)
    d.rounded_rectangle([P(cx) - w2, P(cy) - h2, P(cx) + w2, P(cy) + h2], radius=int(h2), fill=col, outline=DARK, width=P(6))
    bb = f.getbbox(txt)
    d.text((P(cx) - lw / 2, P(cy) - (bb[1] + bb[3]) / 2), txt, font=f, fill=WHITE)


def heart(d, x, y, r, col=(240, 70, 110)):
    d.ellipse([P(x - r), P(y - r), P(x), P(y)], fill=col); d.ellipse([P(x), P(y - r), P(x + r), P(y)], fill=col)
    d.polygon([(P(x - r), P(y - r * 0.45)), (P(x + r), P(y - r * 0.45)), (P(x), P(y + r * 0.9))], fill=col)


def drop(d, x, y, r, col=(110, 190, 250)):
    d.polygon([(P(x), P(y - r * 1.8)), (P(x - r * 0.8), P(y - r * 0.2)), (P(x + r * 0.8), P(y - r * 0.2))], fill=col)
    d.ellipse([P(x - r), P(y - r), P(x + r), P(y + r)], fill=col)


def fx_text(d, txt, x, y, t0, tt, col=(255, 230, 80), size=80, life=1.4, rot=0):
    if not (t0 <= tt < t0 + life): return
    sc = back(seg(tt, t0, t0 + 0.2)) * (1 - seg(tt, t0 + life - 0.2, t0 + life))
    stroke_text(d, txt, x, y - 30 * seg(tt, t0, t0 + life), size, col, sc=sc)


# ---------------------------------------------------------------- acting
def base_pose(gt, who):
    blink = (gt * 0.9 + (0.3 if who == 'dad' else 0.6 if who == 'kid' else 0)) % 3.1 < 0.12
    return dict(eyes='closed' if blink else 'open', mouth='smile', la=(8, 0), ra=(8, 0), bob=2 * math.sin(gt * 3), look=(0, 0))


def walk_in(o, tt, gt, t1=0.7, x0=1350, x1=PX, run=False):
    u = sm(seg(tt, 0, t1)); x = lerp(x0, x1, u)
    if tt < t1:
        ph = gt * (16 if run else 10)
        o.update(swing=(30 if run else 20) * math.sin(ph), bob=abs(math.sin(ph)) * (16 if run else 8),
                 la=(25 * math.sin(ph) + 10, -20), ra=(-25 * math.sin(ph) + 10, -20), look=(-1, 0))
    return x


def kid_react(o, react, tt, gt, d, info_pending):
    """kid reaction at local time tt (0 = when it starts)"""
    fx = []
    if react == 'happy':
        j = abs(math.sin(tt * 7)) * 60 if tt < 1.4 else 0
        o.update(eyes='happy', mouth='grin', la=(150, 10), ra=(150, 10), bob=j)
        fx.append(('sparkle',))
    elif react == 'cry':
        o.update(eyes='sad' if (gt * 2) % 1 < 0.8 else 'closed', mouth='big', mo=0.7 + 0.3 * math.sin(gt * 12), la=(20, 60), ra=(20, 60))
        fx.append(('tears', tt))
    elif react == 'shock':
        o.update(eyes='wide', mouth='o', la=(60, 100), ra=(60, 100), bob=20 * math.exp(-tt * 4))
        fx.append(('bang', tt))
    elif react == 'roll':
        o.update(eyes='roll', mouth='flat', la=(20, 70), ra=(20, 70), look=(0, -1))
        fx.append(('ugh', tt))
    elif react == 'laugh':
        o.update(eyes='happy', mouth='big', mo=0.6 + 0.4 * abs(math.sin(gt * 14)), la=(30, 80), ra=(30, 80), bob=6 * abs(math.sin(gt * 14)))
        fx.append(('haha', tt))
    elif react == 'sad':
        o.update(eyes='sad', mouth='frown', la=(5, 0), ra=(5, 0), look=(0, 1))
    elif react == 'sleep':
        o.update(eyes='closed', mouth='smile', la=(5, 0), ra=(5, 0), bob=0)
        fx.append(('zzz', tt))
    elif react == 'love':
        o.update(eyes='happy', mouth='smile', la=(10, 0), ra=(10, 0))
        fx.append(('hearts', tt))
    return fx


def draw_fx(d, fx, info, gt):
    hx, hy = info['head']; R = info['R']
    for f in fx:
        k = f[0]
        if k == 'tears':
            for s in (-1, 1):
                for i in range(3):
                    u = ((gt * 1.6 + i / 3) % 1)
                    drop(d, hx + s * (R * 0.4 + u * 60), hy + R * 0.2 + u * 220, 11)
        elif k == 'bang': fx_text(d, '!!', hx + R * 1.3, hy - R * 1.1, 0.0, f[1], (255, 90, 80), 100, 2.0)
        elif k == 'ugh': fx_text(d, 'UGH.', hx, hy - R * 1.6, 0.1, f[1], (200, 200, 220), 70, 2.0)
        elif k == 'haha': fx_text(d, 'HA HA!', hx, hy - R * 1.6, 0.0, f[1], (255, 230, 80), 76, 2.0)
        elif k == 'zzz':
            for i in range(3):
                u = (gt * 0.7 + i / 3) % 1
                stroke_text(d, 'z', hx + 40 + u * 90, hy - R - u * 160, 40 + 30 * u, (230, 230, 255))
        elif k in ('hearts', 'sparkle'):
            for i in range(5):
                u = (gt * 0.6 + i / 5) % 1
                xx = hx + math.sin(i * 2.3) * 150; yy = hy - R * 0.5 - u * 260
                if k == 'hearts': heart(d, xx, yy, 18 + 8 * math.sin(i))
                else: stroke_text(d, '*', xx, yy, 60, (255, 230, 80))


def parent_part(d, fam, who, spec, tt, gt, kid_o):
    """who = 'mom' | 'dad'; spec = (action, line, kid_reaction, prop). Returns (parent info, kid fx)."""
    act, line, react, pr = spec
    pal = fam[who]; o = base_pose(gt, who); x = PX; ex = []
    o['look'] = (-1, 0)
    if act in ('rush', 'hug'):
        run = act == 'rush'
        x = walk_in(o, tt, gt, 0.45 if run else 0.8, x1=560, run=run)
        if tt >= (0.45 if run else 0.8):
            o.update(la=(95, -40), ra=(-50, 40), eyes='happy', mouth='grin')
            ex.append(('hearts',))
    elif act == 'point':
        x = walk_in(o, tt, gt)
        if tt >= 0.7:
            o.update(la=(90, 0), ra=(35, -70), eyes='angry', mouth='open' if (tt * 6) % 1 < 0.5 and tt < 2.4 else 'flat', mo=0.5)
    elif act == 'phone':
        x = walk_in(o, tt, gt, 0.9)
        o.update(ra=(30, 120), look=(0.5, 1), eyes='open' if tt % 2.4 > 0.12 else 'closed', mouth='smile')
        if tt >= 2.4: o.update(la=(150, 10), mouth='grin')
    elif act == 'film':
        x = walk_in(o, tt, gt, 0.8)
        o.update(la=(120, -40), ra=(30, 60), eyes='happy', mouth='grin')
    elif act == 'sleep':
        x = None
    elif act == 'panic':
        if tt < 0.5: x = walk_in(o, tt, gt, 0.5, run=True)
        else:
            x = PX + 120 * math.sin((tt - 0.5) * 5)
            o.update(la=(160 + 15 * math.sin(gt * 25), 0), ra=(160 + 15 * math.cos(gt * 25), 0), eyes='wide', mouth='big', mo=1,
                     swing=28 * math.sin(gt * 18), bob=abs(math.sin(gt * 18)) * 18)
            ex.append(('sweat',))
    elif act == 'cook':
        x = walk_in(o, tt, gt, 0.6)
        o.update(la=(55, 10), eyes='happy' if tt > 1.2 else 'open', mouth='grin')
    elif act == 'shrug':
        x = walk_in(o, tt, gt)
        if tt >= 0.8:
            u = sm(seg(tt, 0.8, 1.1))
            o.update(la=(lerp(8, 60, u), lerp(0, -110, u)), ra=(lerp(8, 60, u), lerp(0, -110, u)), mouth='smile', eyes='open', bob=8 * u, look=(0, -0.5))
    elif act == 'dance':
        x = walk_in(o, tt, gt, 0.6)
        if tt >= 0.6:
            b = math.sin(gt * 12)
            o.update(la=(150 if b > 0 else 40, -40), ra=(40 if b > 0 else 150, -40), bob=abs(b) * 30, swing=18 * b, eyes='happy', mouth='grin', lean=30 * b)
            ex.append(('notes',))
    elif act == 'joke':
        x = walk_in(o, tt, gt)
        if 0.8 <= tt < 2.3: o.update(ra=(60, -60), mouth='open' if (tt * 7) % 1 < 0.5 else 'smile', mo=0.5)
        elif tt >= 2.3:
            o.update(eyes='happy', mouth='big', mo=0.6 + 0.4 * abs(math.sin(gt * 14)), la=(25, 90), ra=(25, 90), bob=10 * abs(math.sin(gt * 14)))
            ex.append(('haha_p', tt - 2.3))
    elif act == 'gift':
        x = walk_in(o, tt, gt)
        o.update(la=(40 + 45 * sm(seg(tt, 0.8, 1.2)), -30), eyes='happy', mouth='grin')
    elif act == 'flex':
        x = walk_in(o, tt, gt)
        if tt >= 0.8: o.update(la=(95, -120), ra=(95, -120), eyes='angry', mouth='grin', bob=4); ex.append(('shine',))
    elif act == 'eat':
        x = walk_in(o, tt, gt)
        ch = (tt * 2.5) % 1 < 0.5
        o.update(la=(40, 40), ra=(30, 130) if ch else (20, 80), mouth='o' if ch else 'smile', eyes='happy')
    elif act == 'shock':
        x = walk_in(o, tt, gt, 0.6)
        if tt >= 0.7:
            o.update(eyes='wide', mouth='big', la=(150, 20), ra=(150, 20), bob=40 * math.exp(-(tt - 0.7) * 5))
            ex.append(('bang_p', tt - 0.7))
    elif act == 'calm':
        x = walk_in(o, tt, gt)
        if tt >= 0.8: o.update(la=(55, -40), mouth='open' if (tt * 6) % 1 < 0.5 and tt < 2.4 else 'smile', mo=0.4)
    elif act == 'facepalm':
        x = walk_in(o, tt, gt)
        if tt >= 1.4: o.update(ra=(150, -150), eyes='closed', mouth='frown')
    else:
        x = walk_in(o, tt, gt)
    # draw parent
    if x is None:   # asleep on the couch: draw horizontally on a sprite
        spr = Image.new('RGBA', (P(700), P(1000)), (0, 0, 0, 0)); sd = ImageDraw.Draw(spr)
        o.update(eyes='closed', mouth='open' if (gt * 1.2) % 1 < 0.5 else 'o', mo=0.4, la=(150, 20), ra=(10, 0))
        if tt >= 2.4: o.update(la=(120, 40))
        pinfo = person(sd, pal, 350, 980, o)
        f = 0.78
        rot = spr.rotate(-90, expand=True, resample=Image.BICUBIC)
        rot = rot.resize((int(rot.width * f), int(rot.height * f)), Image.BICUBIC)
        hx, hy = (1000 - pinfo['head'][1]) * f, pinfo['head'][0] * f      # head inside the rotated sprite (logical)
        ox, oy = 975 - hx, GY - 250 - hy
        d._image.paste(rot, (P(ox), P(oy)), rot)
        info = dict(head=(975, GY - 250), R=pinfo['R'] * f, top=GY - 420, hands=[(900, GY - 260)] * 2)
        ex.append(('zzz_p',))
    else:
        info = person(d, pal, x, GY, o)
    # prop
    if pr:
        hx, hy = info['hands'][0]
        if act == 'gift':
            if tt < 1.3: prop(d, pr, hx, hy - 10, 1.1, gt=gt)
            elif tt < 1.7: prop(d, pr, lerp(hx, KX + 60, sm(seg(tt, 1.3, 1.7))), lerp(hy, GY - 330, sm(seg(tt, 1.3, 1.7))), 1.1, gt=gt)
            # after 1.7 s the kid holds it: drawn in frame() on top of the kid
        elif act == 'phone': prop(d, 'phone', info['hands'][1][0], info['hands'][1][1] - 20, 1.0)
        elif act == 'film':
            prop(d, 'phone', info['hands'][0][0], info['hands'][0][1] - 10, 1.1)
            if (gt * 2) % 1 < 0.6: stroke_text(d, 'REC', info['hands'][0][0], info['hands'][0][1] - 90, 40, (255, 80, 80))
        elif act == 'cook':
            prop(d, 'pan', hx, hy, 1.0)
            fl = (tt * 1.1) % 1; py = hy - 10 - 260 * math.sin(math.pi * fl) if tt > 0.8 else hy - 10
            sp = 'cookie' if pr != 'pan' else 'cookie'
            d.ellipse([P(hx - 75), P(py - 14), P(hx + 10), P(py + 14)], fill=(240, 190, 110), outline=DARK, width=P(4))
        elif act == 'eat': prop(d, pr, hx, hy - 20, 1.0)
        elif act != 'sleep': prop(d, pr, hx, hy - 10, 1.0, gt=gt)
    draw_parent_fx(d, ex, info, gt, tt)
    return info


def draw_parent_fx(d, ex, info, gt, tt):
    hx, hy = info['head']; R = info['R']
    for f in ex:
        k = f[0]
        if k == 'hearts':
            for i in range(4):
                u = (gt * 0.6 + i / 4) % 1
                heart(d, hx - 120 + i * 70, hy - R - u * 220, 20)
        elif k == 'sweat':
            for i in range(2):
                u = (gt * 2 + i / 2) % 1
                drop(d, hx + (R + 20) * (1 if i else -1), hy - R * 0.4 + u * 80, 12)
        elif k == 'notes':
            for i in range(3):
                u = (gt * 0.8 + i / 3) % 1
                nx, ny = hx - 160 + i * 150, hy - R - u * 200
                circ(d, nx, ny, 16, (255, 230, 80), 4)
                d.line([P(nx + 13), P(ny), P(nx + 13), P(ny - 60)], fill=DARK, width=P(6))
                d.line([P(nx + 13), P(ny - 60), P(nx + 40), P(ny - 45)], fill=DARK, width=P(6))
        elif k == 'haha_p': fx_text(d, 'HA HA HA!', hx, hy - R * 1.7, 0, f[1], (255, 230, 80), 72, 2.0)
        elif k == 'bang_p': fx_text(d, 'WHAT?!', hx, hy - R * 1.8, 0, f[1], (255, 90, 80), 90, 2.0)
        elif k == 'shine':
            for i in range(4):
                a = gt * 3 + i * 1.57
                stroke_text(d, '*', hx + math.cos(a) * 200, hy + 60 + math.sin(a) * 80, 56, (255, 240, 120))
        elif k == 'zzz_p':
            for i in range(3):
                u = (gt * 0.6 + i / 3) % 1
                stroke_text(d, 'Z', hx + u * 60, hy - 60 - u * 200, 46 + 30 * u, (230, 230, 255))


# ---------------------------------------------------------------- frame
PLAN = {}


def frame(t):
    sits, fam = PLAN['sits'], PLAN['fam']
    ri = int(t // ROUND); gt = t
    if ri >= len(sits): return outro_frame(t - len(sits) * ROUND)
    sit = sits[ri]; lt = t - ri * ROUND
    img = room_img(sit['room'], PLAN['seed'] + ri).copy(); d = ImageDraw.Draw(img)
    phase = 'kid' if lt < KIDT else 'mom' if lt < KIDT + PART else 'dad'
    pt = lt - KIDT if phase == 'mom' else lt - KIDT - PART if phase == 'dad' else lt
    ko = base_pose(gt, 'kid'); ko['look'] = (1, 0) if phase != 'kid' else (0, 0)
    kfx = []
    if phase == 'kid':
        ko.update(mouth='open' if lt < 1.2 and (lt * 7) % 1 < 0.5 else 'smile', mo=0.5, eyes=sit.get('kid_eyes', ko['eyes']))
        if sit.get('kid_eyes') == 'sad': ko['mouth'] = 'frown' if (lt * 7) % 1 >= 0.5 else 'open'
    else:
        spec = sit[phase]
        if pt >= 2.15: kfx = kid_react(ko, spec[2], pt - 2.15, gt, d, None)
        if spec[0] == 'sleep' and pt < 2.15: ko['look'] = (1, 0)
    # draw parent first if it is behind (sleep on couch draws on room), kid in front
    pinfo = None
    if phase != 'kid':
        pinfo = parent_part(d, fam, phase, sit[phase], pt, gt, ko)
    kinfo = person(d, fam['kid'], KX, GY, ko)
    if phase != 'kid' and sit[phase][0] == 'gift' and sit[phase][3] and pt >= 1.7:
        prop(d, sit[phase][3], KX + 60, GY - 330 - ko.get('bob', 0), 1.1, gt=gt)
    draw_fx(d, kfx, kinfo, gt)
    # bubbles
    if phase == 'kid':
        bubble(d, sit['kid'], KX + 120, kinfo['top'] - 40, KX + 30, kinfo['top'] - 5, 0.15, lt, size=62)
    else:
        line = sit[phase][1]
        hx, hy = pinfo['head']
        bubble(d, line, min(max(hx, 380), 700), pinfo['top'] - 50, hx - 20, pinfo['top'] - 10, 0.75 if sit[phase][0] != 'sleep' else 0.4, pt,
               col=lerpc(MOMC if phase == 'mom' else DADC, WHITE, 0.82), size=58)
    # top: situation + MOM / DAD pill
    head = sit['cap']
    stroke_text(d, 'MOM vs DAD', W / 2, 120, 66, (255, 230, 80), sc=1.0)
    stroke_text(d, head, W / 2, 205, 62, WHITE, maxw=1000)
    if phase != 'kid':
        sc = back(seg(pt, 0, 0.25))
        pill(d, 'MOM' if phase == 'mom' else 'DAD', W / 2, 310, MOMC if phase == 'mom' else DADC, sc, 66)
    else:
        stroke_text(d, f'ROUND {ri + 1}', W / 2, 310, 50, (220, 220, 240), sc=back(seg(lt, 0, 0.25)))
    # wipe between parts
    for edge in (KIDT, KIDT + PART):
        dt = lt - edge
        if -0.12 < dt < 0.12:
            a = 1 - abs(dt) / 0.12
            ov = Image.new('RGB', img.size, WHITE); img = Image.blend(img, ov, 0.55 * a); d = ImageDraw.Draw(img)
    return img


def outro_frame(lt):
    fam = PLAN['fam']; gt = lt + 100
    img = room_img('living', PLAN['seed'] + 77).copy(); d = ImageDraw.Draw(img)
    om = base_pose(gt, 'mom'); od = base_pose(gt, 'dad'); ok = base_pose(gt, 'kid')
    wv = math.sin(gt * 9)
    om.update(la=(150 + 20 * wv, 0), mouth='grin'); od.update(ra=(150 - 20 * wv, 0), mouth='grin'); ok.update(eyes='happy', mouth='grin')
    person(d, fam['mom'], 250, GY, om); person(d, fam['dad'], 830, GY, od); person(d, fam['kid'], 540, GY, ok)
    sc = back(seg(lt, 0, 0.3))
    stroke_text(d, 'WHO DID IT BETTER?', W / 2, 330, 84, (255, 230, 80), sc=sc)
    pill(d, '1 = MOM', W / 2 - 230, 500, MOMC, back(seg(lt, 0.2, 0.5)), 60)
    pill(d, '2 = DAD', W / 2 + 230, 500, DADC, back(seg(lt, 0.35, 0.65)), 60)
    stroke_text(d, 'Comment below!', W / 2, 640, 60, WHITE, sc=back(seg(lt, 0.5, 0.8)))
    return img


def render_frame(i):
    img = frame(i / FPS)
    return img.resize((W, H), Image.LANCZOS).tobytes()


def init_worker(plan):
    global PLAN
    PLAN = plan


# ---------------------------------------------------------------- audio (all synthesized)
def total_dur(plan): return len(plan['sits']) * ROUND + OUTRO


def tone(f, dur, amp=0.3, decay=6.0, harm=(1, 0.5, 0.25)):
    t = np.arange(int(SR * dur)) / SR
    y = sum(a * np.sin(2 * np.pi * f * (k + 1) * t) for k, a in enumerate(harm))
    return amp * y * np.exp(-decay * t) * np.clip(t * 400, 0, 1)


def music(dur, seed):
    r = random.Random(seed); bpm = r.choice([112, 118, 124]); beat = 60 / bpm
    key = r.choice([0, 2, 5, 7]); base = 220 * 2 ** (key / 12)
    prog = r.choice([[0, 5, 3, 4], [0, 3, 4, 4], [0, 4, 5, 3]])
    scale = [0, 2, 4, 5, 7, 9, 11]
    out = np.zeros(int(SR * (dur + 1)))
    def add(sig, t0):
        i = int(t0 * SR); n = min(len(sig), len(out) - i)
        if n > 0: out[i:i + n] += sig[:n]
    nb = int(dur / beat) + 1
    mel = [r.choice([0, 2, 4, 4, 7, 9]) for _ in range(16)]
    for b in range(nb):
        ch = prog[(b // 4) % 4]; root = base * 2 ** (scale[ch] / 12) / 2
        add(tone(root, beat * 0.9, 0.22, 5, (1, 0.3)), b * beat)                       # bass
        if b % 2 == 1:
            for iv in (0, 4, 7): add(tone(root * 2 * 2 ** (iv / 12), beat * 0.5, 0.06, 9), b * beat)   # off-beat chord
        if b % 4 in (1, 3):   # clap
            n = np.random.RandomState(b).randn(int(SR * 0.08)) * np.exp(-np.arange(int(SR * 0.08)) / SR * 50) * 0.08
            add(n, b * beat)
        m = mel[b % 16]
        if (b + 2) % 4 != 0: add(tone(base * 2 * 2 ** ((scale[(ch + m // 2) % 7]) / 12), beat * 0.45, 0.07, 10, (1, 0.2, 0.1)), b * beat + beat * 0.5)
    return out[:int(SR * dur)]


def sfx_pop():
    t = np.arange(int(SR * 0.12)) / SR
    return 0.35 * np.sin(2 * np.pi * (500 + 1800 * t) * t) * np.exp(-t * 30)


def sfx_whoosh():
    n = int(SR * 0.3); x = np.random.RandomState(3).randn(n); env = np.sin(np.linspace(0, np.pi, n)) ** 2
    y = np.convolve(x, np.ones(30) / 30, mode='same')
    return 0.25 * y * env


def sfx_slide(up=False):
    t = np.arange(int(SR * 0.45)) / SR; f0, f1 = (300, 1200) if up else (1200, 300)
    f = f0 + (f1 - f0) * t / t[-1]
    return 0.22 * np.sin(2 * np.pi * np.cumsum(f) / SR) * np.exp(-t * 2)


def sfx_ding():
    return tone(1320, 0.6, 0.18, 4, (1, 0.4)) + tone(1760, 0.6, 0.1, 5, (1,))


def sfx_boing():
    t = np.arange(int(SR * 0.35)) / SR
    return 0.25 * np.sin(2 * np.pi * (180 + 80 * np.sin(t * 50)) * t) * np.exp(-t * 7)


def soundtrack(plan, path):
    dur = total_dur(plan)
    y = music(dur, plan['seed']) * 0.8
    def add(sig, t0, g=1.0):
        i = int(t0 * SR); n = min(len(sig), len(y) - i)
        if n > 0: y[i:i + n] += sig[:n] * g
    for ri, sit in enumerate(plan['sits']):
        t0 = ri * ROUND
        add(sfx_pop(), t0 + 0.15)
        for k, who in enumerate(('mom', 'dad')):
            ts = t0 + KIDT + k * PART
            act, _, react, _ = sit[who]
            add(sfx_whoosh(), ts - 0.1)
            add(sfx_pop(), ts + (0.4 if act == 'sleep' else 0.75))
            rs = ts + 2.15
            if react in ('happy', 'love'): add(sfx_ding(), rs)
            elif react in ('shock',): add(sfx_slide(False), rs)
            elif react in ('cry', 'sad'): add(sfx_slide(False), rs, 0.6)
            elif react in ('laugh',): add(sfx_boing(), rs)
            elif react == 'roll': add(sfx_boing(), rs, 0.6)
            if act in ('panic', 'shock', 'dance', 'flex'): add(sfx_boing(), ts + 0.7, 0.7)
    add(sfx_ding(), len(plan['sits']) * ROUND + 0.1)
    y = np.clip(y / max(1.0, np.abs(y).max() / 0.9), -1, 1)
    pcm = (y * 32767).astype(np.int16)
    with wave.open(path, 'wb') as w:
        w.setnchannels(1); w.setsampwidth(2); w.setframerate(SR); w.writeframes(pcm.tobytes())


def render(plan, out_mp4, procs=None):
    os.makedirs(os.path.dirname(out_mp4), exist_ok=True)
    n = int(total_dur(plan) * FPS)
    wav = out_mp4.replace('.mp4', '.wav'); soundtrack(plan, wav)
    ff = imageio_ffmpeg.get_ffmpeg_exe()
    cmd = [ff, '-y', '-loglevel', 'error', '-f', 'rawvideo', '-pix_fmt', 'rgb24', '-s', f'{W}x{H}', '-r', str(FPS), '-i', '-',
           '-i', wav, '-c:v', 'libx264', '-preset', 'medium', '-crf', '20', '-pix_fmt', 'yuv420p', '-c:a', 'aac', '-b:a', '160k',
           '-shortest', '-movflags', '+faststart', out_mp4]
    p = subprocess.Popen(cmd, stdin=subprocess.PIPE)
    with Pool(procs or os.cpu_count(), initializer=init_worker, initargs=(plan,)) as pool:
        for k, b in enumerate(pool.imap(render_frame, range(n), chunksize=4)):
            p.stdin.write(b)
            if k % 150 == 0: print(f'  frame {k}/{n}', flush=True)
    p.stdin.close(); p.wait()
    if p.returncode: sys.exit('ffmpeg failed')
    os.remove(wav)


def make_plan(keys, seed=1):
    from situations import SITS
    return dict(sits=[dict(SITS[k], key=k) for k in keys], fam=family(seed), seed=seed)


if __name__ == '__main__':
    import argparse
    ap = argparse.ArgumentParser()
    ap.add_argument('--sit', default='sick,bored,money'); ap.add_argument('--seed', type=int, default=1)
    ap.add_argument('--preview', default=''); ap.add_argument('--render', action='store_true')
    a = ap.parse_args()
    plan = make_plan(a.sit.split(','), a.seed); PLAN = plan
    if a.preview:
        os.makedirs(OUT, exist_ok=True)
        for ts in a.preview.split(','):
            frame(float(ts)).resize((W // 2, H // 2), Image.LANCZOS).save(os.path.join(OUT, f'prev_{ts}.png'))
        print('ok')
    if a.render:
        render(plan, os.path.join(OUT, 'final.mp4'))
        print('rendered', os.path.join(OUT, 'final.mp4'))

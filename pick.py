#!/usr/bin/env python3
"""Sıradaki simülasyonu seç (tekrar yok) → output/params.json + output/meta_upload.json
Tür sırayla döner, aynı tür arka arkaya gelmez; aynı (tür, sayı, top, malzeme) birleşimi asla tekrar etmez."""
import json, os, random, sys
from datetime import datetime, timezone
from pathlib import Path

HERE = Path(__file__).resolve().parent
HIST = HERE / 'records' / 'history.json'
OUT = HERE / 'output'

BALL_MATS = ['steel', 'gold', 'copper', 'black iron']
DENSITY = {'steel': 7850, 'gold': 19300, 'copper': 8960, 'black iron': 7870}   # kg/m³ (gerçek değerler)
KINDS = {
    'wall':    dict(rows=(12, 20), cols=(9, 15), ball_r=(0.3, 0.55), hit_h=(0.25, 0.6)),
    'tower':   dict(layers=(14, 24), ball_r=(0.2, 0.4), hit_h=(0.15, 0.55)),
    'pyramid': dict(base=(4, 6), ball_r=(0.6, 1.1)),
}


def kg(m): return f'{m:,} kg'


def title_of(p, n):
    mat = p['ball_mat'].title()
    thing = {'wall': f'{n}-Brick Wall', 'tower': f'{n}-Block Wooden Tower', 'pyramid': f'Pyramid of {n} Wooden Crates'}[p['kind']]
    verb = 'Dropped on a' if p['kind'] == 'pyramid' else 'vs'
    t = f"{kg(p['ball_mass'])} {mat} Ball {verb} {thing}"
    return f"{t} | Physics Simulation"


def count_of(p):
    return {'wall': lambda: p['rows'] * p['cols'], 'tower': lambda: p['layers'] * 3,
            'pyramid': lambda: sum((p['base'] - i) ** 2 for i in range(p['base']))}[p['kind']]()


def main():
    hist = json.loads(HIST.read_text()) if HIST.exists() else []
    seen = {h['key'] for h in hist}
    last = hist[-1]['kind'] if hist else None
    rng = random.Random(f"{datetime.now(timezone.utc):%Y%m%d%H}-{len(hist)}")
    order = [k for k in KINDS if k != last]
    used = {k: sum(h['kind'] == k for h in hist) for k in KINDS}
    order.sort(key=lambda k: (used[k], rng.random()))     # en az kullanılan tür önce
    for kind in order:
        spec = KINDS[kind]
        for _ in range(200):
            p = {'kind': kind, 'seed': rng.randrange(10 ** 6), 'frames': 300, 'spp': 16, 'hit_frame': 26,
                 'ball_mat': rng.choice(BALL_MATS)}
            for k, v in spec.items():
                p[k] = rng.randint(*v) if isinstance(v[0], int) else round(rng.uniform(*v), 2)
            m = DENSITY[p['ball_mat']] * 4 / 3 * 3.14159265 * p['ball_r'] ** 3   # kütle = yoğunluk × hacim
            p['ball_mass'] = int(round(m, -1 if m < 10000 else -2))
            n = count_of(p)
            key = f"{kind}-{n}-{p['ball_mass']}-{p['ball_mat']}"
            if key not in seen: break
        else:
            continue
        break
    else:
        sys.exit('yeni birleşim kalmadı')
    title = title_of(p, n)
    what = {'wall': f'a {n}-brick wall (each brick about 2 kg)', 'tower': f'a tower of {n} wooden blocks',
            'pyramid': f'a pyramid of {n} wooden crates'}[kind]
    desc = (f"A solid {p['ball_mat']} ball, {p['ball_r'] * 2:.2f} m across ({kg(p['ball_mass'])}, from the real density of {p['ball_mat']}), meets {what}. Shown in slow motion (0.5x).\n\n"
            "This is a 3D physics simulation, built and rendered in Blender (rigid-body physics, Cycles renderer). "
            "Nothing real was destroyed and this is not real footage. Results are illustrative, not engineering data.\n\n"
            "What should reach its breaking point next? Tell us in the comments.\n\n"
            "#physics #simulation #satisfying")
    tags = ['physics simulation', 'blender', 'satisfying', 'destruction', 'slow motion', 'rigid body', '3d simulation',
            {'wall': 'brick wall', 'tower': 'jenga', 'pyramid': 'crates'}[kind], f"{p['ball_mat']} ball"]
    OUT.mkdir(exist_ok=True)
    (OUT / 'params.json').write_text(json.dumps(p))
    (OUT / 'meta_upload.json').write_text(json.dumps(dict(title=title, description=desc, tags=tags, key=key, kind=kind, n=n,
                                                          hook=hook_of(p, n), params=p)))
    print(title)


def hook_of(p, n):
    """ekranın üstündeki kısa yazı (başlıkla aynı bilgi, kandırmaca yok)"""
    target = {'wall': f'{n} BRICKS', 'tower': f'{n}-BLOCK TOWER', 'pyramid': f'{n} CRATES'}[p['kind']]
    return [f"{p['ball_mass']:,} KG {p['ball_mat'].upper()} BALL", 'VS', target]


if __name__ == '__main__':
    main()

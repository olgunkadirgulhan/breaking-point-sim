#!/usr/bin/env python3
"""Sıradaki seriyi seç (tekrar yok) → output/rounds.json + output/meta_upload.json

Rakip analizi (2026-10-20, 446 fizik-sim Short'u): 31-60 sn'lik videolar medyanda 2-3 kat daha çok izleniyor,
en iyi formatlar "0% vs 100%" ve seviye seviye büyüyen seriler. Bu yüzden her video 4-5 turluk bir seri:
aynı sahne, tek bir değişken adım adım artar, izleyici bir sonrakini görmek için kalır.

Dürüstlük: kütle gerçek yoğunluk × hacimden; hız km/h olarak simülasyondaki çarpma hızı; başlık ekrandakiyle aynı."""
import json, math, random, sys
from datetime import datetime, timezone
from pathlib import Path

HERE = Path(__file__).resolve().parent
HIST = HERE / 'records' / 'history.json'
OUT = HERE / 'output'

DENSITY = {'wood': 700, 'rubber': 1100, 'aluminium': 2700, 'steel': 7850, 'black iron': 7870, 'copper': 8960, 'lead': 11340,
           'gold': 19300}   # kg/m³


def mass(mat, r):
    m = DENSITY[mat] * 4 / 3 * math.pi * r ** 3
    return int(round(m, -1 if m < 10000 else -2)) if m >= 10 else round(m, 1)


def r_for(mat, m):
    return round((m / DENSITY[mat] * 3 / (4 * math.pi)) ** (1 / 3), 3)


def kg(m): return f'{m:,} kg' if m >= 10 else f'{m:g} kg'


def series(kind, rng):
    """(base sahne, tur listesi [(değişiklik, ekran etiketi)], başlık, açıklama cümlesi, anahtar)"""
    if kind == 'mass_wall':
        rows, cols = rng.randint(12, 18), rng.randint(10, 14); mat = rng.choice(['steel', 'black iron', 'copper'])
        steps = rng.choice([[10, 100, 1000, 5000, 20000], [20, 200, 2000, 8000, 30000], [5, 50, 500, 3000, 15000]])
        base = dict(kind='wall', rows=rows, cols=cols, ball_mat=mat, hit_h=round(rng.uniform(0.3, 0.5), 2), speed=10)
        rounds = [(dict(ball_r=r_for(mat, m), ball_mass=m), kg(m)) for m in steps]
        n = rows * cols
        return (base, rounds, f"{mat.title()} Ball vs {n}-Brick Wall: {kg(steps[0])} to {kg(steps[-1])} | Physics Simulation",
                f"The same {n}-brick wall is hit five times at 36 km/h by a solid {mat} ball that gets heavier every round "
                f"({kg(steps[0])} to {kg(steps[-1])}; the ball's size follows from the real density of {mat}).", f'mass_wall-{n}-{mat}-{steps[0]}')
    if kind == 'mortar_wall':
        rows, cols = rng.randint(12, 16), rng.randint(10, 14); m = rng.choice([1500, 2500, 4000]); mat = 'steel'
        base = dict(kind='wall', rows=rows, cols=cols, ball_mat=mat, ball_r=r_for(mat, m), ball_mass=m, hit_h=round(rng.uniform(0.3, 0.5), 2),
                    speed=10, mortar_max=4.0)
        rounds = [(dict(mortar=p / 100), f'{p}% CEMENT') for p in (0, 25, 50, 75, 100)]
        n = rows * cols
        return (base, rounds, f"0% vs 100% Cement Strength: {n}-Brick Wall vs {kg(m)} Steel Ball | Physics Simulation",
                f"Five identical {n}-brick walls, each with stronger mortar bonds between the bricks (0% = loose bricks, "
                f"100% = the strongest bond in this simulation), hit by the same {kg(m)} steel ball at 36 km/h.", f'mortar_wall-{n}-{m}')
    if kind == 'speed_tower':
        layers = rng.randint(16, 22); mat = rng.choice(['steel', 'copper', 'lead']); r = round(rng.uniform(0.12, 0.2), 2); m = mass(mat, r)
        kmh = rng.choice([[10, 30, 60, 120, 250], [5, 20, 50, 100, 200], [15, 40, 80, 150, 300]])
        base = dict(kind='tower', layers=layers, ball_mat=mat, ball_r=r, ball_mass=m, hit_h=round(rng.uniform(0.2, 0.45), 2))
        rounds = [(dict(speed=round(v / 3.6, 2)), f'{v} KM/H') for v in kmh]
        n = layers * 3
        return (base, rounds, f"{kg(m)} {mat.title()} Ball vs {n}-Block Tower at {kmh[0]} to {kmh[-1]} km/h | Physics Simulation",
                f"The same {kg(m)} {mat} ball hits the same {n}-block wooden tower five times, faster every round "
                f"({kmh[0]} to {kmh[-1]} km/h impact speed).", f'speed_tower-{n}-{mat}-{kmh[-1]}')
    if kind == 'material_pyramid':
        base_n = rng.randint(4, 5); r = round(rng.uniform(0.55, 0.8), 2)
        mats = ['wood', 'aluminium', 'steel', 'lead', 'gold']
        base = dict(kind='pyramid', base=base_n, ball_r=r)
        rounds = [(dict(ball_mat=mt, ball_mass=mass(mt, r)), f'{mt.upper()} · {kg(mass(mt, r))}') for mt in mats]
        n = sum((base_n - i) ** 2 for i in range(base_n))
        return (base, rounds, f"Same Size Ball, 5 Materials: Wood to Gold vs {n} Crates | Physics Simulation",
                f"A {r * 2:.2f} m ball dropped on a pyramid of {n} wooden crates, five times: wood, aluminium, steel, lead and gold. "
                f"Same size, so only the mass changes ({kg(mass('wood', r))} to {kg(mass('gold', r))}, from real densities).",
                f'material_pyramid-{n}-{r}')
    if kind == 'rain_tower':
        layers = rng.randint(14, 20); counts = [1, 10, 100, 1000]
        base = dict(kind='rain', layers=layers, ball_mat='steel', bead_r=0.05, bead_mass=mass('steel', 0.05))
        rounds = [(dict(count=c), f'{c:,} BALL' + ('S' if c > 1 else '')) for c in counts]
        n = layers * 3
        return (base, rounds, f"1 vs 10 vs 100 vs 1,000 Steel Balls on a {n}-Block Tower | Physics Simulation",
                f"Steel balls ({kg(mass('steel', 0.05))} each, 10 cm across) dropped onto the same {n}-block wooden tower: "
                f"1, then 10, then 100, then 1,000.", f'rain_tower-{n}')
    raise SystemExit(kind)


KINDS = ['mortar_wall', 'mass_wall', 'speed_tower', 'material_pyramid', 'rain_tower']


def main():
    hist = json.loads(HIST.read_text()) if HIST.exists() else []
    seen = {h['key'] for h in hist}; last = hist[-1].get('series') if hist else None
    rng = random.Random(f"{datetime.now(timezone.utc):%Y%m%d%H}-{len(hist)}")
    used = {k: sum(h.get('series') == k for h in hist) for k in KINDS}
    order = sorted([k for k in KINDS if k != last], key=lambda k: (used[k], rng.random()))
    if len(sys.argv) > 1: order = [sys.argv[1]]
    for kind in order:
        for _ in range(100):
            base, rounds, title, what, key = series(kind, rng)
            if key not in seen: break
        else:
            continue
        break
    else:
        sys.exit('yeni seri kalmadı')
    seed = rng.randrange(10 ** 6)
    sun = dict(sun_el=round(rng.uniform(14, 38), 1), sun_az=round(rng.uniform(0, 360), 1), cam_az=round(rng.uniform(-70, -40), 1))
    frames = 165 if len(rounds) == 5 else 195
    R = [dict(base, **ch, **sun, seed=seed, frames=frames, spp=16, hit_frame=26, res=[1080, 1920], label=lab) for ch, lab in rounds]
    desc = (f"{what} Shown in slow motion (0.5x).\n\nWhich round surprised you the most?\n\n"
            "This is a 3D physics simulation, built and rendered in Blender (rigid-body physics, Cycles renderer). "
            "Nothing real was destroyed and this is not real footage. Results are illustrative, not engineering data.\n\n"
            "#physics #simulation #satisfying")
    tags = ['physics simulation', 'blender', 'satisfying', 'destruction', 'slow motion', 'rigid body', '3d simulation', '0 vs 100']
    OUT.mkdir(exist_ok=True)
    (OUT / 'rounds.json').write_text(json.dumps(R))
    (OUT / 'meta_upload.json').write_text(json.dumps(dict(title=title, description=desc, tags=tags, key=key, series=kind,
                                                          kind=base['kind'], n=len(R), hook=title.split(' | ')[0], labels=[r['label'] for r in R])))
    print(title); print(' / '.join(r['label'] for r in R))


if __name__ == '__main__':
    main()

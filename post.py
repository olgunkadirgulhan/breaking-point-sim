#!/usr/bin/env python3
"""output/raw_{i}.mp4 + sim_meta_{i}.json (tur başına) → output/final.mp4: ilk 2.5 sn başlık, her turda büyük tur etiketi +
ilerleme çubuğu, kalıcı '3D PHYSICS SIMULATION' etiketi; ses her turun çarpışma şiddetinden üretilir."""
import json, subprocess, wave
from pathlib import Path
import numpy as np
from PIL import Image, ImageDraw, ImageFilter
import brand as B

HERE = Path(__file__).resolve().parent
OUT = HERE / 'output'
SR = 44100
W, H = 1080, 1920


def text_shadow(img, xy, s, f, fill, anchor='mm', r=10):
    sh = Image.new('RGBA', img.size, (0, 0, 0, 0)); d = ImageDraw.Draw(sh)
    d.text(xy, s, font=f, fill=(0, 0, 0, 200), anchor=anchor)
    sh = sh.filter(ImageFilter.GaussianBlur(r)); img.alpha_composite(sh)
    ImageDraw.Draw(img).text(xy, s, font=f, fill=fill, anchor=anchor)


def fit(d, s, size, maxw):
    while size > 40 and d.textlength(s, font=B.TITLE(size)) > maxw: size -= 4
    return B.TITLE(size)


def wrap(d, s, size, maxw):
    """başlığı en fazla 3 satıra böl"""
    words = s.split(); lines = ['']
    for w in words:
        t = (lines[-1] + ' ' + w).strip()
        if d.textlength(t, font=B.TITLE(size)) <= maxw: lines[-1] = t
        else: lines.append(w)
    return lines


def overlays(meta):
    """ov_hook.png: videonun ilk 2.5 sn'si başlık; ov_r{i}.png: tur etiketi + kalıcı 'SIMULATION' etiketi"""
    hook = Image.new('RGBA', (W, H), (0, 0, 0, 0)); d = ImageDraw.Draw(hook)
    size = 92; lines = wrap(d, meta['hook'].upper(), size, W - 120)
    while len(lines) > 3: size -= 8; lines = wrap(d, meta['hook'].upper(), size, W - 120)
    for i, l in enumerate(lines):
        text_shadow(hook, (W // 2, 330 + i * (size + 12)), l, B.TITLE(size), B.WHITE + (255,))
    d.rounded_rectangle([40, 70, 400, 128], radius=8, fill=B.HOT + (235,))   # sim etiketi başlıkta da görünsün
    d.text((220, 99), '3D PHYSICS SIMULATION', font=B.MONO(26, 700), fill=B.BG + (255,), anchor='mm')
    hook.save(OUT / 'ov_hook.png')
    n = len(meta['labels'])
    for i, lab in enumerate(meta['labels']):
        img = Image.new('RGBA', (W, H), (0, 0, 0, 0)); d = ImageDraw.Draw(img)
        d.rounded_rectangle([40, 70, 400, 128], radius=8, fill=B.HOT + (235,))
        d.text((220, 99), '3D PHYSICS SIMULATION', font=B.MONO(26, 700), fill=B.BG + (255,), anchor='mm')
        f = B.MONO(28, 600); line = f'ROUND {i + 1}/{n}  ·  0.5x SLOW-MO'; w = d.textlength(line, font=f)
        d.rounded_rectangle([40, 140, 40 + w + 32, 190], radius=8, fill=(17, 19, 22, 190))
        d.text((56, 165), line, font=f, fill=B.WHITE + (255,), anchor='lm')
        # tur etiketi: büyük, ilerleme çubuğu ile
        text_shadow(img, (W // 2, 640), lab, fit(d, lab, 120, W - 140), B.WHITE + (255,))
        bw = 560; x0 = W // 2 - bw // 2
        for k in range(n):
            seg = [x0 + k * bw // n + 6, 720, x0 + (k + 1) * bw // n - 6, 734]
            d.rounded_rectangle(seg, radius=6, fill=(B.HOT + (255,)) if k <= i else (236, 238, 240, 90))
        img.save(OUT / f'ov_r{i}.png')


def audio(sim, dur):
    """kare başı çarpışma şiddeti → malzemeye göre filtrelenmiş darbe sesleri + çarpma anında derin gümleme"""
    rng = np.random.default_rng(sim.get('seed', 1)); n = int(dur * SR); out = np.zeros(n)
    inten = np.array(sim['intensity'], float); fps = sim['fps']
    base = np.median(inten[: max(3, sim['hit_frame'] - 2)]) if len(inten) > 5 else 0
    inten = np.clip(inten - base * 1.05, 0, None)
    if inten.max() > 0: inten /= np.percentile(inten[inten > 0], 98) + 1e-9
    band = {'wall': (900, 4200), 'tower': (500, 2600), 'pyramid': (180, 1400)}.get(sim['kind'], (400, 3000))

    def burst(lo, hi, dur_s, decay):
        m = int(dur_s * SR); x = rng.standard_normal(m)
        X = np.fft.rfft(x); f = np.fft.rfftfreq(m, 1 / SR); X[(f < lo) | (f > hi)] = 0
        x = np.fft.irfft(X, m); t = np.arange(m) / SR
        return x / (np.abs(x).max() + 1e-9) * np.exp(-t / decay)

    def put(sig, t0, g):
        i = int(t0 * SR); j = min(n, i + len(sig))
        if i < n: out[i:j] += sig[: j - i] * g

    for k, v in enumerate(inten):
        if v < 0.02: continue
        for _ in range(1 + int(min(v, 3) * 3)):   # şiddet arttıkça daha çok parça çarpışması
            put(burst(*band, 0.12, rng.uniform(0.012, 0.04)), k / fps + rng.uniform(0, 1 / fps), min(v, 2.5) * rng.uniform(0.15, 0.4))
    hf = sim['hit_frame'] / fps
    t = np.arange(int(1.6 * SR)) / SR
    thump = np.sin(2 * np.pi * (48 + 30 * np.exp(-t / 0.05)) * t) * np.exp(-t / 0.35)
    put(thump, hf, 1.4); put(burst(60, 900, 1.2, 0.25), hf, 0.7)
    w = burst(200, 2500, 0.9, 0.5)[::-1] * np.linspace(0, 1, int(0.9 * SR)) ** 2   # yaklaşma vınlaması
    put(w, max(0, hf - 0.9), 0.35)
    room = burst(40, 300, dur, 1e9) * 0.025          # oda uğultusu
    out += room
    return out / (np.abs(out).max() + 1e-9) * 0.89


def write_wav(path, x):
    with wave.open(str(path), 'wb') as f:
        f.setnchannels(1); f.setsampwidth(2); f.setframerate(SR); f.writeframes((np.clip(x, -1, 1) * 32767).astype(np.int16).tobytes())


def main():
    meta = json.loads((OUT / 'meta_upload.json').read_text()); overlays(meta)
    parts = []
    for i in range(meta['n']):
        sim = json.loads((OUT / f'sim_meta_{i}.json').read_text()); dur = sim['frames'] / sim['fps']
        write_wav(OUT / f'sfx_{i}.wav', audio(sim, dur))
        cmd = ['ffmpeg', '-y', '-v', 'error', '-i', str(OUT / f'raw_{i}.mp4'), '-i', str(OUT / f'ov_r{i}.png'), '-i', str(OUT / 'ov_hook.png'),
               '-i', str(OUT / f'sfx_{i}.wav'), '-filter_complex',
               (f"[0][2]overlay=enable='lt(t,2.5)'[h];[h][1]overlay=enable='gte(t,2.5)'[o]" if i == 0 else "[0][1]overlay[o]"),
               '-map', '[o]', '-map', '3:a', '-c:v', 'libx264', '-preset', 'medium', '-crf', '16', '-pix_fmt', 'yuv420p',
               '-c:a', 'aac', '-b:a', '192k', '-ar', '44100', '-shortest', str(OUT / f'part_{i}.mp4')]
        subprocess.run(cmd, check=True); parts.append(OUT / f'part_{i}.mp4')
    (OUT / 'parts.txt').write_text(''.join(f"file '{p.name}'\n" for p in parts))
    subprocess.run(['ffmpeg', '-y', '-v', 'error', '-f', 'concat', '-safe', '0', '-i', str(OUT / 'parts.txt'),
                    '-c:v', 'libx264', '-preset', 'slow', '-crf', '18', '-pix_fmt', 'yuv420p', '-c:a', 'aac', '-b:a', '192k',
                    '-af', 'loudnorm=I=-14:TP=-1.5:LRA=11', str(OUT / 'final.mp4')], check=True)
    print('✓ final.mp4', meta['n'], 'tur')


if __name__ == '__main__':
    main()

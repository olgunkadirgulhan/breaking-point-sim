#!/usr/bin/env python3
"""output/raw.mp4 + sim_meta.json → output/final.mp4: üst yazı (ilk 3.5 sn), kalıcı 'SIMULATION' etiketi + ölçüm,
çarpışma şiddetinden üretilen ses (fizik motorunun her karesindeki yavaşlamalardan)."""
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


def overlays(meta):
    hook = Image.new('RGBA', (W, H), (0, 0, 0, 0)); d = ImageDraw.Draw(hook)
    a, vs, b = meta['hook']
    text_shadow(hook, (W // 2, 300), a, fit(d, a, 104, W - 120), B.WHITE + (255,))
    text_shadow(hook, (W // 2, 402), vs, B.TITLE(70), B.HOT + (255,))
    text_shadow(hook, (W // 2, 502), b, fit(d, b, 104, W - 120), B.WHITE + (255,))
    hook.save(OUT / 'ov_hook.png')
    tag = Image.new('RGBA', (W, H), (0, 0, 0, 0)); d = ImageDraw.Draw(tag)
    d.rounded_rectangle([40, 70, 400, 128], radius=8, fill=B.HOT + (235,))
    d.text((220, 99), '3D PHYSICS SIMULATION', font=B.MONO(26, 700), fill=B.BG + (255,), anchor='mm')
    p = meta['params']
    line = f"BALL {p['ball_mass']:,} kg  ·  0.5x SLOW-MO"   # YouTube arayüzü alttaki ~%25'i kapatır → üstte
    f = B.MONO(28, 600); w = d.textlength(line, font=f)
    d.rounded_rectangle([40, 140, 40 + w + 32, 190], radius=8, fill=(17, 19, 22, 190))
    d.text((56, 165), line, font=f, fill=B.WHITE + (255,), anchor='lm')
    tag.save(OUT / 'ov_tag.png')


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
    out = out / (np.abs(out).max() + 1e-9) * 0.89
    with wave.open(str(OUT / 'sfx.wav'), 'wb') as f:
        f.setnchannels(1); f.setsampwidth(2); f.setframerate(SR); f.writeframes((out * 32767).astype(np.int16).tobytes())


def main():
    meta = json.loads((OUT / 'meta_upload.json').read_text()); sim = json.loads((OUT / 'sim_meta.json').read_text())
    dur = sim['frames'] / sim['fps']
    overlays(meta); audio(sim, dur)
    subprocess.run(['ffmpeg', '-y', '-v', 'error', '-i', str(OUT / 'raw.mp4'), '-i', str(OUT / 'ov_hook.png'), '-i', str(OUT / 'ov_tag.png'),
                    '-i', str(OUT / 'sfx.wav'), '-filter_complex',
                    "[0][1]overlay=enable='lt(t,3.5)'[a];[a][2]overlay[v]", '-map', '[v]', '-map', '3:a',
                    '-c:v', 'libx264', '-preset', 'slow', '-crf', '18', '-pix_fmt', 'yuv420p', '-c:a', 'aac', '-b:a', '192k',
                    '-af', 'loudnorm=I=-14:TP=-1.5:LRA=11', '-shortest', str(OUT / 'final.mp4')], check=True)
    print('✓ final.mp4', round(dur, 1), 's')


if __name__ == '__main__':
    main()

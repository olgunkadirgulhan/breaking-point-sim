#!/usr/bin/env python3
"""output/params.json'u Kaggle GPU'da render et → output/raw.mp4 + output/sim_meta.json
KAGGLE_API_TOKEN ortam değişkeni gerekir. Önce P100 (sıra beklemez), sırada kalırsa T4'e geçer."""
import base64, json, os, shutil, subprocess, sys, time
from pathlib import Path

HERE = Path(__file__).resolve().parent
OUT = HERE / 'output'
USER = os.environ.get('KAGGLE_USER') or 'olgunkadirglhan'
SLUG = 'bps-render'
BLENDER = 'https://download.blender.org/release/Blender4.5/blender-4.5.14-linux-x64.tar.xz'

RUN = r'''
import base64, glob, json, os, subprocess, time
W = '/kaggle/working'
open('/tmp/scene.py', 'wb').write(base64.b64decode('{SCENE}'))
R = json.loads(base64.b64decode('{PARAMS}'))
t = time.time()
subprocess.run('curl -sSfL -A "Mozilla/5.0" {BLENDER} | tar -xJ -C /tmp', shell=True, check=True)
print('blender indi', round(time.time() - t), 's', flush=True)
B = glob.glob('/tmp/blender-*/blender')[0]
st = []
for i, P in enumerate(R):
    json.dump(P, open('/tmp/p.json', 'w')); o = f'/tmp/r{i}'; t = time.time()
    p = subprocess.run([B, '-b', '--factory-startup', '-P', '/tmp/scene.py', '--', '/tmp/p.json', o], capture_output=True, text=True)
    n = len(glob.glob(o + '/f_*.jpg')); dt = round(time.time() - t)
    print(f'tur {i + 1}/{len(R)} {P["label"]}: {n} kare, {dt} s ({dt / max(n, 1):.1f} s/kare) rc {p.returncode}', flush=True)
    for l in p.stdout.splitlines():
        if l.startswith('DEVICES') and i == 0 or 'Error' in l: print(l)
    if p.returncode: print(p.stderr[-2000:])
    subprocess.run(f'ffmpeg -y -v error -framerate 30 -i {o}/f_%04d.jpg -c:v libx264 -preset slow -crf 14 -pix_fmt yuv420p {W}/raw_{i}.mp4', shell=True)
    os.system(f'cp {o}/meta.json {W}/sim_meta_{i}.json')
    st.append({'frames': n, 'rc': p.returncode, 'render_s': dt})
json.dump(st, open(W + '/status.json', 'w'))
'''


def kg(*a, check=True):
    r = subprocess.run(['kaggle', *a], capture_output=True, text=True)
    if check and r.returncode: sys.exit(f'kaggle {a[0]} {a[1]}: {r.stdout[-500:]} {r.stderr[-500:]}')
    return (r.stdout + r.stderr).strip()


def push(shape):
    d = Path('/tmp/bps_kernel'); shutil.rmtree(d, ignore_errors=True); d.mkdir()
    code = RUN.replace('{SCENE}', base64.b64encode((HERE / 'sims' / 'scene.py').read_bytes()).decode()) \
              .replace('{PARAMS}', base64.b64encode((OUT / 'rounds.json').read_bytes()).decode()).replace('{BLENDER}', BLENDER)
    (d / 'run.py').write_text(code)
    (d / 'kernel-metadata.json').write_text(json.dumps({
        'id': f'{USER}/{SLUG}', 'title': SLUG, 'code_file': 'run.py', 'language': 'python', 'kernel_type': 'script',
        'is_private': True, 'enable_gpu': True, 'enable_internet': True, 'machine_shape': shape,
        'dataset_sources': [], 'competition_sources': [], 'kernel_sources': []}))
    print(kg('kernels', 'push', '-p', str(d)), flush=True)


def status():
    s = kg('kernels', 'status', f'{USER}/{SLUG}', check=False)
    for k in ('COMPLETE', 'ERROR', 'CANCEL', 'RUNNING', 'QUEUED'):
        if k in s.upper(): return k
    return s[-80:]


def main():
    push('NvidiaTeslaP100')
    t0 = time.time(); started = False
    while True:
        time.sleep(30); s = status()
        if s == 'RUNNING' and not started: started = True; print(f'başladı ({round(time.time() - t0)} s sırada)', flush=True)
        if s == 'QUEUED' and time.time() - t0 > 25 * 60:
            print('P100 sırası uzun → T4', flush=True); push('NvidiaTeslaT4'); t0 = time.time()
        if s in ('COMPLETE', 'ERROR', 'CANCEL'): break
        if time.time() - t0 > 5.2 * 3600: sys.exit('kaggle zaman aşımı')
    print('durum', s, round((time.time() - t0) / 60), 'dk', flush=True)
    for i in range(5):
        r = subprocess.run(['kaggle', 'kernels', 'output', f'{USER}/{SLUG}', '-p', str(OUT), '-o'], capture_output=True, text=True)
        if (OUT / 'status.json').exists(): break
        time.sleep(20)
    log = next(OUT.glob('*.log'), None)
    if log:
        try:
            for x in json.loads(log.read_text()):
                l = x.get('data', '').rstrip()
                if l and 'Warning' not in l and not l.startswith(('Fra:', 'Saved:')): print('  |', l[:300])
        except Exception: pass
    if s != 'COMPLETE' or not (OUT / 'status.json').exists(): sys.exit('render başarısız')
    st = json.loads((OUT / 'status.json').read_text()); R = json.loads((OUT / 'rounds.json').read_text())
    print('kaggle:', st)
    if len(st) < len(R) or any(x['rc'] or x['frames'] < r['frames'] for x, r in zip(st, R)): sys.exit('eksik kare')


if __name__ == '__main__':
    main()

#!/usr/bin/env python3
"""output/params.json'u Kaggle GPU'da render et → output/raw.mp4 + output/sim_meta.json
KAGGLE_API_TOKEN ortam değişkeni gerekir. Önce P100 (sıra beklemez), sırada kalırsa T4'e geçer."""
import base64, json, os, shutil, subprocess, sys, time
from pathlib import Path

HERE = Path(__file__).resolve().parent
OUT = HERE / 'output'
USER = os.environ.get('KAGGLE_USER', 'orkunburakglhan')
SLUG = 'bps-render'
BLENDER = 'https://download.blender.org/release/Blender4.5/blender-4.5.14-linux-x64.tar.xz'

RUN = r'''
import base64, glob, json, os, subprocess, time
W = '/kaggle/working'
open('/tmp/scene.py', 'wb').write(base64.b64decode('{SCENE}'))
open('/tmp/params.json', 'wb').write(base64.b64decode('{PARAMS}'))
t = time.time()
subprocess.run('curl -sSfL -A "Mozilla/5.0" {BLENDER} | tar -xJ -C /tmp', shell=True, check=True)
print('blender indi', round(time.time() - t), 's', flush=True)
B = glob.glob('/tmp/blender-*/blender')[0]
t = time.time()
p = subprocess.run([B, '-b', '--factory-startup', '-P', '/tmp/scene.py', '--', '/tmp/params.json', '/tmp/out'], capture_output=True, text=True)
print('render', round(time.time() - t), 's rc', p.returncode, flush=True)
for l in p.stdout.splitlines():
    if l.startswith(('DEVICES', 'META')) or 'Error' in l: print(l)
print(p.stderr[-3000:])
n = len(glob.glob('/tmp/out/f_*.jpg')); print('kare', n)
subprocess.run('ffmpeg -y -v error -framerate 30 -i /tmp/out/f_%04d.jpg -c:v libx264 -preset slow -crf 14 -pix_fmt yuv420p ' + W + '/raw.mp4', shell=True)
os.system('cp /tmp/out/meta.json ' + W + '/sim_meta.json')
json.dump({'frames': n, 'rc': p.returncode, 'render_s': round(time.time() - t)}, open(W + '/status.json', 'w'))
'''


def kg(*a, check=True):
    r = subprocess.run(['kaggle', *a], capture_output=True, text=True)
    if check and r.returncode: sys.exit(f'kaggle {a[0]} {a[1]}: {r.stdout[-500:]} {r.stderr[-500:]}')
    return (r.stdout + r.stderr).strip()


def push(shape):
    d = Path('/tmp/bps_kernel'); shutil.rmtree(d, ignore_errors=True); d.mkdir()
    code = RUN.replace('{SCENE}', base64.b64encode((HERE / 'sims' / 'scene.py').read_bytes()).decode()) \
              .replace('{PARAMS}', base64.b64encode((OUT / 'params.json').read_bytes()).decode()).replace('{BLENDER}', BLENDER)
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
        if time.time() - t0 > 4.5 * 3600: sys.exit('kaggle zaman aşımı')
    print('durum', s, round((time.time() - t0) / 60), 'dk', flush=True)
    for i in range(5):
        r = subprocess.run(['kaggle', 'kernels', 'output', f'{USER}/{SLUG}', '-p', str(OUT), '-o'], capture_output=True, text=True)
        if (OUT / 'raw.mp4').exists(): break
        time.sleep(20)
    log = next(OUT.glob('*.log'), None)
    if log:
        try:
            for x in json.loads(log.read_text()):
                l = x.get('data', '').rstrip()
                if l and 'Warning' not in l and not l.startswith(('Fra:', 'Saved:')): print('  |', l[:300])
        except Exception: pass
    if s != 'COMPLETE' or not (OUT / 'raw.mp4').exists(): sys.exit('render başarısız')
    st = json.loads((OUT / 'status.json').read_text()); print('kaggle:', st)
    if st['rc'] or st['frames'] < 300: sys.exit('eksik kare')


if __name__ == '__main__':
    main()

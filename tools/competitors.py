#!/usr/bin/env python3
"""Rakip analizi: fizik simülasyonu Shorts'ları (son 90 gün) → süre, izlenme, kanal, başlık.
Çıktı: records/competitors.json + özet (stdout). Kota: arama başına 100 birim."""
import json, os, re, sys
from collections import defaultdict
from datetime import datetime, timedelta, timezone
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from upload import yt

QUERIES = ['physics simulation', 'blender physics simulation', 'destruction simulation', 'hydraulic press simulation',
           'satisfying physics', 'softbody simulation', 'ball vs wall simulation', 'car crash simulation beamng',
           'domino simulation', 'what happens if simulation 3d']


def dur_s(iso):
    m = re.fullmatch(r'P(?:(\d+)D)?T?(?:(\d+)H)?(?:(\d+)M)?(?:(\d+)S)?', iso or '')
    if not m: return 0
    d, h, mi, s = (int(x or 0) for x in m.groups())
    return d * 86400 + h * 3600 + mi * 60 + s


def main():
    api = yt(); since = (datetime.now(timezone.utc) - timedelta(days=90)).strftime('%Y-%m-%dT%H:%M:%SZ')
    ids = {}
    for q in QUERIES:
        r = api.search().list(part='id', q=q, type='video', videoDuration='short', order='viewCount', publishedAfter=since,
                              maxResults=50, relevanceLanguage='en', regionCode='US').execute()
        for it in r.get('items', []): ids.setdefault(it['id']['videoId'], q)
    vids = []
    idl = list(ids)
    for i in range(0, len(idl), 50):
        r = api.videos().list(part='snippet,contentDetails,statistics', id=','.join(idl[i:i + 50])).execute()
        for v in r['items']:
            vids.append(dict(id=v['id'], q=ids[v['id']], title=v['snippet']['title'], channel=v['snippet']['channelTitle'],
                             cid=v['snippet']['channelId'], published=v['snippet']['publishedAt'][:10],
                             dur=dur_s(v['contentDetails']['duration']), views=int(v['statistics'].get('viewCount', 0)),
                             likes=int(v['statistics'].get('likeCount', 0)), comments=int(v['statistics'].get('commentCount', 0))))
    vids.sort(key=lambda x: -x['views'])
    Path('records').mkdir(exist_ok=True)
    Path('records/competitors.json').write_text(json.dumps(vids, indent=1, ensure_ascii=False))
    sh = [v for v in vids if v['dur'] <= 180]
    print(f'{len(sh)} video (≤3 dk), son 90 gün')
    buckets = defaultdict(list)
    for v in sh:
        b = '≤10s' if v['dur'] <= 10 else '11-20s' if v['dur'] <= 20 else '21-30s' if v['dur'] <= 30 else '31-45s' if v['dur'] <= 45 else '46-60s' if v['dur'] <= 60 else '61s+'
        buckets[b].append(v['views'])
    print('\nSÜRE → video sayısı, medyan izlenme, en iyi')
    for b in ['≤10s', '11-20s', '21-30s', '31-45s', '46-60s', '61s+']:
        x = sorted(buckets[b])
        if x: print(f'  {b:7} {len(x):4}  medyan {x[len(x) // 2]:>11,}  max {x[-1]:>13,}')
    top = sh[:40]
    print('\nEN ÇOK İZLENEN 40:')
    for v in top:
        print(f"  {v['views']:>12,}  {v['dur']:>3}s  {v['channel'][:22]:22}  {v['title'][:80]}")
    ch = defaultdict(lambda: [0, 0])
    for v in sh: ch[v['channel']][0] += v['views']; ch[v['channel']][1] += 1
    print('\nKANALLAR (toplam izlenme, video):')
    for c, (s, n) in sorted(ch.items(), key=lambda kv: -kv[1][0])[:20]:
        print(f'  {s:>13,}  {n:3}  {c}')


if __name__ == '__main__':
    main()

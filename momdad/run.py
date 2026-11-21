#!/usr/bin/env python3
"""Mom vs Dad Toons: pick 3 situations -> render -> upload as a scheduled Short.

  python momdad/run.py              # pick + render + upload
  python momdad/run.py --dry-run    # pick + render, no upload
Lead situation (the one in the title) is not reused as lead for 40 videos; the other two rounds are fresh for 6 videos.
"""
import json, os, random, sys
from datetime import datetime, timedelta, timezone
from pathlib import Path

HERE = Path(__file__).resolve().parent
ROOT = HERE.parent
sys.path.insert(0, str(HERE))
import engine
from situations import SITS

OUT = ROOT / 'output'
HIST = ROOT / 'records' / 'momdad_history.json'
SLOTS = (18, 21)   # UTC = New York 13:00 / 16:00 (Paw data: 18-20 UTC best)

TITLES = [
    'Mom vs Dad When {t} 😂',
    'When {t}: Mom vs Dad 😂',
    'Mom vs Dad: {t} (Who Did It Better?)',
    'How Mom vs Dad React When {t} 😂',
]


def pick(hist, rnd):
    leads = [h['sits'][0] for h in hist[-40:]]
    recent = {k for h in hist[-6:] for k in h['sits']}
    keys = list(SITS)
    fresh_leads = [k for k in keys if k not in leads and k not in recent]
    lead = rnd.choice(fresh_leads or [k for k in keys if k not in recent] or keys)
    rest = [k for k in keys if k != lead and k not in recent]
    if len(rest) < 2: rest = [k for k in keys if k != lead]
    # avoid same room three times in a row
    rnd.shuffle(rest)
    a = rest[0]; b = next((k for k in rest[1:] if not (SITS[k]['room'] == SITS[a]['room'] == SITS[lead]['room'])), rest[1])
    return [lead, a, b]


def meta(keys, hist, rnd):
    lead = SITS[keys[0]]
    used = {h['title'] for h in hist}
    tpls = TITLES[:]; rnd.shuffle(tpls)
    title = next((t.format(t=lead['title']) for t in tpls if t.format(t=lead['title']) not in used), tpls[0].format(t=lead['title']))
    rounds = '\n'.join(f'Round {i + 1}: {SITS[k]["cap"].capitalize()}' for i, k in enumerate(keys))
    desc = (f'Mom vs Dad: who handles it better? 😂\n\n{rounds}\n\n'
            'Comment 1 for Mom or 2 for Dad 👇\nNew Mom vs Dad episode every day.\n\n'
            'Animated comedy sketch. All characters are fictional.\n'
            'Make your own animated video, 3 free: https://fennecvideo.com\n\n'
            '#momvsdad #funny #animation #parenting #shorts')
    tags = ['mom vs dad', 'mom vs dad animation', 'funny animation', 'parenting humor', 'family comedy', 'cartoon',
            'animated comedy', 'shorts', 'funny shorts', lead['title'].lower()]
    return title, desc, tags


def publish_at(hist):
    now = datetime.now(timezone.utc); used = {h['publish_at'] for h in hist}
    for day in (0, 1, 2):
        for hh in SLOTS:
            t = (now + timedelta(days=day)).replace(hour=hh, minute=0, second=0, microsecond=0)
            ts = t.strftime('%Y-%m-%dT%H:%M:%SZ')
            if t >= now + timedelta(minutes=25) and ts not in used: return ts
    return (now + timedelta(minutes=30)).strftime('%Y-%m-%dT%H:%M:%SZ')


def slot_due(hist):
    """For scheduled runs: is there a slot in the next 24 h that has no video yet? (keeps 2/day, no backlog)"""
    now = datetime.now(timezone.utc); used = {h['publish_at'] for h in hist}
    for day in (0, 1):
        for hh in SLOTS:
            t = (now + timedelta(days=day)).replace(hour=hh, minute=0, second=0, microsecond=0)
            if now + timedelta(minutes=25) <= t <= now + timedelta(hours=10) and t.strftime('%Y-%m-%dT%H:%M:%SZ') not in used:
                return True
    return False


def yt():
    from google.oauth2.credentials import Credentials
    from googleapiclient.discovery import build
    c = Credentials(None, refresh_token=os.environ['YT_REFRESH_TOKEN'], token_uri='https://oauth2.googleapis.com/token',
                    client_id=os.environ['YT_CLIENT_ID'], client_secret=os.environ['YT_CLIENT_SECRET'])
    return build('youtube', 'v3', credentials=c, cache_discovery=False)


def main():
    dry = '--dry-run' in sys.argv
    hist = json.loads(HIST.read_text()) if HIST.exists() else []
    if '--auto' in sys.argv and not slot_due(hist):
        print('no slot due in the next 10 h: skip'); return
    rnd = random.Random()
    keys = pick(hist, rnd)
    seed = rnd.randrange(10 ** 6)
    plan = engine.make_plan(keys, seed)
    title, desc, tags = meta(keys, hist, rnd)
    print('plan:', keys, '|', title)
    mp4 = str(OUT / 'final.mp4')
    engine.render(plan, mp4, procs=os.cpu_count())
    if dry:
        print('DRY: rendered', mp4); return
    from googleapiclient.http import MediaFileUpload
    api = yt()
    ch = api.channels().list(part='snippet', mine=True).execute()['items'][0]
    if os.environ.get('YT_CHANNEL_ID') and ch['id'] != os.environ['YT_CHANNEL_ID']: sys.exit('wrong channel: ' + ch['snippet']['title'])
    pa = publish_at(hist)
    body = {'snippet': {'title': title[:100], 'description': desc, 'tags': tags, 'categoryId': '23',
                        'defaultLanguage': 'en', 'defaultAudioLanguage': 'en'},
            'status': {'privacyStatus': 'private', 'publishAt': pa, 'selfDeclaredMadeForKids': False,
                       'containsSyntheticMedia': False}}   # obvious cartoon, nothing realistic
    import time
    for attempt in range(3):
        try:
            vid = api.videos().insert(part='snippet,status', body=body, media_body=MediaFileUpload(mp4, resumable=True)).execute()['id']
            break
        except Exception as e:
            print('upload retry', attempt, e); time.sleep(20)
    else:
        sys.exit('upload failed')
    hist.append(dict(sits=keys, seed=seed, title=title, video=vid, publish_at=pa, date=datetime.now(timezone.utc).strftime('%Y-%m-%d')))
    HIST.parent.mkdir(exist_ok=True); HIST.write_text(json.dumps(hist, indent=1))
    print(f'✓ https://youtube.com/shorts/{vid}  (publish {pa})  {title}')


if __name__ == '__main__':
    main()

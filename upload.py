#!/usr/bin/env python3
"""output/final.mp4 → YouTube (Short). Sentetik içerik işareti açık, ABD akşamına zamanlı, geçmişe kaydedilir.
python upload.py [--dry-run]"""
import json, os, sys
from datetime import datetime, timedelta, timezone
from pathlib import Path

HERE = Path(__file__).resolve().parent
OUT = HERE / 'output'
HIST = HERE / 'records' / 'history.json'


def yt():
    from google.oauth2.credentials import Credentials
    from googleapiclient.discovery import build
    c = Credentials(None, refresh_token=os.environ['YT_REFRESH_TOKEN'], token_uri='https://oauth2.googleapis.com/token',
                    client_id=os.environ['YT_CLIENT_ID'], client_secret=os.environ['YT_CLIENT_SECRET'])
    return build('youtube', 'v3', credentials=c, cache_discovery=False)


SLOTS = (17, 23)   # UTC: ABD doğu 13:00 ve 19:00 (günde 2)


def publish_at(hist):
    """bugünün boş ABD saat dilimi; ikisi de geçtiyse/doluysa 30 dk sonra"""
    now = datetime.now(timezone.utc); used = {h['publish_at'] for h in hist}
    for day in (0, 1):
        for h in SLOTS:
            t = (now + timedelta(days=day)).replace(hour=h, minute=0, second=0, microsecond=0)
            ts = t.strftime('%Y-%m-%dT%H:%M:%SZ')
            if t >= now + timedelta(minutes=20) and ts not in used: return ts
    return (now + timedelta(minutes=30)).strftime('%Y-%m-%dT%H:%M:%SZ')


def main():
    m = json.loads((OUT / 'meta_upload.json').read_text())
    hist = json.loads(HIST.read_text()) if HIST.exists() else []
    if any(h['key'] == m['key'] for h in hist): sys.exit('bu birleşim zaten yüklendi')
    if '--dry-run' in sys.argv:
        print('DRY:', m['title']); return
    from googleapiclient.http import MediaFileUpload
    api = yt(); ch = api.channels().list(part='snippet', mine=True).execute()['items'][0]
    if ch['id'] != os.environ.get('YT_CHANNEL_ID', ch['id']): sys.exit('yanlış kanal: ' + ch['snippet']['title'])
    pa = publish_at(hist)
    body = {'snippet': {'title': m['title'][:100], 'description': m['description'][:4900], 'tags': m['tags'], 'categoryId': '28',
                        'defaultLanguage': 'en', 'defaultAudioLanguage': 'en'},
            'status': {'privacyStatus': 'private', 'publishAt': pa, 'selfDeclaredMadeForKids': False,
                       'containsSyntheticMedia': True}}     # gerçekçi görünen sim → "değiştirilmiş/sentetik" etiketi
    vid = api.videos().insert(part='snippet,status', body=body, media_body=MediaFileUpload(str(OUT / 'final.mp4'), resumable=True)).execute()['id']
    hist.append(dict(key=m['key'], series=m.get('series'), kind=m['kind'], n=m['n'], title=m['title'], video=vid, publish_at=pa,
                     date=datetime.now(timezone.utc).strftime('%Y-%m-%d'), labels=m.get('labels')))
    HIST.write_text(json.dumps(hist, indent=1))
    print(f"✓ https://youtube.com/shorts/{vid}  (yayın {pa})  {m['title']}")


if __name__ == '__main__':
    main()

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


def publish_at():
    """ABD doğu yakası 18:00 (22:00 UTC); geçtiyse 30 dk sonra"""
    now = datetime.now(timezone.utc); t = now.replace(hour=22, minute=0, second=0, microsecond=0)
    if t < now + timedelta(minutes=20): t = now + timedelta(minutes=30)
    return t.strftime('%Y-%m-%dT%H:%M:%SZ')


def main():
    m = json.loads((OUT / 'meta_upload.json').read_text())
    hist = json.loads(HIST.read_text()) if HIST.exists() else []
    if any(h['key'] == m['key'] for h in hist): sys.exit('bu birleşim zaten yüklendi')
    if '--dry-run' in sys.argv:
        print('DRY:', m['title']); return
    from googleapiclient.http import MediaFileUpload
    api = yt(); ch = api.channels().list(part='snippet', mine=True).execute()['items'][0]
    if ch['id'] != os.environ.get('YT_CHANNEL_ID', ch['id']): sys.exit('yanlış kanal: ' + ch['snippet']['title'])
    pa = publish_at()
    body = {'snippet': {'title': m['title'][:100], 'description': m['description'][:4900], 'tags': m['tags'], 'categoryId': '28',
                        'defaultLanguage': 'en', 'defaultAudioLanguage': 'en'},
            'status': {'privacyStatus': 'private', 'publishAt': pa, 'selfDeclaredMadeForKids': False,
                       'containsSyntheticMedia': True}}     # gerçekçi görünen sim → "değiştirilmiş/sentetik" etiketi
    vid = api.videos().insert(part='snippet,status', body=body, media_body=MediaFileUpload(str(OUT / 'final.mp4'), resumable=True)).execute()['id']
    hist.append(dict(key=m['key'], kind=m['kind'], n=m['n'], title=m['title'], video=vid, publish_at=pa,
                     date=datetime.now(timezone.utc).strftime('%Y-%m-%d'), params=m['params']))
    HIST.write_text(json.dumps(hist, indent=1))
    print(f"✓ https://youtube.com/shorts/{vid}  (yayın {pa})  {m['title']}")


if __name__ == '__main__':
    main()

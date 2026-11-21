#!/usr/bin/env python3
"""Mom vs Dad Toons channel identity: banner + profile picture + description.  python momdad/brand_md.py [--apply]"""
import os, sys
from pathlib import Path
from PIL import Image, ImageDraw
HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
import engine as E

A = HERE.parent / 'assets' / 'momdad'
DESCRIPTION = ("Mom vs Dad: who handles it better? 😂\n\n"
               "Short 2D cartoon sketches about everyday family moments. The kid says something, then Mom handles it and Dad handles it. "
               "You vote: 1 for Mom, 2 for Dad.\n\nNew episodes every day. All characters are fictional; everything is animated in code.")
KEYWORDS = ['mom vs dad', 'mom vs dad animation', 'funny animation', 'family comedy', 'parenting humor', 'cartoon', 'animated shorts']


def scene(w, h, seed, people):
    E.SC = 1.3
    img = E.room_img('living', seed).resize((E.P(E.W), E.P(E.H)))
    d = ImageDraw.Draw(img)
    fam = E.family(seed)
    for who, x, o in people:
        po = E.base_pose(0.5, who); po.update(o); E.person(d, fam[who], x, E.GY, po)
    return img, d


def banner():
    A.mkdir(parents=True, exist_ok=True)
    img, d = scene(0, 0, 11, [('mom', 300, dict(la=(150, 0), mouth='grin', eyes='happy')), ('kid', 540, dict(mouth='grin', eyes='happy', la=(150, 10), ra=(150, 10))),
                              ('dad', 780, dict(ra=(150, 0), mouth='grin'))])
    small = img.resize((E.W, E.H), Image.LANCZOS)
    bw, bh = 2560, 1440
    bg = Image.new('RGB', (bw, bh), (240, 232, 252)); dd = ImageDraw.Draw(bg)
    dd.rectangle([0, 960, bw, bh], fill=(200, 150, 110))
    fam = small.crop((60, 620, 1020, 1540)); fam = fam.resize((int(fam.width * 430 / fam.height), 430), Image.LANCZOS)
    bg.paste(fam, (bw // 2 + 773 - fam.width - 10, 515))
    def txt(t, x, y, size, col):
        f = E.font(size); dd.text((x, y), t, font=f, fill=col, stroke_width=size // 9, stroke_fill=E.DARK)
    txt('MOM vs DAD', 540, 560, 170, (255, 230, 80))
    txt('TOONS', 560, 760, 110, (255, 255, 255))
    for i, (col, t) in enumerate(((E.MOMC, '1 = MOM'), (E.DADC, '2 = DAD'))):
        x0 = 960 + i * 250
        dd.rounded_rectangle([x0, 790, x0 + 230, 870], radius=40, fill=col, outline=E.DARK, width=6)
        f = E.font(48); tw = f.getlength(t); dd.text((x0 + 115 - tw / 2, 800), t, font=f, fill=(255, 255, 255))
    bg.save(A / 'banner_2560x1440.png')


def profile():
    A.mkdir(parents=True, exist_ok=True)
    img = Image.new('RGB', (E.P(800), E.P(800)), (255, 230, 80)); d = ImageDraw.Draw(img)
    d.ellipse([E.P(-200), E.P(400), E.P(400), E.P(1000)], fill=E.MOMC); d.ellipse([E.P(400), E.P(400), E.P(1000), E.P(1000)], fill=E.DADC)
    fam = E.family(11); E.SC = 1.0
    E.person(d, fam['mom'], 250, 1060, dict(E.base_pose(0.5, 'mom'), mouth='grin', eyes='happy'))
    E.person(d, fam['dad'], 560, 1060, dict(E.base_pose(0.5, 'dad'), mouth='grin'))
    E.stroke_text(d, 'MOM vs DAD', 400, 140, 110, E.WHITE)
    img.resize((800, 800), Image.LANCZOS).save(A / 'profile_800x800.png')


def apply():
    from googleapiclient.http import MediaFileUpload
    from google.oauth2.credentials import Credentials
    from googleapiclient.discovery import build
    c = Credentials(None, refresh_token=os.environ['YT_REFRESH_TOKEN'], token_uri='https://oauth2.googleapis.com/token',
                    client_id=os.environ['YT_CLIENT_ID'], client_secret=os.environ['YT_CLIENT_SECRET'])
    api = build('youtube', 'v3', credentials=c, cache_discovery=False)
    ch = api.channels().list(part='snippet,brandingSettings', mine=True).execute()['items'][0]
    print('channel:', ch['snippet']['title'])
    url = api.channelBanners().insert(media_body=MediaFileUpload(str(A / 'banner_2560x1440.png'), mimetype='image/png')).execute()['url']
    b = ch.get('brandingSettings', {}); b.setdefault('channel', {})
    b['channel'].update(description=DESCRIPTION, keywords=' '.join(f'"{k}"' if ' ' in k else k for k in KEYWORDS), defaultLanguage='en', country='US')
    b.setdefault('image', {})['bannerExternalUrl'] = url; b.pop('hints', None)
    api.channels().update(part='brandingSettings', body={'id': ch['id'], 'brandingSettings': b}).execute()
    print('✓ banner + description')


if __name__ == '__main__':
    banner(); profile(); print('✓ images in', A)
    if '--apply' in sys.argv: apply()

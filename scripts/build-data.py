"""Build data/cameras.json from open sources.
Sources: OpenStreetMap (ODbL) contact:webcam / webcam tags, NYC DOT (open data), Caltrans CWWP2 (open data).
Usage: bash scripts/fetch-raw.sh && python3 scripts/build-data.py"""
import json, glob, re, hashlib, os, sys, collections
from urllib.parse import urlparse

RAW = sys.argv[1] if len(sys.argv) > 1 else 'raw'
out, seen = [], set()

SKIP = {'pioupiou.com', 'balisemeteo.com'}  # wind sensors, not cameras
SCENIC = ('foto-webcam', 'feratel', 'skaping', 'bergfex', 'webcam-hd', 'youtube', 'youtu.be',
          'webcams.travel', 'windy.com', 'earthcam', 'roundshot', 'panomax', 'livecam', 'webcamera')
TRAFFIC = ('traffic', '511', 'dot.', 'roads', 'dgt.es', 'asfinag', 'vegvesen', 'verkehr',
           'tripcheck', 'informo', 'chart.maryland', 'eot.state', 'mto.gov', 'inforoute', 'utinform',
           'movilidad', 'ristmikud', 'travelwise', 'wsdot', 'ctroads', 'trafikverket', 'highway')

def h(s): return hashlib.sha1(s.encode()).hexdigest()[:10]
def is_img(u): return bool(re.search(r'\.(jpe?g|png|gif|webp)(\?|$)', u or '', re.I))
def add(cid, lat, lon, name, cat, src, url, img=None, stream=None):
    key = (url or '').split('?')[0].lower().rstrip('/')
    if not url or key in seen: return
    if not (-90 <= lat <= 90 and -180 <= lon <= 180): return
    seen.add(key)
    out.append({'id': cid, 'lat': round(lat, 5), 'lon': round(lon, 5), 'name': (name or '').strip()[:90],
                'cat': cat, 'src': src, 'url': url, 'img': img, 'stream': stream})

for c in json.load(open(f'{RAW}/nyc.json')):
    if str(c.get('isOnline')) != 'true': continue
    add('nyc-' + c['id'][:8], float(c['latitude']), float(c['longitude']),
        c['name'] + ', ' + c.get('area', ''), 'traffic', 'NYC DOT', c['imageUrl'], img=c['imageUrl'])

for f in sorted(glob.glob(f'{RAW}/ct*.json')):
    for row in json.load(open(f))['data']:
        c = row['cctv']
        if c.get('inService') != 'true': continue
        loc, im = c['location'], c['imageData']
        img = im['static'].get('currentImageURL') or None
        name = loc['locationName'].split('--')[-1].strip() + ', ' + (loc.get('nearbyPlace') or loc.get('county') or '')
        add('ct-' + h(img or name), float(loc['latitude']), float(loc['longitude']), name, 'traffic', 'Caltrans',
            img or im.get('streamingVideoURL'), img=img, stream=im.get('streamingVideoURL') or None)

for e in json.load(open(f'{RAW}/osm.json'))['elements']:
    t = e.get('tags', {})
    url = (t.get('contact:webcam') or t.get('webcam') or '').split(';')[0].strip()
    if not url.startswith('http'): continue
    dom = urlparse(url).netloc.lower().replace('www.', '')
    if dom in SKIP: continue
    lat = e.get('lat') or e.get('center', {}).get('lat'); lon = e.get('lon') or e.get('center', {}).get('lon')
    if lat is None: continue
    zone, mm = t.get('surveillance:zone', ''), t.get('man_made', '')
    if mm == 'monitoring_station' or 'usgs' in dom or t.get('monitoring:water_level'): cat = 'water'
    elif any(k in dom for k in SCENIC) or t.get('tourism'): cat = 'scenic'
    elif zone == 'traffic' or any(k in dom for k in TRAFFIC): cat = 'traffic'
    else: cat = 'other'
    name = t.get('name') or t.get('description') or t.get('operator') or dom
    img = url if is_img(url) else (t.get('image') if is_img(t.get('image')) else None)
    add(f"osm-{e['type'][0]}{e['id']}", float(lat), float(lon), name, cat, 'OpenStreetMap', url, img=img)

out.sort(key=lambda c: c['id'])
os.makedirs('data', exist_ok=True)
json.dump(out, open('data/cameras.json', 'w'), separators=(',', ':'), ensure_ascii=False)
print(len(out), dict(collections.Counter(c['cat'] for c in out)), dict(collections.Counter(c['src'] for c in out)),
      'with image:', sum(1 for c in out if c['img']))

# compact client file for the dashboard: [id, lon, lat, name, cat, src, img|0]
C = ['traffic', 'scenic', 'water', 'other']; S = ['OpenStreetMap', 'NYC DOT', 'Caltrans']
os.makedirs('public/data', exist_ok=True)
json.dump({'cats': C, 'srcs': S, 'rows': [[c['id'], c['lon'], c['lat'], c['name'], C.index(c['cat']), S.index(c['src']), c['img'] or 0] for c in out]},
          open('public/data/cams.json', 'w'), separators=(',', ':'), ensure_ascii=False)
print('wrote public/data/cams.json')

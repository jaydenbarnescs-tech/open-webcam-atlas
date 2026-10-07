"""Build the camera index from every open source in scripts/sources.py.
Usage:  python3 scripts/build-data.py            (uses raw/ cache; delete raw/ to refresh)
        WINDY_API_KEY=... python3 scripts/build-data.py   (adds Windy's worldwide network)"""
import json, os, re, sys, collections, time, argparse
from concurrent.futures import ThreadPoolExecutor
import urllib.request
from urllib.parse import urljoin, urlparse, urlsplit, urlunsplit, parse_qsl, urlencode
sys.path.insert(0, os.path.dirname(__file__))
import sources as S

t0 = time.time()
parser = argparse.ArgumentParser()
parser.add_argument('--sources', nargs='+', help='Refresh only these source functions, retaining all other sources')
args = parser.parse_args()
functions = [f for f in S.ALL if not args.sources or f.__name__ in args.sources]
if args.sources and set(args.sources) - {f.__name__ for f in functions}: parser.error('Unknown source function')
all_cams = []
with ThreadPoolExecutor(10) as ex:
    for fn, res in zip(functions, ex.map(lambda f: S._safe(f), functions)):
        print(f'{fn.__name__:12s} {len(res):6d}'); all_cams += res

# ---- a source that returns nothing today (blocked IP, outage) keeps its last good records instead of vanishing
OLD_PATH = 'data/cameras.json'
preserved_ids = set()
if os.path.exists(OLD_PATH):
    old = json.load(open(OLD_PATH)); got = {c['src'] for c in all_cams}
    for src in sorted({c['src'] for c in old} - got - (set() if args.sources else {'OpenStreetMap'})):
        keep = [c for c in old if c['src'] == src]; all_cams += keep
        if args.sources: preserved_ids.update(c['id'] for c in keep)
        print(f'  carried over {len(keep)} cameras from {src} (source returned nothing this run)')

# ---- portals expanded in full by their own source: drop the single OSM pins that point into them
COVERED = {'cam.krk.ru', 'apps.usgs.gov'}
def dom_of(u): return urlparse(u or '').netloc.lower().replace('www.', '').split(':')[0]

# ---- dedupe (same feed url, or same image) and sanity-check coordinates
def feed_key(url):
    # Camera IDs in query strings identify different feeds; only discard cache/tracking parameters.
    p = urlsplit(url)
    query = [(k, v) for k, v in parse_qsl(p.query) if k not in {'_t', 'timestamp', 'cachebust'} and not k.startswith('utm_')]
    return urlunsplit((p.scheme.lower(), p.netloc.lower(), p.path.rstrip('/'), urlencode(sorted(query)), ''))

seen, cams = set(), []
for c in all_cams:
    if c['id'] in preserved_ids:
        cams.append(c)
        continue
    if c['src'] == 'OpenStreetMap' and dom_of(c['url']) in COVERED: continue
    if not (-90 <= c['lat'] <= 90 and -180 <= c['lon'] <= 180) or (c['lat'] == 0 and c['lon'] == 0): continue
    keys = {feed_key(k) for k in (c['url'], c['img']) if k}
    if keys & seen: continue
    seen |= keys; cams.append(c)

# ---- probe link-only pages: find an embeddable page, a YouTube player, an HLS stream or a camera still
PROBE_PATH = os.path.join(S.RAW, 'probe.json')
probe = json.load(open(PROBE_PATH)) if os.path.exists(PROBE_PATH) else {}
# a seller's page (CCTV installer, shop) has several of these and no camera media
SHOP = re.compile(r'add to cart|add-to-cart|buy now|checkout|shopping cart|price list|\bprice\b|купить|цена|корзин|販売|カートに入れる|ご購入|見積', re.I)
IMG_HINT = re.compile(r'(webcam|current|live|cam|snapshot|latest|image)', re.I)

def probe_url(u):
    res = {}
    try:
        req = urllib.request.Request(u, headers={'User-Agent': 'Mozilla/5.0 (compatible; open-webcam-atlas)', 'Accept': 'text/html,image/*'})
        with urllib.request.urlopen(req, timeout=10) as r:
            ct = r.headers.get('Content-Type', ''); final = r.geturl()
            if ct.startswith('image/'): return {'img': final}
            if 'html' not in ct: return res
            xfo = (r.headers.get('X-Frame-Options') or '').lower(); csp = (r.headers.get('Content-Security-Policy') or '').lower()
            body = r.read(400_000).decode('utf-8', 'replace')
        low = body.lower()
        if len(SHOP.findall(low)) >= 3: res['shop'] = True
        fa = re.search(r'frame-ancestors([^;]*)', csp)
        frameable = not xfo and (not fa or '*' in fa.group(1).split())
        if frameable and final.startswith('https://'): res['embed'] = final
        yt = re.search(r'(?:youtube(?:-nocookie)?\.com/embed/|youtube\.com/watch\?v=)([\w-]{11})', body)
        if yt: res['embed'] = f'https://www.youtube-nocookie.com/embed/{yt.group(1)}?autoplay=1&mute=1&playsinline=1'
        m3 = re.search(r'https://[^"\'\s<>]+\.m3u8[^"\'\s<>]*', body)
        if m3: res['stream'] = m3.group(0)
        for m in re.finditer(r'<img[^>]+src=["\']([^"\']+\.(?:jpe?g|png|webp)[^"\']*)["\']', body, re.I):
            src = urljoin(final, html_unescape(m.group(1)))
            if IMG_HINT.search(src) and not re.search(r'logo|icon|banner|sprite|avatar', src, re.I): res['img'] = src; break
        if 'img' not in res:
            og = re.search(r'<meta[^>]+property=["\']og:image["\'][^>]+content=["\']([^"\']+)', body, re.I)
            if og and IMG_HINT.search(og.group(1)) and not re.search(r'logo|icon|share|default', og.group(1), re.I): res['img'] = urljoin(final, og.group(1))
    except Exception:
        pass
    return res

def html_unescape(s): return s.replace('&amp;', '&')

todo = sorted({c['url'] for c in cams if c['id'] not in preserved_ids and c['src'] == 'OpenStreetMap' and not c['img'] and not c['embed'] and c['url'] not in probe})
print('probing', len(todo), 'operator pages...')
with ThreadPoolExecutor(64) as ex:
    for u, r in zip(todo, ex.map(probe_url, todo)): probe[u] = r
json.dump(probe, open(PROBE_PATH, 'w'))
shops = {c['id'] for c in cams if c['id'] not in preserved_ids and c['src'] == 'OpenStreetMap' and (probe.get(c['url']) or {}).get('shop')
         and not (c['img'] or c['embed'] or c['stream'] or c['video'])
         and not any((probe.get(c['url']) or {}).get(k) for k in ('img', 'embed', 'stream'))}
print('dropping', len(shops), 'non-camera (shop) OSM entries')
cams = [c for c in cams if c['id'] not in shops]
for c in cams:
    if c['id'] in preserved_ids: continue
    p = probe.get(c['url'])
    if p and not c['img'] and not c['embed']:
        c['img'] = p.get('img'); c['embed'] = p.get('embed'); c['stream'] = c['stream'] or p.get('stream')

# ---- playback mode: 2 = moving video (stream / clip / player), 1 = live still image, 0 = link only
for c in cams:
    if c['id'] in preserved_ids and c['src'] != 'Windy Webcams': continue
    # Public Windy day players are available even when this camera has no live stream.
    if c['src'] == 'Windy Webcams' and not c.get('embed'):
        c['embed'] = f"https://webcams.windy.com/webcams/public/embed/player/{c['id'].removeprefix('windy-')}/day?autoplay=1&loop=1"
        c['timelapse'] = True
    c['mode'] = 2 if (c['stream'] or c['video'] or c['embed']) else 1 if c['img'] else 0

cams.sort(key=lambda c: c['id'])
os.makedirs('data', exist_ok=True)
json.dump(cams, open('data/cameras.json', 'w'), separators=(',', ':'), ensure_ascii=False)

from compact import write_compact
write_compact(cams)
print(f'\n{len(cams)} cameras from {len({c["src"] for c in cams})} sources in {time.time() - t0:.0f}s')
print('modes:', dict(collections.Counter(c['mode'] for c in cams)), ' cats:', dict(collections.Counter(c['cat'] for c in cams)))
print('countries:', len({c["country"] for c in cams if c["country"]}))

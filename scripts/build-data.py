"""Build the camera index from every open source in scripts/sources.py.
Usage:  python3 scripts/build-data.py            (uses raw/ cache; delete raw/ to refresh)
        WINDY_API_KEY=... python3 scripts/build-data.py   (adds Windy's worldwide network)"""
import json, os, re, sys, collections, time, argparse
from concurrent.futures import ThreadPoolExecutor
import urllib.request
from urllib.parse import urljoin, urlparse, urlsplit, urlunsplit, parse_qsl, urlencode
sys.path.insert(0, os.path.dirname(__file__))
import sources as S
import quality as Q

t0 = time.time()
parser = argparse.ArgumentParser()
parser.add_argument('--sources', nargs='+', help='Refresh only these source functions, retaining all other sources')
parser.add_argument('--clean-only', action='store_true', help='Apply camera quality rules to the existing index without downloading sources')
args = parser.parse_args()
functions = [] if args.clean_only else [f for f in S.ALL if not args.sources or f.__name__ in args.sources]
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
    for src in sorted({c['src'] for c in old} - got - (set() if args.sources or args.clean_only else {'OpenStreetMap'})):
        keep = [c for c in old if c['src'] == src]; all_cams += keep
        if args.sources or args.clean_only: preserved_ids.update(c['id'] for c in keep)
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

def camera_keys(c):
    # Distinct views can share one operator page. Media URLs identify cameras more precisely.
    media = [c.get(k) for k in ('img', 'stream', 'video', 'embed') if c.get(k)]
    return {feed_key(k) for k in (media or [c['url']])}

seen = {key for c in all_cams if c['id'] in preserved_ids for key in camera_keys(c)}
cams = []
for c in all_cams:
    if c['id'] in preserved_ids:
        cams.append(c)
        continue
    if c['src'] == 'OpenStreetMap' and dom_of(c['url']) in COVERED: continue
    if not (-90 <= c['lat'] <= 90 and -180 <= c['lon'] <= 180) or (c['lat'] == 0 and c['lon'] == 0): continue
    keys = camera_keys(c)
    if keys & seen: continue
    seen |= keys; cams.append(c)

# ---- probe link-only pages: find an embeddable page, a YouTube player, an HLS stream or a camera still
PROBE_PATH = os.path.join(S.RAW, 'probe.json')
probe = json.load(open(PROBE_PATH)) if os.path.exists(PROBE_PATH) else {}
def probe_url(u):
    if not Q.public_url(u): return {'quality_version': Q.VERSION, 'excluded': 'non_public_url'}
    try:
        req = urllib.request.Request(u, headers={'User-Agent': S.UA, 'Accept': 'text/html,image/*'})
        with urllib.request.urlopen(req, timeout=10) as r:
            ct = r.headers.get('Content-Type', ''); final = r.geturl()
            if ct.startswith('image/') and Q.camera_image(final, direct=True): return {'quality_version': Q.VERSION, 'img': final}
            if 'html' not in ct: return {'quality_version': Q.VERSION}
            return Q.extract_media(r.read(600_000).decode('utf-8', 'replace'), final)
    except Exception:
        return {'quality_version': Q.VERSION}

todo = sorted({c['url'] for c in cams if c['id'] not in preserved_ids and c['src'] == 'OpenStreetMap' and not c['img'] and not c['embed'] and probe.get(c['url'], {}).get('quality_version') != Q.VERSION})
print('probing', len(todo), 'operator pages...')
with ThreadPoolExecutor(64) as ex:
    for u, r in zip(todo, ex.map(probe_url, todo)): probe[u] = r
json.dump(probe, open(PROBE_PATH, 'w'))
# Admission rules run on EVERY OSM record, including cached and carried-over records.
# Keep an audit of exclusions without retaining unsafe URLs or credential-bearing query strings.
approved, excluded, adjusted = [], [], 0
for c in cams:
    reviewed, reason = Q.review(c, probe.get(c['url']))
    if reviewed is None:
        excluded.append({'id': c['id'], 'name': c['name'], 'reason': reason})
    else:
        approved.append(reviewed)
        adjusted += bool(reason)
cams = approved
os.makedirs('data', exist_ok=True)
audit_path = 'data/excluded-cameras.json'
previous = json.load(open(audit_path)) if os.path.exists(audit_path) else []
audit = {c['id']: c for c in previous + excluded}
for c in cams: audit.pop(c['id'], None)
json.dump(list(audit.values()), open(audit_path, 'w'), ensure_ascii=False, indent=2)
print('quality exclusions:', dict(collections.Counter(c['reason'] for c in excluded)), 'previews corrected:', adjusted)

# ---- playback mode: 2 = moving video (stream / clip / player), 1 = live still image, 0 = link only
for c in cams:
    if c['id'] in preserved_ids and c['src'] != 'Windy Webcams': continue
    # Public Windy day players are available even when this camera has no live stream.
    if c['src'] == 'Windy Webcams' and not c.get('embed'):
        c['embed'] = f"https://webcams.windy.com/webcams/public/embed/player/{c['id'].removeprefix('windy-')}/day?autoplay=1&loop=1"
        c['timelapse'] = True
    c['mode'] = 2 if (c['stream'] or c['video'] or c['embed'] or c.get('frames')) else 1 if c['img'] else 0

cams.sort(key=lambda c: c['id'])
os.makedirs('data', exist_ok=True)
json.dump(cams, open('data/cameras.json', 'w'), separators=(',', ':'), ensure_ascii=False)

from compact import write_compact
write_compact(cams)
print(f'\n{len(cams)} cameras from {len({c["src"] for c in cams})} sources in {time.time() - t0:.0f}s')
print('modes:', dict(collections.Counter(c['mode'] for c in cams)), ' cats:', dict(collections.Counter(c['cat'] for c in cams)))
print('countries:', len({c["country"] for c in cams if c["country"]}))

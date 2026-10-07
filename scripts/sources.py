"""Open camera sources. Each source = fetch (raw JSON/XML text cached in raw/) + parse -> list of camera dicts.

Rules for adding a source: the operator must publish the feed openly (open-data portal or public
traveller site). Never add cameras found by scanning for unsecured devices.

Camera dict: id, lat, lon, name, cat (traffic|scenic|water|weather|other), src (display name),
country (ISO-2), url (operator page or image), img (still), stream (HLS m3u8), video (mp4 clip),
embed (iframe url), refresh (seconds between new stills, if known).
"""
import json, os, re, hashlib, html, time, math
import urllib.request, urllib.error
from concurrent.futures import ThreadPoolExecutor
from urllib.parse import urlparse, quote

UA = 'open-webcam-atlas/0.2 (+https://github.com/jaydenbarnescs-tech/open-webcam-atlas)'
RAW = 'raw'


def get(url, timeout=60, headers=None, binary=False, data=None):
    req = urllib.request.Request(url, data=data, headers={'User-Agent': UA, 'Accept': '*/*', 'Accept-Encoding': 'gzip', **(headers or {})})
    with urllib.request.urlopen(req, timeout=timeout) as r:
        b = r.read()
        if r.headers.get('Content-Encoding') == 'gzip' or b[:2] == b'\x1f\x8b':
            import gzip; b = gzip.decompress(b)
        return b if binary else b.decode('utf-8', 'replace')


def cached(name, url, **kw):
    path = os.path.join(RAW, name)
    if os.path.exists(path) and os.path.getsize(path) > 50:
        return open(path, encoding='utf-8').read()
    txt = get(url, **kw)
    os.makedirs(RAW, exist_ok=True)
    open(path, 'w', encoding='utf-8').write(txt)
    return txt


def h(s): return hashlib.sha1(s.encode()).hexdigest()[:10]
def clean(s): return re.sub(r'\s+', ' ', html.unescape(str(s or ''))).strip()


def cam(id, lat, lon, name, cat, src, country, url, img=None, stream=None, video=None, embed=None, refresh=None):
    return dict(id=id, lat=float(lat), lon=float(lon), name=clean(name)[:100], cat=cat, src=src, country=country,
                url=url, img=img, stream=stream, video=video, embed=embed, refresh=refresh)


# ---------------------------------------------------------------- OpenStreetMap
SKIP_DOMAINS = {'pioupiou.com', 'balisemeteo.com'}
# social/profile pages are never a camera feed (e.g. a CCTV installer's Facebook page)
SOCIAL_DOMAINS = {'facebook.com', 'fb.com', 'instagram.com', 'vk.com', 'linkedin.com', 'twitter.com', 'x.com', 'tiktok.com', 'wa.me'}
SCENIC = ('foto-webcam', 'feratel', 'skaping', 'bergfex', 'webcam-hd', 'youtube', 'youtu.be', 'webcams.travel', 'windy.com',
          'earthcam', 'roundshot', 'panomax', 'livecam', 'webcamera', 'skylinewebcams', 'camstreamer', 'ipcamlive', 'rtsp.me')
TRAFFIC = ('traffic', '511', 'dot.', 'roads', 'dgt.es', 'asfinag', 'vegvesen', 'verkehr', 'tripcheck', 'informo', 'chart.maryland',
           'eot.state', 'mto.gov', 'inforoute', 'utinform', 'movilidad', 'ristmikud', 'travelwise', 'wsdot', 'ctroads', 'trafikverket', 'highway')


def is_img(u): return bool(re.search(r'\.(jpe?g|png|gif|webp)(\?|$)', u or '', re.I))


def youtube_embed(u):
    m = re.search(r'(?:youtube\.com/(?:watch\?v=|live/|embed/)|youtu\.be/)([\w-]{11})', u or '')
    if m: return f'https://www.youtube-nocookie.com/embed/{m.group(1)}?autoplay=1&mute=1&playsinline=1'
    m = re.search(r'youtube\.com/channel/(UC[\w-]{22})', u or '')
    if m: return f'https://www.youtube-nocookie.com/embed/live_stream?channel={m.group(1)}&autoplay=1&mute=1'
    return None


def osm():
    q = '[out:json][timeout:280];(nwr["contact:webcam"];nwr["webcam"];nwr["surveillance:type"="webcam"]["website"];);out center tags;'
    path = os.path.join(RAW, 'osm.json')
    if not (os.path.exists(path) and os.path.getsize(path) > 1000):
        from urllib.parse import urlencode
        for mirror in ('https://overpass-api.de/api/interpreter', 'https://overpass.private.coffee/api/interpreter', 'https://overpass.kumi.systems/api/interpreter'):
            try:
                txt = get(mirror, timeout=300, headers={'Accept': 'application/json'}, data=urlencode({'data': q}).encode())
                if txt.lstrip().startswith('{'): os.makedirs(RAW, exist_ok=True); open(path, 'w').write(txt); break
            except Exception as ex: print('  overpass', mirror, ex)
    txt = open(path).read()
    out = []
    for e in json.loads(txt)['elements']:
        t = e.get('tags', {})
        url = (t.get('contact:webcam') or t.get('webcam') or t.get('website') or '').split(';')[0].strip()
        if not url.startswith('http'): continue
        dom = urlparse(url).netloc.lower().replace('www.', '')
        if dom in SKIP_DOMAINS or any(dom == d or dom.endswith('.' + d) for d in SOCIAL_DOMAINS): continue
        lat = e.get('lat') or e.get('center', {}).get('lat'); lon = e.get('lon') or e.get('center', {}).get('lon')
        if lat is None: continue
        zone, mm = t.get('surveillance:zone', ''), t.get('man_made', '')
        if mm == 'monitoring_station' or 'usgs' in dom or t.get('monitoring:water_level'): cat = 'water'
        elif any(k in dom for k in SCENIC) or t.get('tourism'): cat = 'scenic'
        elif zone == 'traffic' or any(k in dom for k in TRAFFIC): cat = 'traffic'
        elif t.get('monitoring:weather'): cat = 'weather'
        else: cat = 'other'
        name = t.get('name') or t.get('description') or t.get('operator') or dom
        img = url if is_img(url) else (t.get('image') if is_img(t.get('image')) else None)
        out.append(cam(f"osm-{e['type'][0]}{e['id']}", lat, lon, name, cat, 'OpenStreetMap', t.get('addr:country', ''), url,
                       img=img, embed=youtube_embed(url)))
    return out


# ---------------------------------------------------------------- North America
def nyc():
    out = []
    for c in json.loads(cached('nyc.json', 'https://webcams.nyctmc.org/api/cameras')):
        if str(c.get('isOnline')) != 'true': continue
        out.append(cam('nyc-' + c['id'][:8], c['latitude'], c['longitude'], f"{c['name']}, {c.get('area', '')}", 'traffic',
                       'NYC DOT', 'US', c['imageUrl'], img=c['imageUrl'], refresh=2))
    return out


def caltrans():
    out = []
    for d in range(1, 13):
        try: rows = json.loads(cached(f'ct{d:02d}.json', f'https://cwwp2.dot.ca.gov/data/d{d}/cctv/cctvStatusD{d:02d}.json'))['data']
        except Exception as ex: print('  caltrans d', d, ex); continue
        for row in rows:
            c = row['cctv']
            if c.get('inService') != 'true': continue
            loc, im = c['location'], c['imageData']
            img = im['static'].get('currentImageURL') or None
            name = loc['locationName'].split('--')[-1].strip() + ', ' + (loc.get('nearbyPlace') or loc.get('county') or '')
            out.append(cam('ct-' + h(img or name), loc['latitude'], loc['longitude'], name, 'traffic', 'Caltrans', 'US',
                           img or im.get('streamingVideoURL'), img=img, stream=im.get('streamingVideoURL') or None,
                           refresh=int(im['static'].get('currentImageUpdateFrequency')) * 60 if str(im['static'].get('currentImageUpdateFrequency')).isdigit() else 300))
    return out


# Castle Rock / IBI "511" traveller platform — same API on many US states + Canadian provinces.
P511 = {'fl511.com': ('Florida 511', 'US'), '511ga.org': ('Georgia 511', 'US'), 'udottraffic.utah.gov': ('UDOT Traffic', 'US'),
        '511pa.com': ('511PA', 'US'), '511on.ca': ('Ontario 511', 'CA'), 'az511.gov': ('AZ 511', 'US'), '511wi.gov': ('511 Wisconsin', 'US'),
        '511.idaho.gov': ('Idaho 511', 'US'), 'newengland511.org': ('New England 511', 'US'), 'ctroads.org': ('CTroads', 'US'),
        '511.alberta.ca': ('511 Alberta', 'CA'), '511la.org': ('511 Louisiana', 'US'), '511.alaska.gov': ('Alaska 511', 'US'),
        '511in.org': ('INDOT 511', 'US'), '511mn.org': ('511 Minnesota', 'US'), '511.nebraska.gov': ('Nebraska 511', 'US'),
        'nvroads.com': ('NVroads', 'US'), '511ny.org': ('511NY', 'US'), '511sc.org': ('511 South Carolina', 'US'),
        '511.mt.gov': ('Montana 511', 'US'), 'www.511virginia.org': ('511 Virginia', 'US'), 'quebec511.info': ('Québec 511', 'CA'),
        '511.ky.gov': ('GoKY', 'US'), 'www.511nj.org': ('511NJ', 'US'), 'hb.511.idaho.gov': ('Idaho 511', 'US')}


def p511_host(host):
    src, cc = P511[host]
    rows, start = [], 0
    while True:
        q = quote(json.dumps({'columns': [], 'start': start, 'length': 100}))
        d = None
        for attempt in range(4):
            try: d = json.loads(cached(f'p511_{host}_{start}.json', f'https://{host}/List/GetData/Cameras?query={q}&lang=en', timeout=60)); break
            except Exception: time.sleep(2 * (attempt + 1))
        if d is None: print(f'  511 {host}: gave up at start={start}'); break
        page = d.get('data', [])
        rows += page; start += len(page)
        if not page or start >= d.get('recordsTotal', 0): break
    out = []
    for r in rows:
        m = re.search(r'POINT \(([-\d.]+) ([-\d.]+)\)', json.dumps(r.get('latLng') or {}))
        if not m: continue
        lon, lat = float(m.group(1)), float(m.group(2))
        for i, im in enumerate([x for x in r.get('images', []) if not x.get('disabled') and not x.get('blocked')][:4]):
            img = im.get('imageUrl'); img = f'https://{host}{img}' if img and img.startswith('/') else img
            vid = im.get('videoUrl') if im.get('videoUrl') and not im.get('isVideoAuthRequired') and not im.get('videoDisabled') else None
            name = r.get('location') or ' '.join(filter(None, [r.get('roadway'), r.get('direction')]))
            if r.get('city') or r.get('county'): name += f", {r.get('city') or r.get('county')}"
            if i: name += f' (view {i + 1})'
            out.append(cam(f"511-{h(host)}-{r.get('id')}-{i}", lat + i * 0.00002, lon, name, 'traffic', src, cc,
                           img or f"https://{host}/map#Cameras-{r.get('id')}", img=img, stream=vid if vid and vid.endswith('.m3u8') else None))
    return out


def p511():
    out = []
    with ThreadPoolExecutor(12) as ex:
        for host, res in zip(P511, ex.map(lambda x: _safe(p511_host, x), P511)):
            print(f'  511 {host}: {len(res)}'); out += res
    return out


def wsdot():
    out = []
    for m in re.finditer(r'<Placemark id="ID (\d+)"><name><!\[CDATA\[(.*?)\]\]></name>.*?src="([^"]+)".*?<coordinates>([-\d.]+),([-\d.]+)', 
                         cached('wsdot.kml', 'https://www.wsdot.com/Traffic/api/HighwayCameras/kml.aspx'), re.S):
        id_, name, img, lon, lat = m.groups()
        out.append(cam('wsdot-' + id_, lat, lon, name, 'traffic', 'WSDOT', 'US', img, img=img, refresh=120))
    return out


def tripcheck():
    d = json.loads(cached('tripcheck.json', 'https://www.tripcheck.com/Scripts/map/data/cctvinventory.js'))
    out = []
    for f in d['features']:
        a = f['attributes']; img = f"https://tripcheck.com/RoadCams/cams/{a['filename']}"
        out.append(cam(f"or-{a['cameraId']}-{a['publishedImageId']}", a['latitude'], a['longitude'], a['title'], 'traffic', 'ODOT TripCheck', 'US', img, img=img, refresh=300))
    return out


def iowa():
    d = json.loads(cached('iowa.json', 'https://services.arcgis.com/8lRhdTsQyJpO52F1/arcgis/rest/services/Traffic_Cameras_View/FeatureServer/0/query?where=1%3D1&outFields=*&f=json'))
    out = []
    for f in d['features']:
        a = f['attributes']
        if not a.get('ImageURL'): continue
        v = a.get('VideoURL') if a.get('VideoURL') and str(a.get('VideoURL')).endswith('.m3u8') else None
        out.append(cam(f"ia-{a['device_id']}", a['latitude'], a['longitude'], a['Desc_'], 'weather' if a.get('Type') == 'RWIS' else 'traffic',
                       'Iowa DOT', 'US', a['ImageURL'], img=a['ImageURL'], stream=v, refresh=300))
    return out


def drivebc():
    out = []
    for c in json.loads(cached('drivebc.json', 'https://www.drivebc.ca/api/webcams/')):
        if not c.get('is_on') or not c.get('location'): continue
        lon, lat = c['location']['coordinates'][:2]
        img = f"https://images.drivebc.ca/bchighwaycam/pub/cameras/{c['id']}.jpg"
        out.append(cam(f"bc-{c['id']}", lat, lon, f"{c.get('name')}: {c.get('caption', '')}", 'traffic', 'DriveBC', 'CA',
                       f"https://www.drivebc.ca/cameras/{c['id']}", img=img, refresh=int(c.get('update_period_mean') or 600)))
    return out


# ---------------------------------------------------------------- Europe
def tfl():
    out = []
    for c in json.loads(cached('tfl.json', 'https://api.tfl.gov.uk/Place/Type/JamCam')):
        p = {a['key']: a['value'] for a in c['additionalProperties']}
        if p.get('available') != 'true': continue
        out.append(cam('tfl-' + c['id'].split('_')[-1], c['lat'], c['lon'], c['commonName'] + (f" ({p['view']})" if p.get('view') else ''),
                       'traffic', 'TfL JamCams', 'GB', p.get('imageUrl'), img=p.get('imageUrl'), video=p.get('videoUrl'), refresh=300))
    return out


def digitraffic():
    d = json.loads(cached('digitraffic.json', 'https://tie.digitraffic.fi/api/weathercam/v1/stations', headers={'Digitraffic-User': 'open-webcam-atlas'}))
    out = []
    for f in d['features']:
        p = f['properties']; lon, lat = f['geometry']['coordinates'][:2]
        for i, pr in enumerate([x for x in p.get('presets', []) if x.get('inCollection')]):
            img = f"https://weathercam.digitraffic.fi/{pr['id']}.jpg"
            out.append(cam('fi-' + pr['id'], lat + i * 0.00002, lon, p['name'].split('_', 1)[-1].replace('_', ' ') + (f' (view {i + 1})' if i else ''),
                           'weather', 'Digitraffic Finland', 'FI', img, img=img, refresh=600))
    return out


def iceland():
    out = []
    for c in json.loads(cached('iceland.json', 'https://gagnaveita.vegagerdin.is/api/vefmyndavelar2014_1')):
        if not c.get('Slod'): continue
        out.append(cam('is-' + h(c['Slod']), c['Breidd'], c['Lengd'], f"{c['Myndavel']}: {c.get('Skyring') or ''}", 'weather',
                       'Vegagerðin', 'IS', c['Slod'], img=c['Slod'], refresh=600))
    return out


def fotowebcam():
    out = []
    for c in json.loads(cached('fotowebcam.json', 'https://www.foto-webcam.eu/webcam/include/metadata.php'))['cams']:
        if c.get('offline') or c.get('hidden') or not c.get('latitude'): continue
        img = c['imgurl'].replace('/400.jpg', '/1200.jpg')
        out.append(cam('fw-' + c['id'], c['latitude'], c['longitude'], c['title'], 'scenic', 'foto-webcam.eu', (c.get('country') or '').upper(),
                       c['link'], img=img, refresh=int(c.get('captureInterval') or 600)))
    return out


# ---------------------------------------------------------------- Asia-Pacific
def hongkong():
    x = cached('hk.xml', 'https://static.data.gov.hk/td/traffic-snapshot-images/code/Traffic_Camera_Locations_En.xml')
    out = []
    for m in re.finditer(r'<image>.*?<key>(.*?)</key>.*?<description>(.*?)</description>.*?<latitude>(.*?)</latitude>.*?<longitude>(.*?)</longitude>.*?<url>(.*?)</url>', x, re.S):
        k, d, lat, lon, url = m.groups()
        out.append(cam('hk-' + k, lat, lon, d, 'traffic', 'HK Transport Dept', 'HK', url.strip(), img=url.strip(), refresh=120))
    return out


def singapore():
    d = json.loads(get('https://api.data.gov.sg/v1/transport/traffic-images'))
    return [cam('sg-' + c['camera_id'], c['location']['latitude'], c['location']['longitude'], f"LTA traffic camera {c['camera_id']}", 'traffic',
                'LTA Singapore', 'SG', 'https://api.data.gov.sg/v1/transport/traffic-images', img=c['image'], refresh=60)
            for c in d['items'][0]['cameras']]


def nz():
    x = cached('nz.xml', 'https://trafficnz.info/service/traffic/rest/4/cameras/all')
    out = []
    for c in re.findall(r'<camera>(.*?)</camera>', x, re.S):
        g = lambda t: (re.search(rf'<{t}>(.*?)</{t}>', c, re.S) or [None, None])[1]
        if g('offline') == 'true': continue
        img = 'https://www.trafficnz.info' + g('imageUrl')
        out.append(cam('nz-' + g('id'), g('latitude'), g('longitude'), f"{g('name')}: {g('description')}", 'traffic', 'NZTA', 'NZ', img, img=img, refresh=300))
    return out


def nsw():
    out = []
    for f in json.loads(cached('nsw.json', 'https://www.livetraffic.com/datajson/all-feeds-web.json')):
        p = f.get('properties', {})
        if not p.get('href') or f.get('geometry', {}).get('type') != 'Point': continue
        lon, lat = f['geometry']['coordinates'][:2]
        out.append(cam('nsw-' + h(p['href']), lat, lon, f"{p.get('title')}: {p.get('view', '')}", 'traffic', 'Live Traffic NSW', 'AU', p['href'], img=p['href'], refresh=60))
    return out


def qld():
    out = []
    for f in json.loads(cached('qld.json', 'https://api.qldtraffic.qld.gov.au/v1/webcams?apikey=3e83add325cbb69ac4d8e5bf433d770b'))['features']:
        p = f['properties']; lon, lat = f['geometry']['coordinates'][:2]
        if not p.get('image_url'): continue
        out.append(cam(f"qld-{p['id']}", lat, lon, p['description'], 'traffic', 'QLDTraffic', 'AU', p['image_url'], img=p['image_url'], refresh=60))
    return out


# ---------------------------------------------------------------- portals expanded in full
def krk():
    """cam.krk.ru (Krasnoyarsk city cameras, CC BY-SA). The camera list is embedded in the homepage HTML as
    rootScope={"cameras":[...]}; the JSON has `'flutoken': ''` (single quotes) which must be fixed first."""
    page = cached('krk.html', 'https://cam.krk.ru/', headers={'User-Agent': 'Mozilla/5.0 (compatible; open-webcam-atlas)'})
    m = re.search(r'rootScope\s*=\s*(\{"cameras":.*?\});', page, re.S)
    blob = re.sub(r"""(["']?flutoken["']?)\s*:\s*''""", '"flutoken": ""', m.group(1))
    out = []
    for c in json.loads(blob)['cameras']:
        if c.get('latitude') is None or c.get('longitude') is None: continue
        out.append(cam(f"krk-{c['id']}", c['latitude'], c['longitude'], c.get('title') or f"Krasnoyarsk {c['id']}", 'traffic',
                       'cam.krk.ru', 'RU', f"https://cam.krk.ru/camera/{c['id']}",
                       img=f"https://cam.krk.ru/api/v1/web/preview_images/{c['id']}?flutoken=",
                       stream=f"https://fluserver.orionnet.online/cam{c['id']}/index.m3u8", refresh=60))
    return out


def usgs_hivis():
    """USGS HIVIS river cameras (public domain) via the open NIMS API behind apps.usgs.gov/hivis."""
    out = []
    for c in json.loads(cached('usgs_nims.json', 'https://api.waterdata.usgs.gov/nims/v0/cameras?enabled=true')):
        if c.get('hideCam') or not c.get('newestImageDT'): continue
        try: lat, lon = float(c['lat']), float(c['lng'])
        except (TypeError, ValueError): continue
        out.append(cam(f"usgs-{c['camId']}", lat, lon, c.get('camDesc') or c.get('camName'), 'water', 'USGS HIVIS', 'US',
                       f"https://apps.usgs.gov/hivis/camera/{c['camId']}",
                       img=f"{c['smallDir']}{c['camId']}_newest.jpg", refresh=900))
    return out


# ---------------------------------------------------------------- optional, keyed sources
def windy():
    """Windy Webcams API v3 (~69k webcams worldwide, incl. Japan). Needs a free key in WINDY_API_KEY.
    The free tier rejects offset > 1000 ("Offset is over API tier limit"), so the world is cut into bbox tiles
    (north,east,south,west) that are split until each holds <= 1050 cameras, then paged 50 at a time."""
    key = os.environ.get('WINDY_API_KEY')
    if not key: print('  windy: skipped (set WINDY_API_KEY)'); return []
    base = 'https://api.windy.com/webcams/api/v3/webcams'
    hdr = {'x-windy-api-key': key}

    def call(q):
        for attempt in range(4):
            try: return json.loads(get(f'{base}?{q}', headers=hdr, timeout=40))
            except Exception as ex:
                if '400' in str(ex): return None
                time.sleep(1.5 * (attempt + 1))
        return None

    def tile_rows(n, e, s, w, depth=0):
        bb = f'bbox={n},{e},{s},{w}'
        d = call(f'limit=1&offset=0&{bb}')
        if not d: return []
        total = d.get('total', 0)
        if total == 0: return []
        if total > 1050 and (n - s) > 0.02:
            mlat, mlon = (n + s) / 2, (e + w) / 2
            rows = []
            for sub in ((n, e, mlat, mlon), (n, mlon, mlat, w), (mlat, e, s, mlon), (mlat, mlon, s, w)): rows += tile_rows(*sub, depth + 1)
            return rows
        rows = []
        for off in range(0, min(total, 1050), 50):
            d = call(f'limit=50&offset={off}&{bb}&include=location,images,player,urls,categories')
            if not d: break
            rows += d.get('webcams', [])
        return rows

    tiles = [(90, 180, 0, 0), (90, 0, 0, -180), (0, 180, -90, 0), (0, 0, -90, -180)]
    seen, out = set(), []
    with ThreadPoolExecutor(4) as ex:
        for rows in ex.map(lambda tl: tile_rows(*tl), tiles):
            for w_ in rows:
                if w_['webcamId'] in seen or w_.get('status') != 'active': continue
                seen.add(w_['webcamId'])
                loc = w_.get('location') or {}; im = (w_.get('images') or {}).get('current') or {}; pl = w_.get('player') or {}
                ids = [c.get('id') for c in w_.get('categories') or []]
                cat = 'traffic' if 'traffic' in ids else 'weather' if ids == ['meteo'] else 'water' if {'lake', 'river'} & set(ids) else 'scenic'
                out.append(cam(f"windy-{w_['webcamId']}", loc['latitude'], loc['longitude'],
                               ' › '.join(filter(None, [loc.get('city'), w_.get('title', '').split('›')[-1].strip()])) or w_.get('title'), cat,
                               'Windy Webcams', (loc.get('country_code') or '').upper(), (w_.get('urls') or {}).get('detail') or f"https://www.windy.com/webcams/{w_['webcamId']}",
                               img=im.get('preview') or im.get('thumbnail'), embed=pl.get('live') or pl.get('day'), refresh=600))
                if not pl.get('live') and pl.get('day'):
                    out[-1]['embed'] += '?autoplay=1&loop=1'
                    out[-1]['timelapse'] = True
    return out


def osaka():
    """Public prefectural river cameras: join the official catalogue with its EPSG:3857 map."""
    base = 'https://www.osaka-kasen-portal.net/suibou/'
    catalogue = json.loads(cached('osaka-cameras.json', base + 'publicdata/ja/camera_listJp.json'))
    layers = json.loads(cached('osaka-map.json', base + 'publicdata/gis_Pc_jp.json'))
    positions = {}
    for layer in layers['layersDefinitionList']:
        for collection in layer.get('value') or []:
            if not isinstance(collection, dict): continue
            for feature in collection.get('features', []):
                p = feature.get('properties', {})
                if p.get('clickedBalloonMethod') == 'kasenCamera':
                    x, y = feature['geometry']['coordinates']
                    positions[p['iconID']] = (math.degrees(2 * math.atan(math.exp(y / 6378137)) - math.pi / 2), math.degrees(x / 6378137))
    out = []
    for c in catalogue:
        id = c['cameraId']
        if id not in positions or not c.get('cameraURL'): continue
        lat, lon = positions[id]
        out.append(cam('osaka-river-' + id, lat, lon, c['hyojiNm'] + ' · ' + c.get('jusho', ''), 'water',
                       'Osaka Prefecture Rivers', 'JP', base + 'public/ja/cameratabonly.html?cameraId=' + id,
                       img=c['cameraURL'], refresh=300))
    return out


def kyoto_roads():
    """Only stations with published images; resolve timestamped filenames at request time."""
    import xml.etree.ElementTree as ET
    base = 'https://kyoto-douro-s3bk-prod-02.s3.ap-northeast-1.amazonaws.com/public_html/common/'
    stations = ET.fromstring(cached('kyoto-road-stations.xml', base + 'xml/SENSOR_CAMERA.xml'))
    images = ET.fromstring(get(base + 'xml/CAMERA_IMAGE.xml'))
    available = {c.findtext('CameraNo') for c in images if c.findtext('FileName')}
    out = []
    for c in stations:
        number = c.findtext('CameraNo')
        if number not in available or c.findtext('SensorClass') != '003': continue
        id = 'kyoto-road-' + number
        out.append(cam(id, c.findtext('Latitude'), c.findtext('Longitude'),
                       c.findtext('SensorName') + ' · ' + c.findtext('CityName'), 'traffic', 'Kyoto Prefecture Roads', 'JP',
                       'https://dobokubousai.pref.kyoto.jp/pc/camera_syousai.html?cameraNo=' + number,
                       img='/api/snapshot?id=' + id, refresh=900))
    return out


def kyoto_tourism():
    """Official public live streams, matched to documented landmark locations (not guessed camera poles)."""
    locations = json.load(open(os.path.join(os.path.dirname(__file__), 'kyoto-locations.json')))
    out = []
    def videos(value):
        if isinstance(value, dict):
            v = value.get('lockupViewModel')
            if v and 'THUMBNAIL_OVERLAY_BADGE_STYLE_LIVE' in json.dumps(v):
                yield v.get('contentId'), v.get('metadata', {}).get('lockupMetadataViewModel', {}).get('title', {}).get('content', '')
            for child in value.values(): yield from videos(child)
        elif isinstance(value, list):
            for child in value: yield from videos(child)
    for channel in ['DMOKYOTO_Live', 'kyototouristspotlive']:
        body = get('https://www.youtube.com/@' + channel + '/streams')
        match = re.search(r'(?:var\s+)?ytInitialData\s*=\s*', body)
        if not match: raise ValueError('YouTube channel data format changed')
        data, _ = json.JSONDecoder().raw_decode(body[match.end():])
        for video, title in videos(data):
            location = next((p for p in locations if p['match'] in title), None)
            if not location or not re.fullmatch(r'[\w-]{11}', video or ''): continue
            c = cam('kyoto-tourism-' + location['key'], location['lat'], location['lon'], location['name'], 'scenic',
                    'Kyoto Official Tourism', 'JP', 'https://www.youtube.com/watch?v=' + video,
                    img='https://i.ytimg.com/vi/' + video + '/hqdefault.jpg', embed=youtube_embed('https://youtu.be/' + video))
            c['location_note'] = 'Landmark location (OpenStreetMap); the precise camera mount is not published.'
            out.append(c)
    return out


def _safe(fn, *a):
    try: return fn(*a)
    except Exception as ex: print(f'  ! {getattr(fn, "__name__", fn)}{a}: {ex}'); return []


ALL = [osm, krk, usgs_hivis, nyc, caltrans, p511, wsdot, tripcheck, iowa, drivebc, tfl, digitraffic, iceland, fotowebcam, hongkong, singapore, nz, nsw, qld, windy, osaka, kyoto_roads, kyoto_tourism]

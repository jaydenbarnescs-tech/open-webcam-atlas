"""Write the compact client index public/data/cams.json from full camera records.
rows: [id, lon, lat, name, catIdx, srcIdx, img|0, mode, kind]   kind: 0 none, 1 HLS stream, 2 MP4 clip, 3 embed only
Windy preview URLs are stored as "w:<webcamId>" and expanded by the page (saves ~5 MB)."""
import json, os, re, collections

CATS = ['traffic', 'scenic', 'water', 'weather', 'other']
WINDY = re.compile(r'^https://imgproxy\.windy\.com/_/preview/plain/current/(\d+)/original\.jpg\?v=2$')


def short_img(u):
    if not u: return 0
    m = WINDY.match(u)
    return f'w:{m.group(1)}' if m else u


def write_compact(cams, path='public/data/cams.json'):
    srcs = [s for s, _ in collections.Counter(c['src'] for c in cams).most_common()]
    os.makedirs(os.path.dirname(path), exist_ok=True)
    rows = [[c['id'], round(c['lon'], 5), round(c['lat'], 5), c['name'], CATS.index(c['cat']), srcs.index(c['src']),
             short_img(c['img']), c['mode'], 1 if c['stream'] else 2 if c['video'] else 3 if c['embed'] else 0] for c in cams]
    json.dump({'cats': CATS, 'srcs': srcs, 'rows': rows}, open(path, 'w'), separators=(',', ':'), ensure_ascii=False)


if __name__ == '__main__':
    write_compact(json.load(open('data/cameras.json')))

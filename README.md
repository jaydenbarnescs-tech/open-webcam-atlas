# Webcam Atlas

Every open, public webcam we could find, on one monochrome globe — plus a tiny API that
returns the closest cameras to any GPS point, or redirects you straight to the nearest feed.

- **109,000+ cameras from 33 open sources in 127 countries.** About 6,900 play live video (HLS streams, MP4 clips or the
  operator's embedded player), ~29,000 are live stills that refresh in place, and fewer than 2,000 are link-only.
- **Globe:** MapLibre GL (globe projection) + OpenFreeMap vector tiles. Black country borders,
  black buildings once you zoom in, halftone camera clusters.
- **Dashboard:** search an address, see cameras in the vicinity, narrow by radius, category,
  source and "has a live image".
- **No keys, no database.** Static site + three Vercel functions.

## Sources

| Region | Source | How it's read |
|---|---|---|
| Worldwide | OpenStreetMap `contact:webcam` / `webcam` tags (ODbL) | Overpass API; every link-only page is probed for an embeddable player, a YouTube live, an HLS stream or a camera still |
| USA / Canada | 511 traveller platforms: Florida, Georgia, Utah, Pennsylvania, Ontario, Arizona, Wisconsin, Idaho, New England, Connecticut, Alberta, Louisiana, Alaska, Nevada | `/List/GetData/Cameras` (same API on every deployment of the platform) |
| USA | Caltrans (live HLS), NYC DOT, WSDOT, ODOT TripCheck, Iowa DOT | Each DOT's open feed |
| Canada | DriveBC | `drivebc.ca/api/webcams` |
| UK | TfL JamCams (MP4 clips) | `api.tfl.gov.uk/Place/Type/JamCam` |
| Finland | Digitraffic weather cameras | `tie.digitraffic.fi` |
| Iceland | Vegagerðin road cameras | `gagnaveita.vegagerdin.is` |
| Alps (AT/DE/IT/CH) | foto-webcam.eu | public metadata feed |
| Hong Kong | Transport Department snapshots | data.gov.hk |
| Singapore | LTA traffic images | data.gov.sg |
| New Zealand | NZTA | trafficnz.info |
| Australia | Live Traffic NSW, QLDTraffic | open feeds |
| Worldwide | Windy Webcams (~67k incl. Japan), free tier, bbox-tiled because offset is capped at 1000 | `WINDY_API_KEY` (free key); links back to Windy |
| Russia | cam.krk.ru Krasnoyarsk, all 281 cameras (CC BY-SA, live HLS) | list embedded in the homepage |
| USA | USGS HIVIS river cameras (public domain) | open NIMS API `api.waterdata.usgs.gov/nims` |

## API

All endpoints are `GET`, CORS-open, no key.

| Endpoint | What it does |
|---|---|
| `/api/nearest?lat=35.6595&lon=139.7005` | 10 closest cameras, nearest first, with `distance_m`, `direction` and a `go` link |
| `/api/go?lat=..&lon=..` | 302 redirect to the closest camera's feed (`&video=1` for the live stream/clip, `&image=1` for the still) |
| `/api/go/{id}` | 302 redirect to one camera |
| `/api/cameras?id=..` | One camera's full record. No id → dataset totals |

`/nearest` and `/go` accept: `limit` (1–200), `radius_km`, `category` (`traffic,scenic,water,weather,other`),
`source` (any part of a source name, e.g. `tfl`, `caltrans`), `media` (`image` or `video`).

Each camera has `media` (`video` / `image` / `link`) plus whichever of `stream_url` (HLS), `video_url` (MP4),
`embed_url` (iframe player) and `image_url` it offers.

```bash
curl "https://<your-deployment>/api/nearest?lat=40.758&lon=-73.9855&limit=3"
open "https://<your-deployment>/api/go?lat=47.37&lon=8.54"     # nearest feed in Zürich
```

## Run locally

```bash
node scripts/dev.mjs          # http://localhost:3000 (serves public/ and api/)
```

## Refresh the camera index

```bash
rm -rf raw && python3 scripts/build-data.py     # re-downloads every source (~5 min), rebuilds data/ and public/data/
WINDY_API_KEY=xxx python3 scripts/build-data.py # also pull Windy's worldwide network
```
Note: NYC DOT blocks some cloud IP ranges (e.g. Oracle Cloud). Run the build from a home/office connection or CI if it fails.

## Adding a source

Add a function to `scripts/sources.py` that returns `cam(...)` dicts and append it to `ALL`.
Only add feeds that are published openly by their operator. Don't add cameras discovered by scanning
for unsecured devices.

## Licence

Code: MIT. Camera index: ODbL (OpenStreetMap contributors) + NYC DOT / Caltrans open data.
The feeds themselves belong to their operators — the atlas only links to them.

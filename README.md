# Webcam Atlas

Every open, public webcam we could find, on one monochrome globe — plus a tiny API that
returns the closest cameras to any GPS point, or redirects you straight to the nearest feed.

- **~12,000 cameras** from OpenStreetMap (`contact:webcam` / `webcam` tags), NYC DOT and Caltrans.
- **Globe:** MapLibre GL (globe projection) + OpenFreeMap vector tiles. Black country borders,
  black buildings once you zoom in, halftone camera clusters.
- **Dashboard:** search an address, see cameras in the vicinity, narrow by radius, category,
  source and "has a live image".
- **No keys, no database.** Static site + three Vercel functions.

## API

All endpoints are `GET`, CORS-open, no key.

| Endpoint | What it does |
|---|---|
| `/api/nearest?lat=35.6595&lon=139.7005` | 10 closest cameras, nearest first, with `distance_m`, `direction` and a `go` link |
| `/api/go?lat=..&lon=..` | 302 redirect to the closest camera's feed (`&image=1` for the still image) |
| `/api/go/{id}` | 302 redirect to one camera |
| `/api/cameras?id=..` | One camera's full record. No id → dataset totals |

`/nearest` and `/go` accept: `limit` (1–200), `radius_km`, `category` (`traffic,scenic,water,other`),
`source` (`osm,nyc,caltrans`), `has_image=1`.

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
npm run data                  # downloads raw sources into raw/, rebuilds data/ and public/data/
```

## Adding a source

Add a block to `scripts/build-data.py` that calls `add(id, lat, lon, name, category, source, url, img=None, stream=None)`.
Only add feeds that are published openly by their operator. Don't add cameras discovered by scanning
for unsecured devices.

## Licence

Code: MIT. Camera index: ODbL (OpenStreetMap contributors) + NYC DOT / Caltrans open data.
The feeds themselves belong to their operators — the atlas only links to them.

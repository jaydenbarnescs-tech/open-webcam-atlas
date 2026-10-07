import { readFileSync } from 'node:fs';
import { join } from 'node:path';

let CAMS = null;
export function cams() {
  if (!CAMS) CAMS = JSON.parse(readFileSync(join(process.cwd(), 'data', 'cameras.json'), 'utf8'));
  return CAMS;
}

const R = 6371008.8, rad = (d) => (d * Math.PI) / 180;
export function distance(lat1, lon1, lat2, lon2) {
  const dLat = rad(lat2 - lat1), dLon = rad(lon2 - lon1);
  const a = Math.sin(dLat / 2) ** 2 + Math.cos(rad(lat1)) * Math.cos(rad(lat2)) * Math.sin(dLon / 2) ** 2;
  return 2 * R * Math.asin(Math.min(1, Math.sqrt(a)));
}
export function bearing(lat1, lon1, lat2, lon2) {
  const y = Math.sin(rad(lon2 - lon1)) * Math.cos(rad(lat2));
  const x = Math.cos(rad(lat1)) * Math.sin(rad(lat2)) - Math.sin(rad(lat1)) * Math.cos(rad(lat2)) * Math.cos(rad(lon2 - lon1));
  return Math.round(((Math.atan2(y, x) * 180) / Math.PI + 360) % 360);
}
const DIRS = ['N', 'NE', 'E', 'SE', 'S', 'SW', 'W', 'NW'];
export const compass = (b) => DIRS[Math.round(b / 45) % 8];

export const CATEGORIES = ['traffic', 'scenic', 'water', 'weather', 'other'];
export const slug = (s) => String(s).toLowerCase().normalize('NFKD').replace(/[^a-z0-9]+/g, '');
const MEDIA = ['link', 'image', 'video'];

export function shape(c, origin, base = '') {
  const o = {
    id: c.id, name: c.name, lat: c.lat, lon: c.lon, category: c.cat, source: c.src,
    country: c.country || null, media: MEDIA[c.mode ?? (c.img ? 1 : 0)],
    feed_url: c.url, image_url: c.img || null, stream_url: c.stream || null, video_url: c.video || null, embed_url: c.embed || null,
    refresh_s: c.refresh || null,
    go: `${base}/api/go/${encodeURIComponent(c.id)}`,
  };
  if (origin) {
    o.distance_m = Math.round(distance(origin.lat, origin.lon, c.lat, c.lon));
    const b = bearing(origin.lat, origin.lon, c.lat, c.lon);
    o.bearing_deg = b; o.direction = compass(b);
  }
  return o;
}

/** Parse + validate common query params. Returns {error} or params. */
export function parseQuery(q) {
  const lat = parseFloat(q.lat), lon = parseFloat(q.lon ?? q.lng);
  if (!Number.isFinite(lat) || !Number.isFinite(lon) || Math.abs(lat) > 90 || Math.abs(lon) > 180)
    return { error: 'lat and lon are required, e.g. ?lat=35.6595&lon=139.7005' };
  const limit = Math.min(Math.max(parseInt(q.limit ?? '10', 10) || 10, 1), 200);
  const radius = q.radius_km != null ? parseFloat(q.radius_km) : null;
  const cats = q.category ? String(q.category).split(',').filter((c) => CATEGORIES.includes(c)) : null;
  const srcs = q.source ? String(q.source).split(',').map(slug).filter(Boolean) : null;
  const hasImage = ['1', 'true', 'yes'].includes(String(q.has_image ?? '').toLowerCase());
  const media = q.media === 'video' ? 2 : q.media === 'image' ? 1 : hasImage ? 1 : 0; // minimum media level
  return { lat, lon, limit, radius: Number.isFinite(radius) && radius > 0 ? radius : null, cats, srcs, media };
}

export function nearest(p) {
  const res = [];
  for (const c of cams()) {
    if (p.cats && !p.cats.includes(c.cat)) continue;
    if (p.srcs && !p.srcs.some((s) => slug(c.src).includes(s))) continue;
    if (p.media && (c.mode ?? 0) < p.media) continue;
    // cheap bounding prefilter when radius given
    if (p.radius && Math.abs(c.lat - p.lat) > p.radius / 110.574 + 0.01) continue;
    const d = distance(p.lat, p.lon, c.lat, c.lon);
    if (p.radius && d > p.radius * 1000) continue;
    res.push([d, c]);
  }
  res.sort((a, b) => a[0] - b[0]);
  return res.slice(0, p.limit).map((r) => r[1]);
}

export function cors(res) {
  res.setHeader('Access-Control-Allow-Origin', '*');
  res.setHeader('Access-Control-Allow-Methods', 'GET, OPTIONS');
}
export function baseUrl(req) {
  const proto = req.headers['x-forwarded-proto'] || 'https';
  return `${proto}://${req.headers['x-forwarded-host'] || req.headers.host}`;
}
export const ATTRIBUTION =
  'Camera index: © OpenStreetMap contributors (ODbL) and 29 government open-data feeds (see /api/cameras). Feeds belong to their operators.';

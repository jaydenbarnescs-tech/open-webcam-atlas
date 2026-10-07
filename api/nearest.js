import { parseQuery, nearest, shape, cors, baseUrl, ATTRIBUTION } from './_lib/cams.js';

// GET /api/nearest?lat=35.6595&lon=139.7005[&limit=10&radius_km=5&category=traffic,scenic&source=tfl,caltrans&media=video|image]
export default function handler(req, res) {
  cors(res);
  if (req.method === 'OPTIONS') return res.status(204).end();
  const p = parseQuery(req.query);
  if (p.error) return res.status(400).json({ error: p.error });
  const base = baseUrl(req);
  const cameras = nearest(p).map((c) => shape(c, p, base));
  res.setHeader('Cache-Control', 'public, s-maxage=3600, stale-while-revalidate=86400');
  res.status(200).json({
    query: { lat: p.lat, lon: p.lon, limit: p.limit, radius_km: p.radius, category: p.cats, source: p.srcs, media: ['any', 'image', 'video'][p.media] },
    count: cameras.length, cameras, attribution: ATTRIBUTION,
  });
}

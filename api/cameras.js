import { cams, shape, cors, baseUrl, CATEGORIES, ATTRIBUTION } from './_lib/cams.js';

// GET /api/cameras?id=nyc-8a6bc417  -> one camera
// GET /api/cameras                   -> dataset stats
export default function handler(req, res) {
  cors(res);
  const all = cams();
  if (req.query.id) {
    const c = all.find((x) => x.id === req.query.id);
    if (!c) return res.status(404).json({ error: 'Unknown camera id' });
    return res.status(200).json(shape(c, null, baseUrl(req)));
  }
  const by = (k) => all.reduce((m, c) => ((m[c[k]] = (m[c[k]] || 0) + 1), m), {});
  res.setHeader('Cache-Control', 'public, s-maxage=3600');
  const media = by('mode');
  res.status(200).json({ total: all.length, categories: CATEGORIES, by_category: by('cat'), by_source: by('src'), by_country: by('country'),
    by_media: { video: media[2] || 0, image: media[1] || 0, link: media[0] || 0 }, attribution: ATTRIBUTION });
}

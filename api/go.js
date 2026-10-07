import { cams, parseQuery, nearest, cors } from './_lib/cams.js';

// GET /api/go/:id            -> 302 to that camera's feed
// GET /api/go?lat=..&lon=..  -> 302 to the closest camera's feed (same filters as /api/nearest)
// add &image=1 for the still image, &video=1 for the live stream / clip / player (when available)
export default function handler(req, res) {
  cors(res);
  const q = req.query;
  let cam;
  if (q.id) cam = cams().find((c) => c.id === q.id);
  else {
    const p = parseQuery({ ...q, limit: 1 });
    if (p.error) return res.status(400).json({ error: 'Use /api/go/{id} or /api/go?lat=..&lon=..' });
    cam = nearest(p)[0];
  }
  if (!cam) return res.status(404).json({ error: 'No camera found' });
  const target = q.image && cam.img ? cam.img : q.video && (cam.stream || cam.video || cam.embed) ? (cam.stream || cam.video || cam.embed) : cam.url;
  res.setHeader('Cache-Control', 'public, s-maxage=600');
  res.setHeader('X-Camera-Id', cam.id);
  res.redirect(302, target);
}

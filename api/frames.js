import { cams, cors } from './_lib/cams.js';

// Recorded frames published by the operator, restricted to known catalogue cameras.
export default async function handler(req, res) {
  cors(res);
  const camera = cams().find(c => c.id === String(req.query.id || ''));
  if (camera?.frames !== 'weathernews') return res.status(404).json({ error: 'No frame history for this camera' });
  const id = camera.id.replace('weathernews-', '');
  try {
    const response = await fetch('https://weathernews.jp/onebox/livecam/api/livecam/detail?id=' + encodeURIComponent(id) + '&type=all', { signal: AbortSignal.timeout(10000) });
    if (!response.ok) throw new Error('History unavailable');
    const data = await response.json();
    const history = data.onehour?.length > 1 ? data.onehour : data.tenmin;
    const frames = (history || []).filter(f => {
      try {
        const u = new URL(f.file);
        return u.protocol === 'https:' && u.hostname === 'gvs.weathernews.jp' && u.pathname.startsWith('/livecam/' + id + '/') && Number.isFinite(f.time);
      } catch { return false; }
    }).sort((a, b) => a.time - b.time).slice(-24).map(f => ({ url: f.file, time: f.time * 1000 }));
    if (frames.length < 2) throw new Error('Not enough frames');
    res.setHeader('Cache-Control', 'public, s-maxage=60');
    res.status(200).json({ frames });
  } catch {
    res.status(502).json({ error: 'The operator is not providing frame history' });
  }
}

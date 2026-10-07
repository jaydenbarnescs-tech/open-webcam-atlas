import { createHash } from 'node:crypto';
import { cams, cors } from './_lib/cams.js';

const KYOTO = 'https://kyoto-douro-s3bk-prod-02.s3.ap-northeast-1.amazonaws.com/public_html/common/';
let kyotoImages, kyotoChecked = 0, kyotoPending;
async function kyotoImage(camera) {
  if (!kyotoImages || Date.now() - kyotoChecked > 60000) {
    kyotoPending ||= fetch(KYOTO + 'xml/CAMERA_IMAGE.xml', { signal: AbortSignal.timeout(8000), cache: 'no-store' }).then(async (response) => {
      if (!response.ok) throw new Error('Camera catalogue unavailable');
      const xml = await response.text(), images = new Map();
      for (const match of xml.matchAll(/<CAMERA_IMAGE>([\s\S]*?)<\/CAMERA_IMAGE>/g)) {
        const id = match[1].match(/<CameraNo>(\d+)<\/CameraNo>/)?.[1];
        const file = match[1].match(/<FileName>(C_\d+_\d+\.jpg)<\/FileName>/)?.[1];
        if (id && file) images.set(id, file);
      }
      if (!images.size) throw new Error('Empty camera catalogue');
      kyotoImages = images; kyotoChecked = Date.now();
    }).finally(() => { kyotoPending = null; });
    await kyotoPending;
  }
  const file = kyotoImages.get(camera.id.replace('kyoto-road-', ''));
  if (!file) throw new Error('No current camera image');
  return KYOTO + 'img/' + file;
}

// Only fetch known camera records, never an arbitrary caller-supplied URL.
export default async function handler(req, res) {
  cors(res);
  res.setHeader('Access-Control-Expose-Headers', 'X-Camera-Frame, X-Camera-Updated');
  res.setHeader('Cache-Control', 'no-store');
  const camera = cams().find((c) => c.id === String(req.query.id || ''));
  if (!camera?.img) return res.status(404).json({ error: 'No snapshot for this camera' });
  try {
    const url = camera.id.startsWith('kyoto-road-') ? await kyotoImage(camera) : camera.img;
    if (!/^https?:\/\//.test(url)) throw new Error('Invalid snapshot source');
    const response = await fetch(url, { signal: AbortSignal.timeout(10000), cache: 'no-store' });
    if (!response.ok || !response.headers.get('content-type')?.startsWith('image/')) throw new Error('Camera image unavailable');
    const chunks = []; let size = 0;
    for await (const chunk of response.body) {
      size += chunk.length;
      if (size > 4 * 1024 * 1024) throw new Error('Camera image too large');
      chunks.push(chunk);
    }
    const image = Buffer.concat(chunks);
    res.setHeader('Content-Type', response.headers.get('content-type'));
    res.setHeader('X-Camera-Frame', createHash('sha256').update(image).digest('hex'));
    const modified = response.headers.get('last-modified');
    if (modified) res.setHeader('X-Camera-Updated', modified);
    res.end(image);
  } catch {
    res.status(502).json({ error: 'The operator is not providing a current snapshot' });
  }
}

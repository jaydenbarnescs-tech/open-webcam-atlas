import test from 'node:test';
import assert from 'node:assert/strict';
import { createHash } from 'node:crypto';
import handler from '../api/snapshot.js';

const invoke = async (id) => {
  const res = { code: 200, headers: {}, setHeader(k,v) { this.headers[k]=v; }, status(code) { this.code=code; return this; }, json(body) { this.body=body; }, end(body) { this.body=body; } };
  await handler({ query: { id } }, res); return res;
};

test('snapshot lookup rejects unknown cameras and resolves the newest Kyoto filename after cache expiry', async () => {
  const originalFetch = global.fetch, originalNow = Date.now;
  let now = originalNow(), stamp = '20261007211500';
  const requested = [], bytes = Buffer.from('test image frame');
  Date.now = () => now;
  global.fetch = async (url) => {
    requested.push(url);
    if (url.endsWith('CAMERA_IMAGE.xml')) return new Response(`<CAMERA_IMAGE_ROOT><CAMERA_IMAGE><CameraNo>1000042</CameraNo><FileName>C_1000042_${stamp}.jpg</FileName></CAMERA_IMAGE></CAMERA_IMAGE_ROOT>`);
    return new Response(bytes, {headers: {'Content-Type':'image/jpeg'}});
  };
  try {
    assert.equal((await invoke('does-not-exist')).code, 404);
    assert.equal(requested.length, 0);
    let res = await invoke('kyoto-road-1000042');
    assert.equal(res.code, 200);
    assert.equal(res.headers['X-Camera-Frame'], createHash('sha256').update(bytes).digest('hex'));
    assert.match(requested.at(-1), /C_1000042_20261007211500.jpg$/);
    now += 61000; stamp = '20261007213000';
    res = await invoke('kyoto-road-1000042');
    assert.equal(res.code, 200);
    assert.match(requested.at(-1), /C_1000042_20261007213000.jpg$/);
    global.fetch = async () => new Response('<html>Offline</html>', {headers: {'Content-Type':'text/html'}});
    assert.equal((await invoke('kyoto-road-1000042')).code, 502);
  } finally { global.fetch = originalFetch; Date.now = originalNow; }
});

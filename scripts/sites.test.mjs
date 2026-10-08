import test from 'node:test';
import assert from 'node:assert/strict';
import { readFile } from 'node:fs/promises';
import worker from '../dist/server/index.js';
import nearest from '../api/nearest.js';
const env = { ASSETS: { async fetch(req) { const path = new URL(req.url).pathname; try { return new Response(await readFile('dist/client' + (path === '/' ? '/index.html' : path))); } catch { return new Response('missing', {status:404}); } } } };
const call = path => worker.fetch(new Request('https://atlas.example' + path), env);
test('Sites route adapter preserves catalogue, nearest results, details, redirects and failures', async () => {
  assert.match(await (await call('/')).text(), /Webcam Atlas/);
  assert.equal((await (await call('/api/cameras')).json()).total, 110309);
  for (const query of ['lat=34.6937&lon=135.5023&limit=10','lat=35.0116&lon=135.7681&source=weathernews&limit=200','lat=40.758&lon=-73.9855&media=video&radius_km=10']) {
    let expected;
    nearest({query:Object.fromEntries(new URLSearchParams(query)),headers:{host:'atlas.example'}}, {setHeader(){},status(){return this},json(v){expected=v}});
    const actual = await (await call('/api/nearest?' + query)).json();
    assert.deepEqual(actual, expected);
  }
  const result = await (await call('/api/nearest?lat=34.6937&lon=135.5023&limit=1')).json();
  const camera = result.cameras[0];
  const detail = await (await call('/api/cameras?id=' + camera.id)).json();
  assert.equal(detail.id, camera.id);
  const redirect = await call('/api/go/' + camera.id);
  assert.equal(redirect.status,302); assert.equal(redirect.headers.get('location'), camera.feed_url);
  assert.equal((await call('/api/nearest?lat=no')).status,400);
  assert.equal((await call('/api/cameras?id=unknown')).status,404);
  assert.equal((await call('/api/snapshot?id=unknown')).status,404);
  assert.equal((await call('/api/frames?id=unknown')).status,404);
  assert.equal((await call('/api/no-such-route')).status,404);
});
test('Sites snapshot emits bytes and SHA-256, and frame history works', async () => {
  const fetchOriginal=globalThis.fetch;
  const result=await (await call('/api/nearest?lat=34.69&lon=135.5&source=weathernews&limit=1')).json();
  const camera=result.cameras[0], id=camera.id.replace('weathernews-','');
  globalThis.fetch=async url => String(url).includes('/detail?') ? Response.json({onehour:[{file:`https://gvs.weathernews.jp/livecam/${id}/1.jpg`,time:1},{file:`https://gvs.weathernews.jp/livecam/${id}/2.jpg`,time:2}]}) : new Response(new Uint8Array([1,2,3]),{headers:{'content-type':'image/jpeg'}});
  try {
    const snapshot=await call('/api/snapshot?id='+camera.id);
    assert.equal(snapshot.status,200); assert.equal(snapshot.headers.get('x-camera-frame'),'039058c6f2c0cb492c533b0a4d14ef77cc0f78abccced5287d84a1a2011cfb81');
    assert.equal((await (await call('/api/frames?id='+camera.id)).json()).frames.length,2);
  } finally { globalThis.fetch=fetchOriginal; }
});

import test from 'node:test';
import assert from 'node:assert/strict';
import handler from '../api/frames.js';
import { cams } from '../api/_lib/cams.js';

const invoke = async (id) => {
  const res = { code: 200, headers: {}, setHeader(k,v) { this.headers[k]=v; }, status(code) { this.code=code; return this; }, json(body) { this.body=body; } };
  await handler({query:{id}}, res); return res;
};
test('frame history uses known cameras, orders and bounds history, and rejects unrelated URLs', async () => {
  const original = global.fetch;
  const camera = cams().find(c => c.frames === 'weathernews'), id = camera.id.replace('weathernews-', '');
  let calls = 0;
  global.fetch = async () => {
    calls++;
    return Response.json({onehour: [
      {file:'https://unrelated.example/frame.jpg', time:1000},
      {file:'https://gvs.weathernews.jp/livecam/other/frame.jpg', time:1000},
      ...Array.from({length:30}, (_, i) => ({file:`https://gvs.weathernews.jp/livecam/${id}/640/${30-i}.webp`, time:30-i})),
    ]});
  };
  try {
    assert.equal((await invoke('missing')).code, 404); assert.equal(calls, 0);
    const res = await invoke(camera.id);
    assert.equal(res.code, 200); assert.equal(res.body.frames.length, 24);
    assert.equal(res.body.frames[0].time, 7000); assert.equal(res.body.frames.at(-1).time, 30000);
    global.fetch = async () => Response.json({onehour:[]});
    assert.equal((await invoke(camera.id)).code, 502);
  } finally { global.fetch = original; }
});

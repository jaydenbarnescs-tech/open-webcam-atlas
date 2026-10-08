import { handlers } from './handlers.js';
import { shard } from './shard.mjs';
let searchIndex;
async function assetJSON(env, origin, path) {
  const response = await env.ASSETS.fetch(new Request(origin + path));
  if (!response.ok) throw new Error('Catalogue asset unavailable');
  return response.json();
}
async function recordsFor(ids, env, origin) {
  const wanted = new Set(ids), result = [];
  // Sequential partitions keep peak memory bounded, even for 200 results.
  for (const bucket of new Set(ids.map(shard))) {
    const records = await assetJSON(env, origin, `/_catalog/${bucket}.json`);
    for (const c of records) if (wanted.has(c.id)) result.push(c);
  }
  return result;
}
export default {
  async fetch(request, env) {
    const url = new URL(request.url);
    if (!url.pathname.startsWith('/api/')) return env.ASSETS.fetch(request);
    const cors = {'Access-Control-Allow-Origin':'*', 'Access-Control-Allow-Methods':'GET, OPTIONS'};
    if (request.method === 'OPTIONS') return new Response(null, { status: 204, headers: cors });
    if (request.method !== 'GET') return new Response('Method not allowed', { status: 405, headers: cors });
    const match = url.pathname.match(/^\/api\/(cameras|nearest|go|frames|snapshot)(?:\/([^/]+))?$/);
    if (!match || (match[2] && match[1] !== 'go')) return new Response('Not found', {status:404,headers:cors});
    const route = match[1], query = Object.fromEntries(url.searchParams);
    if (match[2]) { try { query.id = decodeURIComponent(match[2]); } catch { return new Response('Invalid id', {status:400,headers:cors}); } }
    try {
      if (route === 'cameras' && !query.id) {
        const stats = await assetJSON(env, url.origin, '/_catalog/stats.json');
        return Response.json(stats, {headers:{...cors,'Cache-Control':'public, max-age=3600'}});
      }
      let ids = query.id ? [query.id] : [];
      if (route === 'nearest' || (route === 'go' && !query.id)) {
        const p = handlers([]).parseQuery(route === 'go' ? {...query,limit:1} : query);
        if (!p.error) {
          searchIndex ||= assetJSON(env, url.origin, '/_catalog/search.json').catch(e => { searchIndex = null; throw e; });
          ids = handlers(await searchIndex).findNearest(p).map(c => c.id);
        }
      }
      const records = await recordsFor(ids, env, url.origin);
      let status = 200, body = null;
      const headers = new Headers(cors);
      const res = {
        setHeader(k,v){headers.set(k,v)},
        status(s){status=s;return this},
        json(value){headers.set('Content-Type','application/json');body=JSON.stringify(value);return this},
        end(value){body=value??null;return this},
        redirect(s,to){status=s;headers.set('Location',to);return this},
      };
      await handlers(records)[route]({query,method:request.method,headers:{host:url.host,'x-forwarded-proto':url.protocol.slice(0,-1)}}, res);
      return new Response(body, {status,headers});
    } catch (e) {
      console.error('Camera request failed:', e.message);
      return Response.json({error:'Camera service temporarily unavailable'}, {status:503,headers:cors});
    }
  }
};

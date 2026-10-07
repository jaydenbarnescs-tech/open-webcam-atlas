// Tiny local dev server: serves ./public and runs ./api/*.js like Vercel would.
import http from 'node:http';
import { readFile } from 'node:fs/promises';
import { extname, join } from 'node:path';
const TYPES = { '.html': 'text/html; charset=utf-8', '.json': 'application/json', '.js': 'text/javascript' };
const port = +process.env.PORT || 3000;
http.createServer(async (req, res) => {
  const url = new URL(req.url, `http://${req.headers.host}`);
  let path = url.pathname;
  const go = path.match(/^\/api\/go\/(.+)$/);
  if (go) { url.searchParams.set('id', decodeURIComponent(go[1])); path = '/api/go'; }
  if (path.startsWith('/api/')) {
    const mod = await import(join(process.cwd(), path + '.js')).catch(() => null);
    if (!mod) { res.writeHead(404); return res.end('no route'); }
    const r = Object.assign(res, {
      status(s) { res.statusCode = s; return r; },
      json(o) { res.setHeader('Content-Type', 'application/json'); res.end(JSON.stringify(o)); return r; },
      redirect(s, u) { res.writeHead(s, { Location: u }); res.end(); },
    });
    req.query = Object.fromEntries(url.searchParams);
    return mod.default(req, r);
  }
  try {
    const f = join('public', path === '/' ? 'index.html' : path);
    const body = await readFile(f);
    res.writeHead(200, { 'Content-Type': TYPES[extname(f)] || 'application/octet-stream' }); res.end(body);
  } catch { res.writeHead(404); res.end('not found'); }
}).listen(port, () => console.log(`http://localhost:${port}`));

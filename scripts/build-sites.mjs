import { readFileSync, writeFileSync, mkdirSync, cpSync } from 'node:fs';
import { shard } from '../worker/shard.mjs';
mkdirSync('dist/server', { recursive: true });
cpSync('public', 'dist/client', { recursive: true });
mkdirSync('dist/client/_catalog', { recursive: true });
const all = JSON.parse(readFileSync('data/cameras.json', 'utf8'));
const buckets = Array.from({ length: 64 }, () => []);
for (const c of all) buckets[shard(c.id)].push(c);
for (let i = 0; i < buckets.length; i++) writeFileSync(`dist/client/_catalog/${i}.json`, JSON.stringify(buckets[i]));
writeFileSync('dist/client/_catalog/search.json', JSON.stringify(all.map(({id,lat,lon,cat,src,mode}) => ({id,lat,lon,cat,src,mode}))));
let lib = readFileSync('api/_lib/cams.js', 'utf8');
lib = lib.slice(lib.indexOf('const R =')).replaceAll('export ', '');
const routes = ['cameras', 'nearest', 'go', 'frames', 'snapshot'];
let code = `export function handlers(records) {\nconst cams = () => records;\n${lib}\n`;
for (const name of routes) {
  let source = readFileSync(`api/${name}.js`, 'utf8').replace(/^import .*;\n/gm, '').replace('export default ', '').replace('function handler(', `function ${name}(`);
  if (name === 'snapshot') source = source.replace('const image = Buffer.concat(chunks);', 'const image = new Uint8Array(size); let offset = 0; for (const chunk of chunks) { image.set(chunk, offset); offset += chunk.length; }').replace("createHash('sha256').update(image).digest('hex')", "Array.from(new Uint8Array(await crypto.subtle.digest('SHA-256', image)), b => b.toString(16).padStart(2, '0')).join('')");
  code += source + '\n';
}
code += 'return { cameras, nearest, go, frames, snapshot, parseQuery, findNearest: nearestRecords };\n}\n';
// The route and shared search function otherwise have the same name.
code = code.replace('function nearest(p)', 'function nearestRecords(p)').replaceAll('nearest(p)', 'nearestRecords(p)');
writeFileSync('dist/server/handlers.js', code);
const headers = {}; let stats;
const {handlers} = await import('../dist/server/handlers.js?build=' + Date.now());
handlers(all).cameras({query:{},headers:{host:'localhost'}}, {setHeader(k,v){headers[k]=v},status(){return this},json(v){stats=v}});
writeFileSync('dist/client/_catalog/stats.json', JSON.stringify(stats));
cpSync('worker/index.mjs', 'dist/server/index.js');
cpSync('worker/shard.mjs', 'dist/server/shard.mjs');
console.log(`Sites build: ${all.length} cameras, ${buckets.length} catalogue partitions, five APIs`);

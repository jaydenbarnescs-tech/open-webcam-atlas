"""Browser regressions. Requires playwright (WebKit) and ffmpeg; run with npm run dev active.
Usage: python3 scripts/test-preview.py [http://localhost:3000]
The test uses synthetic local media and a small camera fixture, not operator feeds.
"""
import asyncio
import base64
import json
from pathlib import Path
import subprocess
import sys
import tempfile
from playwright.async_api import async_playwright

BASE = sys.argv[1] if len(sys.argv) > 1 else 'http://localhost:3000'
ROOT = Path(__file__).resolve().parents[1]
PIXEL = base64.b64decode('iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAQAAAC1HAwCAAAAC0lEQVR42mP8/x8AAwMCAO+/l9sAAAAASUVORK5CYII=')

async def main():
    with tempfile.TemporaryDirectory(prefix='atlas-test-') as tmp:
        clip = Path(tmp) / 'clip.mp4'
        subprocess.run(['ffmpeg', '-v', 'error', '-f', 'lavfi', '-i', 'testsrc2=size=160x90:rate=12', '-t', '2', '-c:v', 'libx264', '-pix_fmt', 'yuv420p', '-movflags', '+faststart', str(clip)], check=True)
        async with async_playwright() as p:
            browser = await p.webkit.launch(headless=True)
            page = await browser.new_page(viewport={'width': 1280, 'height': 900})
            errors = []
            page.on('pageerror', lambda error: errors.append(str(error)))
            await page.route('**/__test/image*', lambda r: r.fulfill(body=PIXEL, content_type='image/png'))
            await page.route('**/__test/clip*', lambda r: r.fulfill(path=clip, content_type='video/mp4'))
            await page.route('**/__test/broken*', lambda r: r.fulfill(status=404, body='unavailable'))
            await page.goto(BASE + '/preview.js')
            await page.set_content('<div id="preview" style="position:relative;width:400px;height:300px"></div><style>video,img{position:absolute;inset:0;width:100%;height:100%}</style>')
            await page.add_script_tag(path=ROOT / 'public/preview.js')
            await page.evaluate('''() => {
              window.statuses = [];
              window.dispose = AtlasPreview(document.querySelector('#preview'), {
                stream_url: '/__test/broken.m3u8', video_url: '/__test/clip.mp4', image_url: '/__test/image.png', refresh_s: 5,
              }, { onStatus: label => statuses.push(label) });
            }''')
            await page.wait_for_function("document.querySelector('video')?.currentTime > 0.1")
            assert await page.locator('video').evaluate('(v) => v.isConnected && v.muted && v.loop && !v.paused')
            assert await page.evaluate("statuses.includes('Latest clip')")
            await page.locator('video').evaluate("v => v.dispatchEvent(new Event('error'))")
            await page.wait_for_function("statuses.at(-1) === 'Snapshot'")
            assert await page.locator('video').count() == 0
            src = await page.locator('img').get_attribute('src')
            await page.wait_for_function('(src) => document.querySelector("img").getAttribute("src") !== src', arg=src, timeout=8000)
            await page.evaluate('dispose()')
            assert await page.locator('#preview > *').count() == 0
            await page.evaluate('''() => {
              window.dispose = AtlasPreview(document.querySelector('#preview'), {video_url: '/__test/clip.mp4'});
              window.oldVideo = document.querySelector('video'); dispose();
            }''')
            await page.wait_for_timeout(200)
            assert await page.evaluate('oldVideo.paused && !oldVideo.hasAttribute("src")')
            print('PASS: stream → clip → refreshing image; disposal stops playback', flush=True)

            # Same image bytes are not a new frame; a changed frame is, and failures retain it.
            second = base64.b64decode(await page.evaluate("""() => { const c=document.createElement('canvas');c.width=c.height=2;const g=c.getContext('2d');g.fillStyle='red';g.fillRect(0,0,2,2);return c.toDataURL().split(',')[1]; }"""))
            frame = {'body': PIXEL, 'fail': False}
            async def snapshot(route):
                await route.fulfill(status=502 if frame['fail'] else 200, body=frame['body'], content_type='image/png')
            await page.route('**/__test/snapshot', snapshot)
            await page.evaluate("""() => {
              window.snapshots=[];
              window.dispose=AtlasPreview(document.querySelector('#preview'), {image_url:'/__test/image.png',snapshot_url:'/__test/snapshot',refresh_s:5}, {trackSnapshot:true,onSnapshot:s=>snapshots.push(s.state)});
            }""")
            await page.wait_for_function("snapshots.includes('loaded')")
            await page.wait_for_function("snapshots.includes('unchanged')", timeout=8000)
            frame['body'] = second
            await page.wait_for_function("snapshots.includes('updated')", timeout=8000)
            last_src = await page.locator('img').get_attribute('src')
            frame['fail'] = True
            await page.wait_for_function("snapshots.includes('unavailable')", timeout=8000)
            assert await page.locator('img').get_attribute('src') == last_src
            await page.evaluate('dispose()')
            print('PASS: unchanged/new/failed snapshot checks report accurately and keep the last frame', flush=True)

            # Recorded frames advance, remain labelled as timelapse, and stop when disposed.
            await page.route('**/__test/history', lambda r: r.fulfill(json={'frames':[
                {'url':'/__test/image.png?frame=1','time':1000}, {'url':'/__test/image.png?frame=2','time':2000}]}))
            await page.evaluate("""() => {
              window.frameTimes=[]; window.frameLabels=[];
              window.dispose=AtlasPreview(document.querySelector('#preview'), {image_url:'/__test/image.png',frames_url:'/__test/history'}, {onFrame:t=>frameTimes.push(t),onStatus:s=>frameLabels.push(s)});
            }""")
            await page.wait_for_function('new Set(frameTimes).size === 2')
            assert await page.evaluate("frameLabels.includes('Timelapse · recorded frames') && !frameLabels.includes('Live video')")
            await page.evaluate('dispose();window.stoppedAt=frameTimes.length')
            await page.wait_for_timeout(900)
            assert await page.evaluate('frameTimes.length===stoppedAt')
            await page.evaluate("""() => { window.fallbackLabels=[];window.dispose=AtlasPreview(document.querySelector('#preview'), {image_url:'/__test/image.png',frames_url:'/__test/broken-history'}, {onStatus:s=>fallbackLabels.push(s)}); }""")
            await page.wait_for_function("fallbackLabels.includes('Snapshot')")
            await page.evaluate('dispose()')
            print('PASS: recorded frames advance, dispose cleanly, and fall back to snapshots', flush=True)

            rows = [[f'fixture-{i}', lon, lat, f'Camera {i}', 0, 0, '/__test/image.png', 2, 2]
                    for i, (lon, lat) in enumerate([(139.70, 35.68), (139.704, 35.682), (139.708, 35.684), (142, 35)])]
            await page.route('**/data/cams.json', lambda r: r.fulfill(json={'cats':['traffic','scenic'], 'srcs':['Fixture'], 'rows':rows}))
            await page.route('**/api/cameras?*', lambda r: r.fulfill(json={'video_url':'/__test/clip.mp4','image_url':'/__test/image.png'}))
            await page.route('https://tiles.openfreemap.org/planet', lambda r: r.fulfill(json={'tilejson':'3.0.0','tiles':[BASE + '/__test/tile/{z}/{x}/{y}'],'maxzoom':14}))
            await page.route('**/__test/tile/**', lambda r: r.fulfill(body=b'', content_type='application/x-protobuf'))
            await page.route('https://tiles.openfreemap.org/fonts/**', lambda r: r.fulfill(body=b'', content_type='application/x-protobuf'))
            await page.goto(BASE)
            await page.wait_for_selector('#loading.done')
            await page.evaluate("__atlas.map.fire('mousedown');__atlas.map.stop();__atlas.map.jumpTo({center:[140.5,35.6],zoom:6})")
            await page.wait_for_selector('.lc[data-id="fixture-3"]')
            assert await page.evaluate('__atlas.map.getZoom() < 15')
            await page.wait_for_function("document.querySelector('.lc video')?.currentTime > 0.1")
            assert await page.locator('.lc').count() == 1, 'Clustered cameras must not get duplicate thumbnails'
            assert await page.evaluate('''() => {
              const m = __atlas.map, p = m.project([142,35]), c = m.getCanvas().getBoundingClientRect();
              const r = document.querySelector('.lc').getBoundingClientRect();
              return Math.abs(r.x+r.width/2-c.x-p.x)<2 && Math.abs(r.y+r.height/2-c.y-p.y)<2;
            }'''), 'Preview must stay anchored to the camera coordinate'
            cluster = await page.evaluate('''() => {
              const m = __atlas.map, f = m.queryRenderedFeatures({layers:['clusters']})[0];
              const p = m.project(f.geometry.coordinates), r = m.getCanvas().getBoundingClientRect();
              return {id:f.properties.cluster_id, x:p.x+r.x, y:p.y+r.y, center:f.geometry.coordinates};
            }''')
            await page.mouse.click(cluster['x'], cluster['y'])
            await page.wait_for_function("__atlas.map.getZoom() > 8 && !__atlas.map.isMoving()")
            await page.wait_for_function('(id) => !__atlas.map.queryRenderedFeatures({layers:["clusters"]}).some(f => f.properties.cluster_id === id)', arg=cluster['id'])
            await page.wait_for_selector('.lc[data-id="fixture-0"]')
            await page.locator('.lc[data-id="fixture-0"]').click(force=True)
            await page.wait_for_function("document.querySelector('#dPlayer video')?.currentTime > 0.1")
            await page.locator('#dClose').click()
            assert await page.locator('#dPlayer video').count() == 0
            assert await page.evaluate('__atlas.map.getPadding().right === 0')
            print('PASS: singletons show moving images below z15; cluster expands; drawer closes cleanly', flush=True)
            await page.locator('#filtersBtn').click()
            await page.locator('#catChips .chip').first.click()
            await page.wait_for_function("document.querySelectorAll('.lc').length === 0")
            print('PASS: filtering removes previews', flush=True)
            await page.set_viewport_size({'width':390, 'height':844})
            await page.goto(BASE + '/?mobile-test#cam=fixture-0')
            await page.wait_for_function("document.querySelector('#dPlayer video')?.currentTime > 0.1")
            assert await page.evaluate('document.documentElement.scrollWidth <= window.innerWidth')
            assert not errors, errors
            print('PASS: mobile playback/layout; no uncaught browser errors', flush=True)
            await browser.close()

asyncio.run(main())

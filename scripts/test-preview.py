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
            await page.wait_for_function("statuses.at(-1) === 'Refreshing image'")
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

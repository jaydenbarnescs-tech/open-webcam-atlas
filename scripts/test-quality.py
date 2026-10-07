"""Regression checks for retail pages, generic embeds and real camera media."""
import unittest
import quality as Q


def camera(**kw):
    return dict(id='osm-test', name='Test camera', src='OpenStreetMap', url='https://operator.example/webcam',
                img=None, embed=None, stream=None, video=None, mode=0, **kw)


class QualityTests(unittest.TestCase):
    def test_screenshot_store_is_excluded_even_with_embed_and_product_image(self):
        c = camera(); c.update(name='CCTV Market Pakistan (Complete Surveillance Security Solution Provider)',
            url='https://cctvmarket.pk', embed='https://cctvmarket.pk',
            img='https://cctvmarket.pk/wp-content/uploads/2025/06/day-and-night-camera.jpg')
        self.assertEqual(Q.review(c, {'shop':True})[1], 'non_camera_business_or_reference')
        self.assertIsNone(Q.review(c)[0])

    def test_frameable_page_and_social_preview_are_not_camera_media(self):
        result = Q.extract_media('<title>Business</title><meta property="og:image" content="/webcam.jpg"><img src="/logo.png">', 'https://camera-shop.example/')
        self.assertFalse(any(result.get(k) for k in ['img','embed','stream','video']))
        c = camera(); c['embed'] = c['url']
        self.assertIsNone(Q.review(c)[0])
        self.assertFalse(Q.camera_image('https://webcam.example/images/holiday.jpg'))

    def test_legitimate_venue_with_checkout_keeps_its_actual_live_feed(self):
        body = '<title>Resort webcam</title>price buy now checkout<video><source src="https://operator.example/live/ski.m3u8"></video><img src="/camera/current.jpg">'
        p = Q.extract_media(body, 'https://operator.example/webcam')
        c, reason = Q.review(camera(), p)
        self.assertEqual(c['stream'], 'https://operator.example/live/ski.m3u8')
        self.assertEqual(c['mode'], 2)
        self.assertIsNone(c['embed'])

    def test_real_embedded_player_is_extracted_not_parent_site(self):
        p = Q.extract_media('<iframe src="https://www.youtube-nocookie.com/embed/abcdefghijk"></iframe>', 'https://operator.example/webcam')
        self.assertEqual(p['embed'], 'https://www.youtube-nocookie.com/embed/abcdefghijk')
        self.assertFalse(Q.player_url('https://youtube.com/@channel'))
        self.assertFalse(Q.player_url('https://youtube.com.attacker.example/embed/abcdefghijk'))

    def test_still_survives_after_false_player_removed(self):
        c = camera(); c.update(img='https://operator.example/current.jpg', embed=c['url'], mode=2)
        clean, reason = Q.review(c)
        self.assertIsNone(clean['embed']); self.assertEqual(clean['mode'],1)
        self.assertEqual(reason, 'unverified_preview_removed')
        self.assertEqual(Q.review(clean), (clean,None))

    def test_nonpublic_and_authenticated_links_are_not_admitted(self):
        for url in ['http://127.0.0.1/cam.jpg','http://10.2.55.55/preview.asp', 'http://[::1]/cam.jpg',
                    'http://camera.local/cam.jpg','https://user:pass@operator.example/cam.jpg', 'https://operator.example/?login=public&password=test']:
            c = camera(); c['url'] = url
            self.assertIsNone(Q.review(c)[0])

    def test_original_direct_feed_preserved_but_stock_image_rejected(self):
        c = camera(); c['url'] = c['img'] = 'https://traffic.example/123.jpg'; c['mode']=1
        self.assertEqual(Q.review(c), (c,None))
        self.assertFalse(Q.camera_image('https://operator.example/wp-content/uploads/2025/01/webcam-advert.jpg'))
        self.assertTrue(Q.camera_image('https://operator.example/webcam/latest.jpg'))

if __name__ == '__main__': unittest.main()

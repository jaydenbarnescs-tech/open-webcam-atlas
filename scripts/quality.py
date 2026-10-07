"""Conservative admission rules for uncurated OSM links and operator-page probes.
A frameable website or a social-share/product image is not evidence of a webcam.
"""
import copy
import html
import ipaddress
import re
from html.parser import HTMLParser
from urllib.parse import urljoin, urlsplit, unquote

VERSION = 2
NON_CAMERA_DOMAINS = {
    'cctvmarket.pk', 'alarmelectronic.com', 'hefanoo.ir', 'hscworldwide.com', 'ecam.com',
    'axis.com', 'wikipedia.org', 'wikimedia.org',
    'facebook.com', 'instagram.com', 'linkedin.com', 'twitter.com', 'x.com', 'tiktok.com',
}
RETAIL_NAME = re.compile(r'cctv\s*market|surveillance\s+security\s+solution|security\s*(?:&|and)\s*consultancy|cctv\s+(?:camera\s+)?installation|security\s+system\s+(?:supplier|installer)|فروشگاه|تجهیزات امنیتی', re.I)
STOCK_IMAGE = re.compile(r'logo|favicon|sprite|avatar|banner|og[-_]?image|homepage-og|product[-_]?images?|shop-resources|listing_summary|/iris-images/|/wp-content/uploads/\d{4}/|/images.squarespace-cdn.com/|/thumb\.wikimedia.org/|ChatGPT-Image', re.I)
CAMERA_IMAGE = re.compile(r'web[-_]?cam|live[-_]?cam|snapshot|latest|current|cctv|axis-cgi|(?:^|[/_-])cam(?:era)?\d*(?:[._/-]|$)', re.I)


def host(url): return (urlsplit(url or '').hostname or '').lower()
def domain_is(url, domain): return host(url) == domain or host(url).endswith('.' + domain)


def public_url(url):
    try:
        p = urlsplit(url or '')
        if p.scheme not in {'http', 'https'} or not p.hostname or p.username or p.password: return False
        if p.hostname.lower() == 'localhost' or p.hostname.lower().endswith(('.local', '.internal')): return False
        if re.search(r'(?:^|&)(?:password|passwd|pwd|login)=', p.query, re.I): return False
        try: return ipaddress.ip_address(p.hostname).is_global
        except ValueError: return True
    except ValueError: return False


def player_url(url):
    if not public_url(url): return False
    p = urlsplit(url); h = host(url); path = p.path.lower()
    if h in {'www.youtube-nocookie.com', 'www.youtube.com', 'youtube.com'}: return path.startswith('/embed/')
    if h in {'player.vimeo.com', 'player.brownrice.com', 'player.webcamera.pl', 'pv.viewsurf.com', 'app.webcam-hd.com'}: return path != '/'
    if domain_is(url, 'roundshot.com') or domain_is(url, 'panomax.com'): return True
    if domain_is(url, 'windy.com'): return '/embed/player/' in path
    if h in {'rtsp.me', 'www.rtsp.me', 'ipcamlive.com', 'www.ipcamlive.com', 'camstreamer.com'}: return '/embed/' in path or '/player/' in path or path == '/player/player.php'
    return False


def camera_image(url, direct=False):
    if not public_url(url): return False
    p = urlsplit(url); path = unquote(p.path)
    if STOCK_IMAGE.search(url) and not re.search(r'(?:latest|current|snapshot)', path, re.I): return False
    return direct or bool(CAMERA_IMAGE.search(path))


class MediaHTML(HTMLParser):
    def __init__(self):
        super().__init__(); self.tags = []; self.title = ''; self.in_title = False
    def handle_starttag(self, tag, attrs):
        self.tags.append((tag, dict(attrs)))
        if tag == 'title': self.in_title = True
    def handle_endtag(self, tag):
        if tag == 'title': self.in_title = False
    def handle_data(self, data):
        if self.in_title: self.title += data


def extract_media(body, url):
    """Extract media, never use the whole document as an iframe or an og:image as a frame."""
    result = {'quality_version': VERSION}
    parser = MediaHTML(); parser.feed(body)
    if any(domain_is(url, d) for d in NON_CAMERA_DOMAINS) or RETAIL_NAME.search(parser.title):
        return {**result, 'excluded': 'non_camera_business_or_reference'}
    if player_url(url): result['embed'] = url
    for tag, attrs in parser.tags:
        src = html.unescape(attrs.get('src') or attrs.get('data-src') or '')
        if not src: continue
        absolute = urljoin(url, src)
        if tag == 'iframe' and player_url(absolute): result['embed'] = absolute
        elif tag in {'video', 'source'} and public_url(absolute):
            if '.m3u8' in absolute: result['stream'] = absolute
            elif re.search(r'\.mp4(?:[?#]|$)', absolute, re.I): result['video'] = absolute
        elif tag == 'img' and camera_image(absolute): result.setdefault('img', absolute)
    for match in re.finditer(r'https://[^"\'\s<>]+\.m3u8[^"\'\s<>]*', html.unescape(body)):
        if public_url(match[0]): result['stream'] = match[0]; break
    return result


def review(camera, probe=None):
    """Return (approved copy, reason), or (None, exclusion reason). Apply even to carried records."""
    if camera['src'] != 'OpenStreetMap': return camera, None
    c = copy.deepcopy(camera)
    p = probe or {}
    if not public_url(c['url']): return None, 'non_public_or_authenticated_url'
    if any(domain_is(c['url'], d) for d in NON_CAMERA_DOMAINS) or RETAIL_NAME.search(c['name']) or p.get('excluded'):
        return None, 'non_camera_business_or_reference'
    # Only actual player endpoints qualify. Old generic page embeds must be discarded.
    if c.get('embed') and not player_url(c['embed']): c['embed'] = None
    if c.get('img') and not camera_image(c['img'], direct=c['img'] == c['url']): c['img'] = None
    for k in ['stream', 'video']:
        if c.get(k) and not public_url(c[k]): c[k] = None
    if p.get('quality_version') == VERSION:
        for k in ['img', 'embed', 'stream', 'video']:
            if p.get(k): c[k] = p[k]
    if not any(c.get(k) for k in ['img', 'embed', 'stream', 'video']): return None, 'no_verified_camera_media'
    c['mode'] = 2 if c.get('stream') or c.get('video') or c.get('embed') else 1
    return c, 'unverified_preview_removed' if c != camera else None

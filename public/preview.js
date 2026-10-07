/* Shared, disposable camera player for the drawer and map thumbnails. */
(() => {
  let hlsLibrary;
  const fresh = (url) => url + (url.includes('?') ? '&' : '?') + '_t=' + Math.floor(Date.now() / 5000);
  const loadHls = () => hlsLibrary ||= new Promise((resolve, reject) => {
    const script = document.createElement('script');
    script.src = 'https://cdn.jsdelivr.net/npm/hls.js@1.7.3/dist/hls.min.js';
    script.onload = () => resolve(window.Hls);
    script.onerror = () => { hlsLibrary = null; reject(new Error('Player unavailable')); };
    document.head.append(script);
  });

  window.AtlasPreview = function(host, detail = {}, options = {}) {
    let disposed = false, generation = 0, release = () => {}, imageTimer, pendingImage, snapshotRequest, objectUrl, frameHash;
    const imageUrl = detail.image_url || options.image;
    const status = (label, moving = false) => { if (!disposed) options.onStatus?.(label, moving); };
    const image = document.createElement('img');
    image.alt = 'Latest picture from this camera';
    host.replaceChildren();
    if (imageUrl) { image.src = fresh(imageUrl); host.append(image); }
    const refreshImage = () => {
      if (!imageUrl || disposed || document.hidden || pendingImage) return;
      const next = pendingImage = new Image();
      next.onload = () => { pendingImage = null; if (!disposed) { image.src = next.src; image.hidden = false; } };
      next.onerror = () => { pendingImage = null; };
      next.src = fresh(imageUrl);
    };
    const checkSnapshot = async () => {
      if (disposed || document.hidden || snapshotRequest) return;
      snapshotRequest = new AbortController();
      const timeout = setTimeout(() => snapshotRequest?.abort(), 12000);
      try {
        const response = await fetch(detail.snapshot_url, { cache: 'no-store', signal: snapshotRequest.signal });
        if (!response.ok) throw new Error('Snapshot unavailable');
        const blob = await response.blob();
        const hash = response.headers.get('X-Camera-Frame') || Array.from(new Uint8Array(await crypto.subtle.digest('SHA-256', await blob.arrayBuffer())), b => b.toString(16).padStart(2, '0')).join('');
        if (disposed) return;
        const changed = frameHash !== hash, first = !frameHash;
        if (changed) {
          const previous = objectUrl;
          objectUrl = URL.createObjectURL(blob); image.src = objectUrl; image.hidden = false; frameHash = hash;
          if (previous) URL.revokeObjectURL(previous);
        }
        options.onSnapshot?.({ state: first ? 'loaded' : changed ? 'updated' : 'unchanged', checkedAt: Date.now(), updatedAt: response.headers.get('X-Camera-Updated') });
      } catch {
        if (!disposed) options.onSnapshot?.({ state: 'unavailable', checkedAt: Date.now() });
      } finally { clearTimeout(timeout); snapshotRequest = null; }
    };
    const snapshot = () => {
      status(imageUrl ? 'Snapshot' : 'Open camera');
      if (!imageUrl || (image.complete && !image.naturalWidth)) options.onUnavailable?.();
      if (!imageUrl) return;
      image.onload = () => {
        if (disposed) return;
        if (!image.isConnected) host.replaceChildren(image);
        if (!options.trackSnapshot || !detail.snapshot_url) status('Snapshot');
        options.onAvailable?.();
      };
      image.onerror = () => options.onUnavailable?.();
      // Recheck the operator's image without blinking or clearing the last good frame.
      const refresh = options.trackSnapshot && detail.snapshot_url ? checkSnapshot : refreshImage;
      if (refresh === checkSnapshot) refresh();
      imageTimer = setInterval(refresh, Math.min(30, Math.max(5, detail.refresh_s || 20)) * 1000);
    };
    const sources = options.motion === false ? [] : [
      detail.stream_url && ['hls', detail.stream_url],
      detail.video_url && ['clip', detail.video_url],
      options.embed && detail.embed_url && ['embed', detail.embed_url],
    ].filter(Boolean);

    async function advance() {
      release(); release = () => {};
      if (disposed) return;
      const version = ++generation, source = sources.shift();
      const current = () => !disposed && version === generation;
      if (!source) return snapshot();
      const [kind, url] = source;
      status(kind === 'clip' ? 'Loading clip…' : 'Connecting…');
      if (kind === 'embed') {
        const frame = document.createElement('iframe');
        frame.title = 'Operator’s camera player'; frame.allow = 'autoplay; encrypted-media; fullscreen; picture-in-picture';
        frame.allowFullscreen = true; frame.src = url;
        const timeout = setTimeout(() => { if (current()) advance(); }, 12000);
        frame.onload = () => { clearTimeout(timeout); if (current()) { image.hidden = true; status(detail.playback_kind === 'timelapse' ? 'Timelapse · past day' : 'Operator player'); } };
        frame.onerror = () => { if (current()) advance(); };
        host.append(frame);
        const refresh = detail.playback_kind === 'timelapse' ? setInterval(() => { if (current() && !document.hidden) frame.src = fresh(url); }, Math.max(60, detail.refresh_s || 600) * 1000) : null;
        release = () => { clearTimeout(timeout); clearInterval(refresh); frame.onload = frame.onerror = null; frame.remove(); };
        return;
      }
      const video = document.createElement('video');
      video.muted = true; video.defaultMuted = true; video.autoplay = true; video.playsInline = true;
      video.loop = kind === 'clip'; video.controls = !!options.controls;
      video.setAttribute('muted', ''); video.setAttribute('playsinline', '');
      video.style.opacity = '0';
      if (imageUrl) video.poster = imageUrl;
      // Safari requires the element to be in the document before muted autoplay.
      host.append(video);
      let hls, reload, watchdog, started = false, lastTime = -1, lastProgress = Date.now();
      const failed = () => { if (current()) advance(); };
      let timeout = setTimeout(failed, 12000);
      const play = () => { if (current()) video.play().catch(failed); };
      video.onplaying = () => {
        if (!current()) return;
        clearTimeout(timeout); video.style.opacity = '1'; image.hidden = true;
        status(kind === 'hls' ? 'Live video' : 'Latest clip', true);
        if (started) return;
        started = true;
        if (kind === 'clip') reload = setInterval(() => {
          if (document.hidden) return;
          video.src = fresh(url); lastProgress = Date.now(); play();
        }, Math.max(30, detail.refresh_s || 300) * 1000);
        watchdog = setInterval(() => {
          if (video.currentTime !== lastTime || document.hidden || (options.controls && video.paused)) {
            lastTime = video.currentTime; lastProgress = Date.now();
          } else if (Date.now() - lastProgress > 15000) failed();
        }, 5000);
      };
      video.onerror = failed;
      release = () => {
        clearTimeout(timeout); clearInterval(reload); clearInterval(watchdog);
        video.onplaying = video.onerror = null; hls?.destroy();
        video.pause(); video.removeAttribute('src'); video.load(); video.remove(); image.hidden = false;
      };
      if (kind === 'hls' && !video.canPlayType('application/vnd.apple.mpegurl')) {
        try {
          const Hls = await loadHls(); if (!current()) return;
          if (!Hls.isSupported()) return failed();
          hls = new Hls({ lowLatencyMode: true, maxBufferLength: 8 });
          hls.on(Hls.Events.ERROR, (_, error) => { if (error.fatal) failed(); });
          hls.on(Hls.Events.MANIFEST_PARSED, play);
          hls.loadSource(url); hls.attachMedia(video);
        } catch { failed(); }
      } else { video.src = kind === 'clip' ? fresh(url) : url; play(); }
    }
    advance();
    return () => {
      disposed = true; generation++; release(); clearInterval(imageTimer);
      snapshotRequest?.abort();
      if (objectUrl) URL.revokeObjectURL(objectUrl);
      image.onload = image.onerror = null;
      if (pendingImage) pendingImage.onload = pendingImage.onerror = null;
      host.replaceChildren();
    };
  };
})();
